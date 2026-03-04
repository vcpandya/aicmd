"""Configuration management for zx CLI."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".zx"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Provider-to-env-var mapping
PROVIDER_ENV_MAP = {
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

# Local providers that don't need API keys
LOCAL_PROVIDERS = ("ollama", "ollama_chat", "vllm", "local")


@dataclass
class ZxConfig:
    api_key: str = ""                           # Legacy (Gemini API key)
    auto_approve: bool = False
    model: str = "gemini/gemini-2.0-flash-lite"  # LiteLLM format
    clean_mode: bool = False
    github_token: str = ""
    community_opt_out: bool = False

    # Multi-provider support
    provider_keys: dict = field(default_factory=dict)  # {"gemini": "...", "openrouter": "...", ...}
    api_base: str = ""                          # Custom API base URL (for vLLM, local models)

    # Budget controls
    monthly_budget: float = 0.0                 # $0 = unlimited
    session_budget: float = 0.0                 # $0 = unlimited
    show_cost: bool = True                      # Show cost after each run

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))
        # Restrict file permissions — API key is sensitive
        try:
            CONFIG_FILE.chmod(0o600)
        except OSError:
            pass  # Windows doesn't support Unix permissions the same way

    @classmethod
    def load(cls) -> "ZxConfig":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                config = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

                # Auto-migrate old model strings (no provider prefix)
                if "/" not in config.model and config.model.startswith("gemini"):
                    config.model = f"gemini/{config.model}"

                # Migrate legacy api_key to provider_keys
                if config.api_key and "gemini" not in config.provider_keys:
                    config.provider_keys["gemini"] = config.api_key

                return config
            except (json.JSONDecodeError, TypeError):
                return cls()
        return cls()


def get_provider_config(model: str = "") -> dict:
    """Resolve API key and base URL for the given model.

    Returns: {"api_key": ..., "api_base": ..., "model": ...}
    """
    config = ZxConfig.load()
    model = model or config.model

    # Determine provider from model string
    provider = model.split("/")[0] if "/" in model else "gemini"

    # Local models don't need API keys
    if provider in LOCAL_PROVIDERS:
        return {
            "api_key": "",
            "api_base": config.api_base or "http://localhost:11434",
            "model": model,
        }

    # Check provider-specific env vars first
    api_key = ""
    if provider in PROVIDER_ENV_MAP:
        api_key = os.environ.get(PROVIDER_ENV_MAP[provider], "").strip()

    # Fall back to config provider_keys
    if not api_key:
        api_key = config.provider_keys.get(provider, "")

    # Fall back to legacy api_key for gemini
    if not api_key and provider == "gemini":
        api_key = config.api_key

    if not api_key:
        env_var = PROVIDER_ENV_MAP.get(provider, provider.upper() + "_API_KEY")
        from .ui import print_error
        print_error(f"No API key for provider '{provider}'. Set {env_var} or run: zx setup")
        raise SystemExit(1)

    # Set the env var so LiteLLM can pick it up
    if provider in PROVIDER_ENV_MAP:
        os.environ[PROVIDER_ENV_MAP[provider]] = api_key

    return {
        "api_key": api_key,
        "api_base": config.api_base or "",
        "model": model,
    }


def get_api_key() -> str:
    """Legacy helper — resolves API key for the configured model.

    Returns the API key string. For local models, returns empty string.
    """
    config = ZxConfig.load()
    provider_config = get_provider_config(config.model)
    return provider_config["api_key"]


def run_setup() -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt

    console = Console()

    console.print()
    console.print(Panel(
        "[bold cyan]zx[/] Setup Wizard",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    config = ZxConfig.load()

    # ── Provider selection ─────────────────────────────────────────────────
    console.print("[bold]Select providers to configure:[/]")
    console.print("  1. [cyan]Gemini[/] (Google)       — gemini/gemini-2.0-flash-lite")
    console.print("  2. [cyan]OpenRouter[/]            — openrouter/anthropic/claude-3.5-sonnet")
    console.print("  3. [cyan]Ollama[/] (local)        — ollama_chat/llama3")
    console.print("  4. [cyan]OpenAI[/]                — openai/gpt-4o")
    console.print("  5. [cyan]Anthropic[/]             — anthropic/claude-3.5-sonnet")
    console.print("  6. [cyan]Other[/] (custom)        — any LiteLLM-supported model")
    console.print()

    providers_input = Prompt.ask(
        "[bold]Enter provider numbers (comma-separated)[/]",
        default="1",
    )
    selected = [p.strip() for p in providers_input.split(",")]

    provider_map = {
        "1": "gemini", "2": "openrouter", "3": "ollama",
        "4": "openai", "5": "anthropic", "6": "other",
    }

    for num in selected:
        provider = provider_map.get(num)
        if not provider:
            continue

        if provider in LOCAL_PROVIDERS or provider == "ollama":
            # Local provider — ask for endpoint
            base = Prompt.ask(
                f"[bold]{provider} endpoint[/]",
                default=config.api_base or "http://localhost:11434",
            )
            config.api_base = base
            console.print(f"  [green]Configured {provider} at {base}[/]")
        elif provider == "other":
            # Custom provider
            custom_key = Prompt.ask("[bold]API key for custom provider[/]", default="")
            custom_base = Prompt.ask("[bold]API base URL (optional)[/]", default="")
            if custom_key:
                custom_name = Prompt.ask("[bold]Provider name[/]", default="custom")
                config.provider_keys[custom_name] = custom_key
            if custom_base:
                config.api_base = custom_base
        else:
            # Cloud provider — ask for API key
            current = config.provider_keys.get(provider, "")
            if provider == "gemini" and not current:
                current = config.api_key
            hint = f" [dim](current: {current[:8]}...)[/]" if current else ""
            env_var = PROVIDER_ENV_MAP.get(provider, "")
            env_hint = f" [dim]or set {env_var}[/]" if env_var else ""

            api_key = Prompt.ask(
                f"[bold]{provider} API key{hint}[/]{env_hint}",
                default=current or None,
            )
            if api_key:
                config.provider_keys[provider] = api_key
                if provider == "gemini":
                    config.api_key = api_key  # Legacy compat
                console.print(f"  [green]Saved {provider} key[/]")

    # ── Default model ──────────────────────────────────────────────────────
    console.print()
    model_suggestions = {
        "gemini": "gemini/gemini-2.0-flash-lite",
        "openrouter": "openrouter/anthropic/claude-3.5-sonnet",
        "ollama": "ollama_chat/llama3",
        "openai": "openai/gpt-4o",
        "anthropic": "anthropic/claude-3.5-sonnet",
    }
    first_provider = provider_map.get(selected[0] if selected else "1", "gemini")
    default_model = model_suggestions.get(first_provider, config.model)

    model = Prompt.ask(
        "[bold]Default model[/]",
        default=default_model,
    )
    config.model = model

    # ── Validate key with a test call ──────────────────────────────────────
    provider = model.split("/")[0] if "/" in model else "gemini"
    test_key = config.provider_keys.get(provider, config.api_key)

    if test_key and provider not in LOCAL_PROVIDERS:
        console.print("[dim]Validating API key...[/]", end=" ")
        try:
            import litellm
            if provider in PROVIDER_ENV_MAP:
                os.environ[PROVIDER_ENV_MAP[provider]] = test_key
            litellm.completion(
                model=model,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=5,
            )
            console.print("[green]Valid![/]")
        except Exception as e:
            console.print(f"[red]Failed: {e}[/]")
            console.print("[yellow]Saving anyway — you can fix it later.[/]")

    # ── Auto-approve ───────────────────────────────────────────────────────
    config.auto_approve = Confirm.ask(
        "[bold]Enable auto-approve by default?[/]",
        default=config.auto_approve,
    )

    # ── Clean mode ─────────────────────────────────────────────────────────
    config.clean_mode = Confirm.ask(
        "[bold]Enable clean/classic mode?[/] [dim](no colors, no panels, no emojis)[/]",
        default=config.clean_mode,
    )

    # ── Budget controls ────────────────────────────────────────────────────
    console.print()
    console.print("[bold]Budget Controls[/] [dim](prevent surprise bills, $0 = unlimited)[/]")

    monthly_str = Prompt.ask(
        "[bold]Monthly spending limit ($)[/]",
        default=str(config.monthly_budget) if config.monthly_budget > 0 else "0",
    )
    try:
        config.monthly_budget = float(monthly_str)
    except ValueError:
        config.monthly_budget = 0.0

    session_str = Prompt.ask(
        "[bold]Per-session spending limit ($)[/]",
        default=str(config.session_budget) if config.session_budget > 0 else "0",
    )
    try:
        config.session_budget = float(session_str)
    except ValueError:
        config.session_budget = 0.0

    config.show_cost = Confirm.ask(
        "[bold]Show cost summary after each run?[/]",
        default=config.show_cost,
    )

    # ── Community opt-out ──────────────────────────────────────────────────
    config.community_opt_out = Confirm.ask(
        "[bold]Opt out of community success reporting?[/] [dim](anonymous usage stats for shared recipes)[/]",
        default=config.community_opt_out,
    )

    config.save()
    console.print()
    console.print(f"[green]Config saved to {CONFIG_FILE}[/]")
