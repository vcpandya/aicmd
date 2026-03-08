"""Smart Alias Generator for zx — analyze history and create shell shortcuts."""

import json
import os
import platform
from collections import Counter
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

ALIASES_FILE = CONFIG_DIR / "aliases.json"


def _detect_shell_profile() -> tuple[str, Path]:
    """Detect the current shell and its profile file.

    Returns:
        (shell_name, profile_path) tuple
    """
    if platform.system() == "Windows":
        if os.environ.get("PSModulePath"):
            # PowerShell profile
            profile = Path.home() / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
            return "powershell", profile
        return "cmd", Path.home() / "aliases.cmd"

    shell = os.path.basename(os.environ.get("SHELL", "/bin/bash"))
    profiles = {
        "bash": Path.home() / ".bashrc",
        "zsh": Path.home() / ".zshrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
    }
    return shell, profiles.get(shell, Path.home() / ".bashrc")


def format_alias(name: str, command: str, shell: str = "") -> str:
    """Format an alias for the given shell."""
    if not shell:
        shell, _ = _detect_shell_profile()

    if shell == "powershell":
        # Escape single quotes in command
        escaped = command.replace("'", "''")
        return f"function {name} {{ {escaped} }}"
    elif shell == "fish":
        return f"alias {name} '{command}'"
    elif shell == "cmd":
        return f"doskey {name}={command}"
    else:
        # bash/zsh
        escaped = command.replace("'", "'\\''")
        return f"alias {name}='{escaped}'"


