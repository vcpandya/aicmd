"""CLI entry point for zx — natural language to terminal commands."""

import sys
from typing import Optional, Annotated

import typer
from typer.core import TyperGroup

from . import __version__


class ZxGroup(TyperGroup):
    """Custom group that passes unknown commands as the prompt to the default handler."""

    def parse_args(self, ctx, args):
        """Intercept args: if the first arg isn't a known command, treat all as prompt."""
        if args and args[0].startswith("@") and len(args) >= 2:
            # Remote execution: zx @host "prompt" → remote --name=host "prompt"
            host_name = args[0][1:]  # Strip @
            prompt = " ".join(args[1:])
            args = ["_remote_run", "--target", host_name, prompt]
        elif args and args[0] not in self.commands and not args[0].startswith("-"):
            # Not a subcommand — inject 'run' as the subcommand and pass args
            args = ["run"] + args
        return super().parse_args(ctx, args)

    def format_usage(self, ctx, formatter):
        formatter.write_usage(ctx.command_path, '[OPTIONS] COMMAND [ARGS]...\n       zx "natural language prompt" [OPTIONS]')


app = typer.Typer(
    name="zx",
    cls=ZxGroup,
    help="Natural language to terminal commands via AI (100+ providers).",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# ── Version callback ─────────────────────────────────────────────────────────


def _version_callback(value: bool):
    if value:
        from rich import print as rprint
        rprint(f"[bold cyan]zx[/] v{__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", help="Show version.", callback=_version_callback, is_eager=True),
    ] = None,
    clean: Annotated[
        bool,
        typer.Option("--clean", help="Clean/classic mode — plain text, no colors, no panels, no emojis."),
    ] = False,
):
    import os
    from .ui import set_clean_mode
    from .config import ZxConfig

    # Check all activation methods: --clean flag, ZX_CLEAN env var, config
    if clean or os.environ.get("ZX_CLEAN", "").strip() in ("1", "true", "yes"):
        set_clean_mode(True)
    else:
        config = ZxConfig.load()
        if config.clean_mode:
            set_clean_mode(True)


# ── Default 'run' command (hidden — invoked automatically) ───────────────────


@app.command("run", hidden=True)
def run_cmd(
    ctx: typer.Context,
    prompt: Annotated[str, typer.Argument(help="Natural language prompt.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Auto-approve commands (except dangerous ones)."),
    ] = False,
    setup: Annotated[
        bool,
        typer.Option("--setup", help="Configure API key and preferences."),
    ] = False,
    single: Annotated[
        bool,
        typer.Option("--single", "-s", help="Single command mode (no multi-step)."),
    ] = False,
    no_plan: Annotated[
        bool,
        typer.Option("--no-plan", help="Use legacy multi-step mode instead of plan mode."),
    ] = False,
    copy: Annotated[
        bool,
        typer.Option("--copy", "-c", help="Copy command to clipboard instead of executing."),
    ] = False,
    snapshot: Annotated[
        bool,
        typer.Option("--snapshot", help="Auto-take before/after snapshots around execution."),
    ] = False,
):
    from .config import ZxConfig
    from .ui import (
        print_banner, print_command, confirm_execution, show_spinner,
        print_output_line, print_success, print_error, print_warning,
        print_step_header, print_done, print_abort,
        prompt_refinement, print_piped_context, console, print_info,
    )
    from .ai import AIClient
    from .executor import execute_command
    from .context import ExecutionContext
    from .safety import analyze_risk
    from . import history

    print_banner()

    # Validate prompt
    if not prompt.strip():
        print_error("Prompt cannot be empty. Example: zx \"list all python files\"")
        raise typer.Exit(1)

    # Auto-snapshot: take "before" snapshot
    before_snap = None
    if snapshot:
        from .snapshot import take_snapshot, save_snapshot, diff_snapshots
        print_info("  [dim]Taking pre-execution snapshot...[/]")
        before_snap = take_snapshot(name="before")

    config = ZxConfig.load()
    from .config import get_provider_config
    provider_cfg = get_provider_config(config.model)
    api_key = provider_cfg["api_key"]
    auto_approve = yes or config.auto_approve

    # Check for piped stdin
    stdin_context = ""
    if not sys.stdin.isatty():
        stdin_context = sys.stdin.read()[:10000]
        print_piped_context(len(stdin_context))

    ai = AIClient(api_key=api_key, model=config.model, config=config)

    if single:
        _run_single(ai, prompt, auto_approve, copy, stdin_context)
    elif no_plan:
        _run_multi_step(ai, prompt, auto_approve, copy, stdin_context)
    else:
        from .planner import run_plan_mode
        run_plan_mode(ai, prompt, auto_approve, copy, stdin_context)

    # Show cost summary after run
    if ai.cost_tracker.session_records and config.show_cost:
        from .ui import print_cost_summary
        print_cost_summary(ai.cost_tracker.get_session_summary())

    # Auto-snapshot: take "after" snapshot and show diff
    if snapshot and before_snap:
        print_info("  [dim]Taking post-execution snapshot...[/]")
        after_snap = take_snapshot(name="after")
        save_snapshot(before_snap)
        save_snapshot(after_snap)
        diffs = diff_snapshots(before_snap, after_snap)
        print_info("\n  Changes detected:")
        for line in diffs:
            print_info(f"  {line}")


