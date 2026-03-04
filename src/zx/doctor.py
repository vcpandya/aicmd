"""Failure Doctor for zx — diagnose and fix command errors."""

import os
import platform
import sys


def get_last_shell_command() -> tuple[str, str]:
    """Try to read the last command from shell history.

    Returns:
        (command, source) tuple where source is 'history', 'fallback', etc.
    """
    shell = ""
    if platform.system() == "Windows":
        if os.environ.get("PSModulePath"):
            shell = "powershell"
        else:
            shell = "cmd"
    else:
        shell = os.environ.get("SHELL", "/bin/bash")

    from .executor import execute_command

    # Try shell-specific history commands
    if "powershell" in shell.lower() or "pwsh" in shell.lower():
        result = execute_command("(Get-History -Count 1).CommandLine")
        if result.success and result.stdout.strip():
            return result.stdout.strip(), "PowerShell history"

    elif "bash" in shell or "zsh" in shell:
        result = execute_command("fc -ln -1 2>/dev/null")
        if result.success and result.stdout.strip():
            return result.stdout.strip(), "shell history"

    return "", ""


def read_piped_input() -> str:
    """Read error output piped to stdin."""
    if not sys.stdin.isatty():
        return sys.stdin.read()[:10000]
    return ""


def run_fix(
    description: str = "",
    ai_client=None,
) -> None:
    """Main fix flow: gather context, diagnose, suggest fix, execute.

    Args:
        description: Manual error description (optional)
        ai_client: AIClient instance
    """
    from .ui import (
        print_banner, print_command, print_success, print_error,
        print_warning, print_info, print_output_header, print_output_line,
        confirm_execution, show_spinner, is_clean_mode,
    )
    from .executor import execute_command
    from .safety import analyze_risk

    print_banner()

    # Step 1: Gather context
    error_output = ""
    failed_command = ""

    # Check for piped input first
    piped = read_piped_input()
    if piped:
        error_output = piped
        print_info(f"  Received {len(piped):,} chars of error output from pipe")
    elif description:
        error_output = description
        print_info(f"  Diagnosing: {description}")
    else:
        # Try to get last command from shell history
        cmd, source = get_last_shell_command()
        if cmd:
            failed_command = cmd
            print_info(f"  Last command (from {source}): {cmd}")
            # Try to re-run it to capture the error
            print_info("  Re-running to capture error output...")
            result = execute_command(cmd)
            if not result.success:
                error_output = result.stderr or result.stdout
                print_info(f"  Captured {len(error_output)} chars of output")
            else:
                print_success("The command succeeded this time! No fix needed.")
                return
        else:
            print_warning("No error context found. Usage:")
            print_info("  command_that_failed 2>&1 | zx fix    (pipe error output)")
            print_info("  zx fix \"description of the error\"    (describe manually)")
            print_info("  zx fix                                (auto-read last command)")
            return

    if not error_output and not failed_command:
        print_error("No error output to diagnose.")
        return

    # Step 1.5: Check community playbooks for a matching fix
    try:
        from .community import match_playbooks_by_error
        matches = match_playbooks_by_error(error_output or failed_command)
        if matches:
            best = matches[0]
            matched = best.get("_matched_symptoms", 0)
            total = best.get("_total_symptoms", 0)
            uses = best.get("success_count", 0)
            print_info(f"\n  Community playbook found!")
            print_info(f"  \"{best.get('name', '?')}\" ({uses} successful uses)")
            print_info(f"  Matched {matched}/{total} symptoms")

            try:
                choice = input("  [u]se playbook  [a]i diagnosis  [c]ancel: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "a"

            if choice == "u":
                from .community import install_community_item
                from .playbook import load_playbook, run_playbook
                category = best.get("category", "general")
                name = best.get("name", "")
                install_community_item("playbooks", category, name)
                playbook = load_playbook(name)
                if playbook:
                    run_playbook(playbook)
                    return
                print_warning("Could not load playbook. Falling back to AI diagnosis.")
            elif choice == "c":
                print_info("  Cancelled.")
                return
            # choice == "a" → continue to AI diagnosis
    except Exception:
        pass  # Community features should never break the fix flow

    # Step 2: Send to AI for diagnosis
    with show_spinner("thinking"):
        diagnosis = ai_client.diagnose_failure(
            error_output=error_output,
            failed_command=failed_command,
        )

    # Step 3: Display diagnosis
    if is_clean_mode():
        print(f"\n  Root Cause: {diagnosis.root_cause}")
        print(f"  Confidence: {diagnosis.confidence}")
        print(f"\n  Fix: {diagnosis.fix_command}")
        print(f"  Explanation: {diagnosis.explanation}")
    else:
        from rich.panel import Panel
        from rich import box
        from .ui import console, S_AI, S_OK, S_WARN, S_DIM, SYM_BULB, SYM_WARN

        # Root cause panel
        confidence_color = {"high": "green", "medium": "yellow", "low": "red"}.get(diagnosis.confidence, "white")
        console.print()
        console.print(Panel(
            f"[bold bright_white]{diagnosis.root_cause}[/]\n\n"
            f"[{S_DIM}]Confidence: [{confidence_color}]{diagnosis.confidence}[/][/]",
            title=f"[{S_AI}]{SYM_BULB} Diagnosis[/]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        ))

    # Step 4: Show fix command and confirm
    risk = analyze_risk(diagnosis.fix_command)
    print_command(diagnosis.fix_command, risk_label=risk, explanation=diagnosis.explanation)

    choice = confirm_execution(
        auto_approve=False,
        is_dangerous=(risk == "DANGEROUS"),
        is_supersafe=(risk == "SUPERSAFE"),
    )

    if choice == "y":
        print_output_header()
        result = execute_command(
            diagnosis.fix_command,
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
        )
        if result.success:
            print_success("Fix applied successfully!")
        else:
            print_error(f"Fix command failed (exit code {result.return_code})")
    elif choice == "c":
        try:
            import pyperclip
            pyperclip.copy(diagnosis.fix_command)
            print_success("Copied fix to clipboard.")
        except Exception:
            print_warning(f"Could not copy. Command: {diagnosis.fix_command}")
    else:
        print_info("  Fix not applied.")

    # Step 5: Prevention tip
    if diagnosis.prevention_tip:
        if is_clean_mode():
            print(f"\n  Prevention tip: {diagnosis.prevention_tip}")
        else:
            from .ui import console, S_DIM, SYM_BULB
            console.print(f"\n  [{S_DIM}]{SYM_BULB} Tip: {diagnosis.prevention_tip}[/]")

    # Step 6: Offer to save as playbook (only after successful fix)
    if choice == "y" and result.success:
        try:
            save_choice = input("\n  Save as reusable playbook? [y/n]: ").strip().lower()
            if save_choice == "y":
                from .playbook import create_playbook_from_diagnosis
                playbook = create_playbook_from_diagnosis(
                    diagnosis=diagnosis,
                    error_output=error_output,
                    failed_command=failed_command,
                    ai_client=ai_client,
                )
                if playbook:
                    share_choice = input("  Share to community? [y/n]: ").strip().lower()
                    if share_choice == "y":
                        from .community import run_share
                        run_share(playbook.name, item_type="playbook")
        except (EOFError, KeyboardInterrupt):
            pass