def save_aliases(aliases: list[dict]) -> None:
    """Save generated aliases to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ALIASES_FILE.write_text(json.dumps(aliases, indent=2))


def load_aliases() -> list[dict]:
    """Load saved aliases."""
    if not ALIASES_FILE.exists():
        return []
    try:
        return json.loads(ALIASES_FILE.read_text())
    except (json.JSONDecodeError, TypeError):
        return []


def analyze_history_patterns(entries: list[dict]) -> list[dict]:
    """Analyze command history to find patterns worth aliasing.

    Returns list of {"command": ..., "count": ..., "suggested_name": ...}
    """
    # Count command prefixes (first word or first two words)
    cmd_counts = Counter()
    full_counts = Counter()

    for entry in entries:
        cmd = entry.get("command", "").strip()
        if not cmd:
            continue
        full_counts[cmd] += 1
        # Also count the base command (first word)
        parts = cmd.split()
        if len(parts) >= 2:
            cmd_counts[" ".join(parts[:2])] += 1
        cmd_counts[parts[0]] += 1

    # Find commands used 3+ times
    suggestions = []
    seen = set()

    # Full commands first (exact repeats)
    for cmd, count in full_counts.most_common(20):
        if count >= 2 and cmd not in seen:
            parts = cmd.split()
            # Generate a short name
            name = _suggest_alias_name(cmd)
            suggestions.append({
                "command": cmd,
                "count": count,
                "suggested_name": name,
                "type": "exact",
            })
            seen.add(cmd)

    # Command patterns (prefix matches)
    for prefix, count in cmd_counts.most_common(20):
        if count >= 3 and prefix not in seen and len(prefix.split()) >= 2:
            name = _suggest_alias_name(prefix)
            suggestions.append({
                "command": prefix,
                "count": count,
                "suggested_name": name,
                "type": "pattern",
            })
            seen.add(prefix)

    return suggestions[:15]  # Top 15


def _suggest_alias_name(command: str) -> str:
    """Generate a short alias name from a command."""
    parts = command.split()
    if len(parts) == 1:
        return parts[0][:3]

    # Use initials of first few words
    initials = "".join(p[0] for p in parts[:3] if p and p[0].isalpha())
    if initials:
        return initials.lower()

    return parts[0][:2] + parts[1][:1]


def generate_profile_block(aliases: list[dict], shell: str = "") -> str:
    """Generate a block of alias definitions for a shell profile.

    Args:
        aliases: List of {"name": ..., "command": ...}
        shell: Shell name (auto-detected if empty)

    Returns:
        String block to add to shell profile
    """
    if not shell:
        shell, _ = _detect_shell_profile()

    lines = [f"# ── zx-generated aliases ──"]
    for a in aliases:
        lines.append(format_alias(a["name"], a["command"], shell))
    lines.append("# ── end zx aliases ──")
    return "\n".join(lines)


def install_aliases(aliases: list[dict]) -> tuple[bool, str]:
    """Install aliases into the shell profile.

    Returns:
        (success, message) tuple
    """
    shell, profile_path = _detect_shell_profile()
    block = generate_profile_block(aliases, shell)

    try:
        # Read existing profile
        existing = ""
        if profile_path.exists():
            existing = profile_path.read_text()

        # Remove old zx aliases block if present
        marker_start = "# ── zx-generated aliases ──"
        marker_end = "# ── end zx aliases ──"
        if marker_start in existing:
            before = existing[:existing.index(marker_start)]
            after_idx = existing.index(marker_end) + len(marker_end)
            after = existing[after_idx:]
            existing = before.rstrip() + after.lstrip("\n")

        # Append new block
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        new_content = existing.rstrip() + "\n\n" + block + "\n"
        profile_path.write_text(new_content)

        return True, f"Installed {len(aliases)} aliases to {profile_path}"
    except Exception as e:
        return False, f"Failed to install aliases: {e}"


def run_alias(
    action: str = "",
    alias_name: str = "",
    alias_command: str = "",
    ai_client=None,
) -> None:
    """Main alias flow.

    Args:
        action: 'suggest', 'list', 'add', 'install', or empty
        alias_name: Name for 'add' action or natural language for AI alias
        alias_command: Command for 'add' action
        ai_client: AIClient for AI-powered suggestions
    """
    from .ui import print_banner, print_success, print_error, print_warning, print_info, show_spinner, is_clean_mode

    print_banner()

    if action == "suggest":
        _suggest_aliases(ai_client)
    elif action == "list":
        _list_aliases()
    elif action == "install":
        _install_aliases()
    elif action == "add" and alias_name and alias_command:
        _add_alias(alias_name, alias_command)
    elif alias_name and not alias_command:
        # Natural language alias creation
        _create_nl_alias(alias_name, ai_client)
    else:
        print_warning("Usage:")
        print_info("  zx alias suggest          Analyze history and suggest aliases")
        print_info("  zx alias list             Show saved aliases")
        print_info("  zx alias add <name> <cmd> Add a custom alias")
        print_info('  zx alias "deploy"         Create alias from natural language')
        print_info("  zx alias install          Install aliases to shell profile")


def _suggest_aliases(ai_client=None) -> None:
    from .ui import print_info, print_success, print_warning, show_spinner, is_clean_mode
    from . import history

    entries = history.get_entries()
    if not entries:
        print_warning("No command history found. Use zx to run some commands first!")
        return

    # Basic pattern analysis
    patterns = analyze_history_patterns(entries)

    if ai_client:
        # Use AI to generate better suggestions
        with show_spinner("thinking"):
            try:
                commands_summary = "\n".join(
                    f"- {e.get('command', '')} (prompt: {e.get('prompt', '')})"
                    for e in entries[-50:]
                )
                response = ai_client.suggest_aliases(commands_summary)
                if response and response.aliases:
                    print_info("\n  AI-Suggested Aliases:")
                    print_info(f"  {'Name':<15} {'Command':<50} Reason")
                    print_info(f"  {'─'*15} {'─'*50} {'─'*30}")
                    for a in response.aliases:
                        name = a.name if hasattr(a, "name") else a.get("name", "")
                        command = a.command if hasattr(a, "command") else a.get("command", "")
                        reason = a.reason if hasattr(a, "reason") else a.get("reason", "")
                        print_info(f"  {name:<15} {command:<50} {reason}")

                    # Ask to save
                    if is_clean_mode():
                        choice = input("\n  Save these aliases? [y/N]: ").strip().lower()
                    else:
                        from rich.prompt import Prompt
                        choice = Prompt.ask("\n  Save these aliases?", choices=["y", "n"], default="n", show_choices=False)

                    if choice == "y":
                        existing = load_aliases()
                        for a in response.aliases:
                            entry = a.model_dump() if hasattr(a, "model_dump") else a
                            existing.append(entry)
                        save_aliases(existing)
                        print_success(f"Saved {len(response.aliases)} aliases.")
                    return
            except Exception:
                pass  # Fall through to pattern-based suggestions

    if not patterns:
        print_warning("Not enough command history to suggest aliases. Keep using zx!")
        return

    shell, _ = _detect_shell_profile()
    print_info(f"\n  Suggested Aliases (for {shell}):")
    print_info(f"  {'Name':<12} {'Used':>5}  {'Type':<8}  Command")
    print_info(f"  {'─'*12} {'─'*5}  {'─'*8}  {'─'*40}")
    for p in patterns:
        alias_line = format_alias(p["suggested_name"], p["command"], shell)
        print_info(f"  {p['suggested_name']:<12} {p['count']:>5}  {p['type']:<8}  {p['command']}")

    # Offer to save
    if is_clean_mode():
        choice = input("\n  Save suggested aliases? [y/N]: ").strip().lower()
    else:
        from rich.prompt import Prompt
        choice = Prompt.ask("\n  Save suggested aliases?", choices=["y", "n"], default="n", show_choices=False)

    if choice == "y":
        aliases = [{"name": p["suggested_name"], "command": p["command"]} for p in patterns]
        existing = load_aliases()
        existing.extend(aliases)
        save_aliases(existing)
        print_success(f"Saved {len(aliases)} aliases.")


def _list_aliases() -> None:
    from .ui import print_info, print_warning

    aliases = load_aliases()
    if not aliases:
        print_warning("No aliases saved. Use 'zx alias suggest' or 'zx alias add' first.")
        return

    shell, _ = _detect_shell_profile()
    print_info(f"\n  Saved Aliases ({shell} format):")
    print_info(f"  {'Name':<15} Command")
    print_info(f"  {'─'*15} {'─'*50}")
    for a in aliases:
        print_info(f"  {a['name']:<15} {a['command']}")
    print_info(f"\n  Total: {len(aliases)} aliases")
    print_info("  Use 'zx alias install' to add them to your shell profile.")


def _add_alias(name: str, command: str) -> None:
    from .ui import print_success

    aliases = load_aliases()
    aliases.append({"name": name, "command": command})
    save_aliases(aliases)
    shell, _ = _detect_shell_profile()
    print_success(f"Alias added: {format_alias(name, command, shell)}")


def _install_aliases() -> None:
    from .ui import print_success, print_error, print_warning

    aliases = load_aliases()
    if not aliases:
        print_warning("No aliases to install. Use 'zx alias suggest' or 'zx alias add' first.")
        return

    success, msg = install_aliases(aliases)
    if success:
        print_success(msg)
        shell, _ = _detect_shell_profile()
        if shell in ("bash", "zsh"):
            print_success(f"Reload with: source ~/.{shell}rc")
        elif shell == "powershell":
            print_success("Restart PowerShell to load new aliases.")
    else:
        print_error(msg)


def _create_nl_alias(description: str, ai_client=None) -> None:
    from .ui import print_info, print_success, print_error, print_warning, show_spinner, is_clean_mode

    if not ai_client:
        print_error("AI client required for natural language alias creation.")
        return

    with show_spinner("thinking"):
        try:
            resp = ai_client.generate_command(f"Create a single shell command that does: {description}")
        except Exception as e:
            print_error(f"AI error: {e}")
            return

    if ai_client.is_done(resp):
        print_warning("Could not generate a command for that description.")
        return

    command = resp.command
    # Suggest a name
    name = _suggest_alias_name(description)

    shell, _ = _detect_shell_profile()
    print_info(f"\n  Suggested alias:")
    print_info(f"  {format_alias(name, command, shell)}")

    if is_clean_mode():
        custom_name = input(f"  Alias name [{name}]: ").strip() or name
    else:
        from rich.prompt import Prompt
        custom_name = Prompt.ask(f"  Alias name", default=name)

    _add_alias(custom_name, command)