# ── Chat command ─────────────────────────────────────────────────────────────


@app.command("chat", help="Interactive conversational mode — AI asks questions, runs commands, and adapts.")
def chat_cmd(
    prompt: Annotated[
        Optional[str],
        typer.Argument(help="Optional starting prompt (or just start chatting)."),
    ] = None,
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .ui import (
        print_banner, print_command, print_output_header, print_output_line,
        print_success, print_error, print_warning, print_info,
        show_spinner, console, confirm_execution,
    )
    from .ui import SYM_BRAIN, SYM_GEAR, SYM_BOLT, S_AI, S_DIM
    from .executor import execute_command
    from .safety import analyze_risk
    from . import history

    print_banner()

    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    # Check for piped stdin
    stdin_context = ""
    if not sys.stdin.isatty():
        stdin_context = sys.stdin.read()[:10000]

    # Initialize chat
    initial = prompt or ""
    ai.start_interactive_chat(initial_prompt=initial, stdin_context=stdin_context)

    console.print()
    if not initial:
        console.print(f"  [{S_AI}]{SYM_BRAIN} Chat mode[/] — describe what you need. Type [bold]quit[/] or [bold]exit[/] to end.")
        console.print()

    # If we have an initial prompt, get the first response
    if initial:
        console.print(f"  [{S_DIM}]You: {initial}[/]")
        console.print()
        with show_spinner("thinking"):
            response = ai.chat_interactive_send()
    else:
        response = None

    while True:
        # If no response yet (first loop without initial prompt), get user input
        if response is None:
            try:
                user_input = console.input(f"  [{S_AI}]{SYM_BOLT}[/] [bold]You:[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                print_info(f"  [{S_DIM}]Chat ended.[/]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "bye", "q"):
                print_info(f"  [{S_DIM}]Chat ended.[/]")
                break

            with show_spinner("thinking"):
                response = ai.chat_interactive_send(user_input)

        # Handle the response
        if response.type == "question":
            console.print(f"  [{S_AI}]{SYM_BRAIN}[/] {response.message}")
            console.print()
            response = None  # Next loop will get user input
            continue

        elif response.type == "answer":
            console.print(f"  [{S_AI}]{SYM_BRAIN}[/] {response.message}")
            console.print()
            response = None
            continue

        elif response.type == "command":
            risk = analyze_risk(response.command)
            print_command(response.command, risk_label=risk, explanation=response.message)

            choice = confirm_execution(
                auto_approve=config.auto_approve,
                is_dangerous=(risk == "DANGEROUS" or response.is_dangerous),
                is_supersafe=(risk == "SUPERSAFE"),
            )

            if choice == "n":
                ai.add_command_result(response.command, "", "User skipped this command.", -1)
                print_warning("  Skipped. Tell me what to do instead.")
                console.print()
                response = None
                continue
            elif choice == "c":
                _copy_to_clipboard(response.command)
                response = None
                continue
            elif choice == "e":
                from .ui import prompt_refinement
                refinement = prompt_refinement()
                with show_spinner("thinking"):
                    response = ai.chat_interactive_send(f"User wants to adjust: {refinement}")
                continue

            # Execute the command
            print_output_header()
            result = execute_command(
                response.command,
                on_stdout=lambda line: print_output_line(line),
                on_stderr=lambda line: print_output_line(line, is_stderr=True),
            )

            history.add_entry(
                prompt or "chat", response.command,
                shell=ai.shell_info.get("shell", ""),
                success=result.success,
            )

            if result.success:
                print_success(f"Done (exit code 0)")
            else:
                print_error(f"Failed (exit code {result.return_code})")

            # Feed result back to AI for next step
            ai.add_command_result(
                response.command, result.stdout, result.stderr, result.return_code,
            )
            console.print()

            # Get AI's next response based on the output
            with show_spinner("thinking"):
                response = ai.chat_interactive_send()
            continue

        elif response.type == "done":
            console.print(f"  [{S_AI}]{SYM_BRAIN}[/] {response.message}")
            console.print()
            response = None
            continue

        else:
            # Unknown type, treat as answer
            console.print(f"  [{S_AI}]{SYM_BRAIN}[/] {response.message}")
            console.print()
            response = None
            continue

    # Show cost summary
    if ai.cost_tracker.session_records and config.show_cost:
        from .ui import print_cost_summary
        print_cost_summary(ai.cost_tracker.get_session_summary())


# ── Setup command ────────────────────────────────────────────────────────────


@app.command("setup", help="Configure API key and preferences interactively.")
def setup_cmd():
    from .config import run_setup
    run_setup()


# ── Explain command ──────────────────────────────────────────────────────────


@app.command("explain", help="Explain what a terminal command does in plain English.")
def explain_cmd(
    command: Annotated[str, typer.Argument(help="The command to explain.")],
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .ui import print_banner, print_explanation, show_spinner, print_cost_summary

    print_banner()
    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    with show_spinner("explaining"):
        resp = ai.explain_command(command)

    print_explanation(command, resp)

    if ai.cost_tracker.session_records and config.show_cost:
        print_cost_summary(ai.cost_tracker.get_session_summary())


# ── History command ──────────────────────────────────────────────────────────


@app.command("history", help="Browse or clear command history.")
def history_cmd(
    clear: Annotated[
        bool,
        typer.Option("--clear", help="Clear all command history."),
    ] = False,
):
    from .ui import print_banner, print_history_table, print_success
    from . import history

    print_banner()
    if clear:
        history.clear_history()
        print_success("History cleared.")
    else:
        entries = history.get_entries()
        print_history_table(entries)


# ── Last command ─────────────────────────────────────────────────────────────


@app.command("last", help="Show the last command that was run.")
def last_cmd():
    from .ui import print_banner, print_command, print_info
    from . import history

    print_banner()
    entries = history.get_entries()
    if not entries:
        print_info("  [dim]No history yet.[/]")
        return
    last = entries[-1]
    print_info(f"  [dim]Prompt:[/] {last.get('prompt', '')}")
    print_command(last.get("command", ""))
    print_info(f"  [dim]{last.get('timestamp', '')[:19]}[/]")


# ── Install command ──────────────────────────────────────────────────────────


@app.command("install", help="Install from a GitHub repo URL, any HTTPS URL, or owner/repo shorthand.")
def install_cmd(
    url: Annotated[str, typer.Argument(help="GitHub URL, HTTPS URL, or owner/repo shorthand.")],
):
    from .config import ZxConfig
    from .ai import AIClient
    from .ui import (
        print_banner, show_spinner, print_error, print_success, print_warning, print_info,
        SYM_LINK, S_AI, S_DIM,
    )
    from .installer import classify_url, parse_github_url, fetch_readme, fetch_url_content, build_install_prompt
    from .planner import run_plan_mode

    print_banner()

    url_type = classify_url(url)
    if not url_type:
        print_error(f"Could not parse URL: {url}")
        print_warning("Expected: https://github.com/owner/repo, owner/repo, or any HTTPS URL")
        raise typer.Exit(1)

    # Fetch content based on URL type
    if url_type == "github":
        parsed = parse_github_url(url)
        if not parsed:
            print_error(f"Could not parse GitHub URL: {url}")
            raise typer.Exit(1)

        owner, repo = parsed
        source_label = f"https://github.com/{owner}/{repo}"
        print_info(f"  [{S_AI}]{SYM_LINK} Repository: {owner}/{repo}[/]")

        with show_spinner("thinking"):
            content = fetch_readme(owner, repo)

        if not content:
            print_error(f"Could not fetch README for {owner}/{repo}")
            print_warning("Check that the repository exists and is accessible.")
            raise typer.Exit(1)
    else:
        source_label = url if "://" in url else f"https://{url}"
        print_info(f"  [{S_AI}]{SYM_LINK} URL: {source_label}[/]")

        with show_spinner("thinking"):
            content = fetch_url_content(url)

        if not content:
            print_error(f"Could not fetch content from: {source_label}")
            raise typer.Exit(1)

    print_success(f"Fetched content ({len(content):,} chars)", witty=False)

    config = ZxConfig.load()
    from .config import get_provider_config
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    install_prompt = build_install_prompt(source_label, content)
    # force_confirm=True: URL-based installs always require manual approval
    run_plan_mode(ai, install_prompt, auto_approve=False, copy_mode=False, stdin_context="", force_confirm=True)


# ── Recipe command ──────────────────────────────────────────────────────────


@app.command("recipe", help="Manage workflow recipes: list, run, save, delete, export, import, explore, share, install.")
def recipe_cmd(
    name: Annotated[Optional[str], typer.Argument(help="Recipe name, or 'explore' to browse community.")] = None,
    list_all: Annotated[
        bool,
        typer.Option("--list", "-l", help="List all saved recipes."),
    ] = False,
    save: Annotated[
        Optional[str],
        typer.Option("--save", "-s", help="Save the last plan as a recipe with this name."),
    ] = None,
    delete: Annotated[
        Optional[str],
        typer.Option("--delete", "-d", help="Delete a recipe by name."),
    ] = None,
    export: Annotated[
        Optional[str],
        typer.Option("--export", help="Export a recipe as a .zxrecipe file."),
    ] = None,
    import_file: Annotated[
        Optional[str],
        typer.Option("--import", help="Import a recipe from a .zxrecipe file."),
    ] = None,
    share: Annotated[
        Optional[str],
        typer.Option("--share", help="Share a recipe to the community."),
    ] = None,
    install: Annotated[
        Optional[str],
        typer.Option("--install", help="Install a community recipe (category/name)."),
    ] = None,
):
    from .ui import (
        print_banner, print_success, print_error, print_warning, print_info,
        print_command, print_output_header, print_output_line,
        confirm_execution, show_spinner,
    )
    from .recipes import (
        list_recipes, load_recipe, delete_recipe, export_recipe,
        import_recipe, replay_recipe, save_recipe, create_recipe_from_plan,
    )

    print_banner()

    # List recipes
    if list_all:
        recipes = list_recipes()
        if not recipes:
            print_info("  No recipes saved yet. Run a plan and save it as a recipe!")
            return
        print_info("  Saved Recipes:")
        print_info(f"  {'Name':<25} {'Steps':>5}  {'Runs':>5}  Description")
        print_info(f"  {'─'*25} {'─'*5}  {'─'*5}  {'─'*40}")
        for r in recipes:
            print_info(f"  {r.name:<25} {len(r.steps):>5}  {r.success_count:>5}  {r.description[:40]}")
        return

    # Save last plan as recipe
    if save:
        from .undo import load_last_plan
        last_plan = load_last_plan()
        if not last_plan:
            print_error("No previous plan found. Run a plan first.")
            return

        steps = last_plan.get("steps", [])
        recipe = create_recipe_from_plan(
            name=save,
            description=last_plan.get("objective", ""),
            steps=steps,
            source_prompt=last_plan.get("objective", ""),
        )
        save_recipe(recipe)
        print_success(f"Recipe '{save}' saved with {len(steps)} steps.")
        return

    # Delete recipe
    if delete:
        if delete_recipe(delete):
            print_success(f"Recipe '{delete}' deleted.")
        else:
            print_error(f"Recipe '{delete}' not found.")
        return

    # Export recipe
    if export:
        path = export_recipe(export)
        if path:
            print_success(f"Recipe exported to: {path}")
        else:
            print_error(f"Recipe '{export}' not found.")
        return

    # Import recipe
    if import_file:
        recipe = import_recipe(import_file)
        if recipe:
            print_success(f"Recipe '{recipe.name}' imported with {len(recipe.steps)} steps.")
        else:
            print_error(f"Could not import recipe from: {import_file}")
        return

    # Share recipe to community
    if share:
        from .community import run_share
        run_share(share, item_type="recipe")
        return

    # Install community recipe
    if install:
        from .community import run_install
        run_install(install)
        return

    # Explore community or run a recipe by name
    if name == "explore":
        from .community import run_explore
        run_explore()
        return

    # Run a recipe by name
    if name:
        # Check if it looks like a search query for explore
        if name.startswith("explore "):
            from .community import run_explore
            run_explore(name[8:])
            return

        recipe = load_recipe(name)
        if not recipe:
            print_error(f"Recipe '{name}' not found. Use 'zx recipe --list' to see available recipes.")
            return

        print_info(f"  Recipe: {recipe.name}")
        print_info(f"  Description: {recipe.description}")
        print_info(f"  Steps: {len(recipe.steps)}")

        # Collect parameters
        params = {}
        if recipe.parameters:
            print_info(f"  Parameters needed: {', '.join(recipe.parameters)}")
            for p in recipe.parameters:
                val = input(f"  Enter value for '{p}': ").strip()
                params[p] = val

        # Replay
        from .executor import execute_command

        def _confirm(cmd, risk, explanation):
            print_command(cmd, risk_label=risk, explanation=explanation)
            return confirm_execution(
                auto_approve=False,
                is_dangerous=(risk == "DANGEROUS"),
                is_supersafe=(risk == "SUPERSAFE"),
            )

        results = replay_recipe(
            recipe, params, execute_command,
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
            confirm_fn=_confirm,
        )

        ok = sum(1 for r in results if r.get("return_code", -1) == 0)
        print_success(f"Recipe complete: {ok}/{len(results)} steps succeeded.")
        return

    # No action specified
    print_warning("Usage: zx recipe --list | zx recipe <name> | zx recipe --save <name>")


# ── Playbook command ────────────────────────────────────────────────────────


@app.command("playbook", help="Incident response playbooks — list, run, create, share.")
def playbook_cmd(
    action: Annotated[
        Optional[str],
        typer.Argument(help="Action: list, run, create, share, or playbook name to run."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Playbook name (for run/share)."),
    ] = None,
):
    from .ui import (
        print_banner, print_success, print_error, print_warning, print_info,
    )

    print_banner()

    if action == "list" or (action is None and name is None):
        from .playbook import list_playbooks
        playbooks = list_playbooks()
        if not playbooks:
            print_info("  No playbooks saved yet.")
            print_info("  Create one from a fix session: zx fix → save as playbook")
            return
        print_info("  Playbooks:")
        print_info(f"  {'Name':<30} {'Severity':<10} {'Runs':>5}  {'Source':<10} Description")
        print_info(f"  {'─'*30} {'─'*10} {'─'*5}  {'─'*10} {'─'*35}")
        for pb in playbooks:
            print_info(
                f"  {pb.name:<30} {pb.severity:<10} {pb.success_count:>5}  "
                f"{pb.source:<10} {pb.description[:35]}"
            )
        return

    if action == "run" or (action and action not in ("list", "create", "share")):
        playbook_name = name or action
        if not playbook_name or playbook_name in ("run",):
            print_warning("Usage: zx playbook run --name <name>  or  zx playbook <name>")
            return
        from .playbook import load_playbook, run_playbook
        pb = load_playbook(playbook_name)
        if not pb:
            print_error(f"Playbook '{playbook_name}' not found.")
            return
        run_playbook(pb)
        return

    if action == "create":
        from .config import ZxConfig
        from .ai import AIClient
        from .playbook import create_playbook_from_diagnosis
        from .undo import load_last_plan

        # Try to create from last fix session context
        print_info("  Creating playbook from last fix session...")
        print_warning("  Note: For best results, run 'zx fix' first, then use the save prompt.")
        print_info("  You can also create playbooks manually by running 'zx fix' and choosing 'save as playbook'.")
        return

    if action == "share":
        if not name:
            print_warning("Usage: zx playbook share --name <name>")
            return
        from .community import run_share
        run_share(name, item_type="playbook")
        return


# ── Undo command ────────────────────────────────────────────────────────────


@app.command("undo", help="Undo the last executed plan (time-travel undo).")
def undo_cmd(
    steps: Annotated[
        Optional[int],
        typer.Option("--steps", "-n", help="Only undo the last N steps."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be undone without executing."),
    ] = False,
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .undo import run_undo

    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    run_undo(ai_client=ai, max_steps=steps, dry_run=dry_run)


# ── Fix command ────────────────────────────────────────────────────────────


@app.command("fix", help="Diagnose and fix command failures. Pipe error output or describe the issue.")
def fix_cmd(
    description: Annotated[
        Optional[str],
        typer.Argument(help="Description of the error (optional — can also pipe error output)."),
    ] = None,
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .doctor import run_fix

    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    run_fix(description=description or "", ai_client=ai)


# ── Alias command ──────────────────────────────────────────────────────────


@app.command("alias", help="Smart shell alias generator — suggest, create, and install aliases.")
def alias_cmd(
    action: Annotated[
        Optional[str],
        typer.Argument(help="Action: suggest, list, add, install, or natural language description."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Alias name (for 'add' action)."),
    ] = None,
    command: Annotated[
        Optional[str],
        typer.Option("--command", "-c", help="Alias command (for 'add' action)."),
    ] = None,
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .alias import run_alias

    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    if action in ("suggest", "list", "install"):
        run_alias(action=action, ai_client=ai)
    elif action == "add" and name and command:
        run_alias(action="add", alias_name=name, alias_command=command)
    elif action and action not in ("suggest", "list", "install", "add"):
        # Treat as natural language alias description
        run_alias(alias_name=action, ai_client=ai)
    else:
        run_alias(ai_client=ai)


# ── Snapshot command ───────────────────────────────────────────────────────


@app.command("snapshot", help="Context snapshots — record and diff system state.")
def snapshot_cmd(
    action: Annotated[
        Optional[str],
        typer.Argument(help="Action: take, list, diff, show, delete."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Snapshot name."),
    ] = None,
):
    from .snapshot import run_snapshot

    run_snapshot(action=action or "", name=name or "")


# ── Learn command ──────────────────────────────────────────────────────────


@app.command("learn", help="Interactive shell tutor — learn shell concepts step by step.")
def learn_cmd(
    topic: Annotated[
        Optional[str],
        typer.Argument(help="Topic to learn (or leave empty for next suggested topic)."),
    ] = None,
    progress: Annotated[
        bool,
        typer.Option("--progress", "-p", help="Show skill tree and progress."),
    ] = False,
):
    from .config import ZxConfig
    from .ai import AIClient
    from .tutor import run_tutor

    if progress:
        run_tutor(show_progress=True)
        return

    config = ZxConfig.load()
    from .config import get_provider_config
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    run_tutor(topic=topic or "", ai_client=ai)


# ── Narrate command ────────────────────────────────────────────────────────


@app.command("narrate", help="Execute a command with live AI commentary on its output.")
def narrate_cmd(
    command: Annotated[str, typer.Argument(help="The command to execute with narration.")],
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .narrate import run_narrate

    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    run_narrate(command=command, ai_client=ai)


# ── Remote @host shorthand (hidden) ───────────────────────────────────────


@app.command("_remote_run", hidden=True)
def remote_run_cmd(
    prompt: Annotated[str, typer.Argument(help="Natural language prompt.")],
    target: Annotated[str, typer.Option("--target", help="Remote host name.")],
):
    from .config import ZxConfig, get_provider_config
    from .ai import AIClient
    from .remote import run_remote

    config = ZxConfig.load()
    provider_cfg = get_provider_config(config.model)
    ai = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    if target == "all":
        run_remote(action="fanout", prompt=prompt, ai_client=ai)
    else:
        run_remote(action="run", name=target, prompt=prompt, ai_client=ai)


# ── Remote command ─────────────────────────────────────────────────────────


@app.command("remote", help="Manage and execute commands on remote hosts via SSH.")
def remote_cmd(
    action: Annotated[
        Optional[str],
        typer.Argument(help="Action: add, remove, list."),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Remote host name."),
    ] = None,
    host: Annotated[
        Optional[str],
        typer.Option("--host", "-H", help="Remote host address (user@ip)."),
    ] = None,
):
    from .remote import run_remote

    ai_client = None
    if action not in ("add", "remove", "list", None):
        from .config import ZxConfig, get_provider_config
        from .ai import AIClient
        config = ZxConfig.load()
        provider_cfg = get_provider_config(config.model)
        ai_client = AIClient(api_key=provider_cfg["api_key"], model=config.model, config=config)

    run_remote(action=action or "", name=name or "", host=host or "", ai_client=ai_client)


# ── Cost command ─────────────────────────────────────────────────────────────


@app.command("cost", help="Show AI usage costs — session, daily, and monthly breakdowns.")
def cost_cmd(
    month: Annotated[
        Optional[str],
        typer.Argument(help="Month to show (e.g. '2026-03'). Defaults to current month."),
    ] = None,
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Clear usage data for the specified month."),
    ] = False,
):
    from .cost import CostTracker
    from .config import ZxConfig
    from .ui import print_banner, print_info, print_success, print_warning
    from datetime import datetime, timezone
    from rich.prompt import Confirm

    print_banner()
    tracker = CostTracker()
    config = ZxConfig.load()

    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    if reset:
        confirmed = False
        try:
            confirmed = Confirm.ask(f"  Clear usage data for {month}?", default=False)
        except Exception:
            # Fallback for non-interactive / clean mode
            resp = input(f"  Clear usage data for {month}? [y/N]: ").strip().lower()
            confirmed = resp in ("y", "yes")
        if confirmed:
            tracker.reset_month(month)
            print_success(f"Usage data for {month} cleared.")
        return

    # Monthly summary
    print_info(f"  {tracker.get_monthly_summary(config, month)}")
    print_info("")

    # Per-model breakdown
    breakdown = tracker.get_monthly_breakdown(month)
    by_model = breakdown.get("by_model", {})
    if by_model:
        print_info("  Per-model breakdown:")
        for model_name, stats in sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True):
            print_info(f"    {model_name}: ${stats['cost']:.4f} | {stats['tokens']:,} tokens | {stats['calls']} calls")
        print_info("")

    # Daily breakdown (last 7 days)
    daily = breakdown.get("daily", {})
    if daily:
        print_info("  Recent daily usage:")
        for day, stats in sorted(daily.items(), reverse=True)[:7]:
            print_info(f"    {day}: ${stats['cost']:.4f} | {stats['tokens']:,} tokens | {stats['calls']} calls")
    else:
        print_info("  No usage data for this month.")


# ── Budget command ───────────────────────────────────────────────────────────


@app.command("budget", help="View or set spending limits for AI usage.")
def budget_cmd(
    monthly: Annotated[
        Optional[float],
        typer.Option("--monthly", "-m", help="Set monthly spending limit ($). Use 0 for unlimited."),
    ] = None,
    session: Annotated[
        Optional[float],
        typer.Option("--session", "-s", help="Set per-session spending limit ($). Use 0 for unlimited."),
    ] = None,
    show: Annotated[
        bool,
        typer.Option("--show", help="Show current budget settings."),
    ] = False,
):
    from .config import ZxConfig
    from .ui import print_banner, print_info, print_success

    print_banner()
    config = ZxConfig.load()

    changed = False
    if monthly is not None:
        config.monthly_budget = monthly
        changed = True
        if monthly > 0:
            print_success(f"Monthly budget set to ${monthly:.2f}")
        else:
            print_success("Monthly budget removed (unlimited)")

    if session is not None:
        config.session_budget = session
        changed = True
        if session > 0:
            print_success(f"Session budget set to ${session:.2f}")
        else:
            print_success("Session budget removed (unlimited)")

    if changed:
        config.save()

    if show or (monthly is None and session is None):
        mb = f"${config.monthly_budget:.2f}" if config.monthly_budget > 0 else "unlimited"
        sb = f"${config.session_budget:.2f}" if config.session_budget > 0 else "unlimited"
        print_info(f"  Monthly budget: {mb}")
        print_info(f"  Session budget: {sb}")
        print_info(f"  Show cost after runs: {'yes' if config.show_cost else 'no'}")


# ── Update command ───────────────────────────────────────────────────────────


@app.command("update", help="Check for updates and refresh the community index.")
def update_cmd():
    import subprocess
    import urllib.request
    import json as _json

    from .ui import print_banner, print_info, print_success, print_warning, print_error, show_spinner
    from .community import fetch_community_index

    print_banner()

    # Step 1: Current version
    current = __version__
    print_info(f"  Current version: v{current}")

    # Step 2: Check PyPI for latest
    latest = None
    try:
        with show_spinner("checking"):
            req = urllib.request.Request(
                "https://pypi.org/pypi/zx-ai/json",
                headers={"User-Agent": "zx-cli", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                latest = data["info"]["version"]
    except Exception:
        print_warning("Could not check PyPI for updates.")

    if latest:
        print_info(f"  Latest version:  v{latest}")
        current_tuple = tuple(int(x) for x in current.split("."))
        latest_tuple = tuple(int(x) for x in latest.split("."))

        if current_tuple < latest_tuple:
            print_info(f"  Upgrading v{current} -> v{latest}...")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "zx-ai"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    print_success(f"Updated to v{latest}")
                else:
                    print_error(f"pip upgrade failed (exit code {result.returncode})")
                    if result.stderr:
                        print_info(f"  {result.stderr.strip()[:200]}")
            except subprocess.TimeoutExpired:
                print_error("pip upgrade timed out.")
            except Exception as e:
                print_error(f"Upgrade failed: {e}")
        else:
            print_success("Already on the latest version.")

    # Step 3: Refresh community index
    print_info("")
    print_info("  Refreshing community index...")
    try:
        with show_spinner("refreshing"):
            index = fetch_community_index(force_refresh=True)
        recipe_count = len(index.get("recipes", []))
        playbook_count = len(index.get("playbooks", []))
        print_success(f"Community index refreshed ({recipe_count} recipes, {playbook_count} playbooks).")
    except Exception:
        print_warning("Could not refresh community index.")


# ── Single-shot mode ─────────────────────────────────────────────────────────


def _run_single(ai, prompt: str, auto_approve: bool, copy_mode: bool, stdin_context: str):
    from .ui import (
        print_command, confirm_execution, show_spinner, print_output_line,
        print_output_header,
        print_success, print_error, print_abort, prompt_refinement,
    )
    from .executor import execute_command
    from .safety import analyze_risk
    from . import history

    with show_spinner("thinking"):
        resp = ai.generate_command(prompt, stdin_context)

    if ai.is_done(resp):
        print_success("No command needed.")
        return

    cmd_str = resp.command

    # Refinement loop
    while True:
        risk = analyze_risk(cmd_str)
        print_command(cmd_str, risk_label=risk, explanation=resp.explanation)

        if copy_mode:
            _copy_to_clipboard(cmd_str)
            return

        choice = confirm_execution(
            auto_approve,
            is_dangerous=(risk == "DANGEROUS"),
            is_supersafe=(risk == "SUPERSAFE"),
        )

        if choice == "n":
            print_abort()
            return
        elif choice == "c":
            _copy_to_clipboard(cmd_str)
            return
        elif choice == "e":
            refinement = prompt_refinement()
            with show_spinner("refining"):
                resp = ai.generate_command(f"{prompt}. Additional requirement: {refinement}", stdin_context)
            if ai.is_done(resp):
                print_success("No command needed.")
                return
            cmd_str = resp.command
            continue
        else:  # 'y'
            break

    # Execute
    print_output_header()
    result = execute_command(
        cmd_str,
        on_stdout=lambda line: print_output_line(line),
        on_stderr=lambda line: print_output_line(line, is_stderr=True),
    )

    history.add_entry(prompt, cmd_str, shell=ai.shell_info.get("shell", ""), success=result.success)

    if result.success:
        print_success(f"Done (exit code {result.return_code})")
    else:
        print_error(f"Failed (exit code {result.return_code})")


# ── Multi-step mode ──────────────────────────────────────────────────────────


def _run_multi_step(ai, prompt: str, auto_approve: bool, copy_mode: bool, stdin_context: str):
    from .ui import (
        print_command, confirm_execution, show_spinner, print_output_line,
        print_output_header,
        print_success, print_error, print_warning, print_step_header,
        print_done, print_abort, prompt_refinement,
    )
    from .executor import execute_command
    from .context import ExecutionContext
    from .safety import analyze_risk
    from . import history

    ctx = ExecutionContext(objective=prompt)
    ai.start_chat(stdin_context)

    with show_spinner("analyzing"):
        resp = ai.chat_send(ctx.build_initial_message())

    while True:
        if ai.is_done(resp):
            if ctx.step_count > 0:
                print_done(ctx.get_summary())
            else:
                print_success("No commands needed.")
            return

        if ctx.is_at_limit:
            print_warning(f"Reached step limit ({ctx.max_steps}). Stopping.")
            print_done(ctx.get_summary())
            return

        cmd_str = resp.command
        step_num = ctx.step_count + 1
        print_step_header(step_num)

        # Refinement loop
        while True:
            risk = analyze_risk(cmd_str)
            print_command(cmd_str, step=step_num, risk_label=risk, explanation=resp.explanation)

            if copy_mode:
                _copy_to_clipboard(cmd_str)
                return

            choice = confirm_execution(
                auto_approve,
                is_dangerous=(risk == "DANGEROUS"),
                is_supersafe=(risk == "SUPERSAFE"),
            )

            if choice == "n":
                print_abort()
                return
            elif choice == "c":
                _copy_to_clipboard(cmd_str)
                return
            elif choice == "e":
                refinement = prompt_refinement()
                with show_spinner("refining"):
                    resp = ai.chat_send(f"User wants to refine the command: {refinement}")
                if ai.is_done(resp):
                    print_done(ctx.get_summary())
                    return
                cmd_str = resp.command
                continue
            else:  # 'y'
                break

        # Execute
        print_output_header()
        result = execute_command(
            cmd_str,
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
        )

        step = ctx.add_step(
            command=cmd_str,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.return_code,
        )

        history.add_entry(prompt, cmd_str, shell=ai.shell_info.get("shell", ""), success=result.success)

        if result.success:
            print_success(f"Step {step_num} done (exit code 0)")
        else:
            print_error(f"Step {step_num} failed (exit code {result.return_code})")

        # Ask AI for next step
        with show_spinner("next_step"):
            resp = ai.chat_send(ctx.build_step_result_message(step))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _copy_to_clipboard(command: str):
    from .ui import print_copied, print_warning
    try:
        import pyperclip
        pyperclip.copy(command)
        print_copied()
    except Exception:
        print_warning(f"Could not copy to clipboard. Command: {command}")


def main():
    """Entry point for the `zx` console script."""
    app()
