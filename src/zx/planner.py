"""Two-phase plan-then-execute orchestration for zx."""

from dataclasses import dataclass, field
from typing import Optional

from .ai import AIClient, PlanResponse, PlanStep, PlanAdaptResponse


@dataclass
class PlanExecutionState:
    """Tracks state during plan execution."""
    objective: str
    original_plan: Optional[PlanResponse] = None
    current_steps: list[PlanStep] = field(default_factory=list)
    completed_steps: list[dict] = field(default_factory=list)
    current_index: int = 0

    @property
    def total_steps(self) -> int:
        return len(self.current_steps)

    @property
    def is_complete(self) -> bool:
        return self.current_index >= self.total_steps

    @property
    def current_step(self) -> Optional[PlanStep]:
        if self.current_index < self.total_steps:
            return self.current_steps[self.current_index]
        return None

    @property
    def remaining_steps(self) -> list[PlanStep]:
        return self.current_steps[self.current_index + 1:]


def run_plan_mode(
    ai: AIClient,
    prompt: str,
    auto_approve: bool,
    copy_mode: bool,
    stdin_context: str,
    force_confirm: bool = False,
) -> None:
    """Main orchestrator for plan-then-execute mode.

    Args:
        force_confirm: If True, overrides auto_approve (used for URL-based installs).
    """
    from .ui import (
        show_spinner, print_plan_table, confirm_plan,
        print_plan_progress, print_command, confirm_execution,
        print_output_header, print_output_line,
        print_success, print_error, print_warning,
        print_done, print_abort, prompt_refinement,
        print_plan_adaptation, print_info,
        print_phase_header, _assign_phases,
        S_DIM, SYM_MAG, SYM_CHECK,
    )
    from .executor import execute_command
    from .safety import analyze_risk
    from . import history

    effective_auto = auto_approve and not force_confirm
    from .ui import print_info

    # ── Phase 0: Quick Recon (skip for simple/short prompts) ──
    recon_context = ""
    if _needs_recon(prompt):
        try:
            with show_spinner("analyzing"):
                recon_context = _gather_system_recon(execute_command, prompt)
            if recon_context:
                print_info(f"  [{S_DIM}]{SYM_MAG} Scanned system environment for smarter planning[/]")
        except Exception:
            pass  # Recon failure is non-fatal

    # ── Phase 0b: Web Search (if configured and useful) ──
    search_context = ""
    try:
        from .search import is_search_available, should_search, web_search, build_search_query
        if is_search_available() and should_search(prompt):
            with show_spinner("searching"):
                query = build_search_query(prompt)
                search_result = web_search(query)
            if search_result.has_results:
                search_context = search_result.raw_context
                print_info(f"  [{S_DIM}]{SYM_MAG} Found {len(search_result.results)} web result(s) for context[/]")
    except Exception:
        pass  # Search failure is non-fatal

    enriched_prompt = prompt
    if recon_context:
        enriched_prompt = f"{prompt}\n\nCURRENT SYSTEM STATE (auto-detected, use this to make a better plan):\n{recon_context}"
    if search_context:
        enriched_prompt = f"{enriched_prompt}\n\nWEB SEARCH CONTEXT (use this for up-to-date information):\n{search_context}"
    if stdin_context:
        enriched_prompt = f"{enriched_prompt}\n\nStdin content:\n{stdin_context[:3000]}"

    # ── Phase 1: Generate Plan ──
    with show_spinner("thinking"):
        plan = ai.generate_plan(enriched_prompt)

    if not plan.steps:
        if plan.summary:
            from .ui import console
            console.print()
            console.print(f"  {plan.summary}")
            console.print()
        else:
            print_success("No commands needed for this request.")
        return

    # ── Handle cd/directory commands — can't change parent shell ──
    if len(plan.steps) == 1 and _is_cd_command(plan.steps[0].command):
        _handle_cd_command(plan.steps[0].command, plan.steps[0].explanation)
        return

    risk_labels = [analyze_risk(step.command) for step in plan.steps]

    # Check if entire plan is supersafe — skip approval for small plans (≤3 steps)
    all_supersafe = (
        all(r == "SUPERSAFE" for r in risk_labels)
        and len(plan.steps) <= 3
        and not force_confirm
    )
    has_dangerous = "DANGEROUS" in risk_labels

    # ── Fast path: single supersafe command — minimal output ──
    if len(plan.steps) == 1 and all_supersafe:
        step = plan.steps[0]
        risk = risk_labels[0]
        print_command(step.command, risk_label=risk, explanation=step.explanation)
        print_output_header()
        result = execute_command(
            step.command,
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
        )
        history.add_entry(prompt, step.command, shell=ai.shell_info.get("shell", ""), success=result.success)
        if result.success:
            print_success(f"Done (exit code 0)")
        else:
            print_error(f"Failed (exit code {result.return_code})")
        return

    if all_supersafe:
        # Supersafe plans execute without any interruption
        print_info(f"  [{S_DIM}]{SYM_CHECK} All commands are supersafe -- executing directly[/]")
    else:
        # Display and approval loop
        print_plan_table(plan, risk_labels)

        while True:
            choice = confirm_plan(has_dangerous)

            if choice == "n":
                print_abort()
                return
            elif choice == "e":
                refinement = prompt_refinement()
                with show_spinner("planning"):
                    plan = ai.generate_plan(
                        f"{prompt}. Additional requirement: {refinement}",
                        stdin_context,
                    )
                if not plan.steps:
                    print_success("No commands needed.")
                    return
                risk_labels = [analyze_risk(step.command) for step in plan.steps]
                all_supersafe = all(r == "SUPERSAFE" for r in risk_labels) and not force_confirm
                has_dangerous = "DANGEROUS" in risk_labels
                if all_supersafe:
                    print_info(f"  [{S_DIM}]{SYM_CHECK} All commands are supersafe -- executing directly[/]")
                    break
                print_plan_table(plan, risk_labels)
                continue
            else:  # 'y'
                break

    # ── Phase 2: Execute Plan Step by Step ──
    state = PlanExecutionState(
        objective=prompt,
        original_plan=plan,
        current_steps=list(plan.steps),
    )

    phases = _assign_phases(risk_labels)
    prev_phase = None

    while not state.is_complete:
        step = state.current_step
        step_num = state.current_index + 1
        total = state.total_steps

        # Show phase transition header
        if state.current_index < len(phases):
            phase = phases[state.current_index]
            if phase != prev_phase:
                print_phase_header(phase)
                prev_phase = phase

        print_plan_progress(step_num, total, step.command)

        risk = analyze_risk(step.command)
        print_command(step.command, step=step_num, risk_label=risk, explanation=step.explanation)

        if copy_mode:
            _copy_to_clipboard(step.command)
            return

        step_choice = confirm_execution(
            effective_auto,
            is_dangerous=(risk == "DANGEROUS"),
            is_supersafe=(risk == "SUPERSAFE" and not force_confirm),
            is_safe=(risk == "SAFE" and not force_confirm),
            plan_approved=True,
        )

        if step_choice == "n":
            print_abort()
            return
        elif step_choice == "c":
            _copy_to_clipboard(step.command)
            return
        elif step_choice == "e":
            refinement = prompt_refinement()
            with show_spinner("adapting"):
                adapted = ai.adapt_plan(
                    original_objective=prompt,
                    completed_steps=state.completed_steps,
                    failed_step={"command": step.command, "reason": f"User requested change: {refinement}"},
                    remaining_steps=[s.model_dump() for s in [step] + list(state.remaining_steps)],
                )
            if adapted.should_abort:
                print_warning(f"AI recommends aborting: {adapted.abort_reason}")
                print_abort()
                return
            state.current_steps = state.current_steps[:state.current_index] + adapted.revised_steps
            risk_labels = [analyze_risk(s.command) for s in state.current_steps]
            phases = _assign_phases(risk_labels)
            prev_phase = None  # Reset so phase headers re-display
            print_plan_adaptation(adapted.assessment, len(adapted.revised_steps))
            continue

        # Execute
        print_output_header()
        result = execute_command(
            step.command,
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
        )

        history.add_entry(
            prompt, step.command,
            shell=ai.shell_info.get("shell", ""),
            success=result.success,
        )

        step_record = {
            "step_number": step_num,
            "command": step.command,
            "return_code": result.return_code,
            "stdout": result.stdout[:1000],
            "stderr": result.stderr[:1000],
        }
        state.completed_steps.append(step_record)

        if result.success:
            print_success(f"Step {step_num}/{total} done (exit code 0)")

            # Output-aware adaptation: if this is an explore-phase step with
            # meaningful output, let the AI re-evaluate remaining steps based
            # on what was discovered (e.g., version mismatch, missing files).
            remaining = state.remaining_steps
            if (
                remaining
                and state.current_index < len(phases)
                and phases[state.current_index] == "EXPLORE"
                and result.stdout.strip()
            ):
                try:
                    with show_spinner("adapting"):
                        adapted = ai.adapt_plan(
                            original_objective=prompt,
                            completed_steps=state.completed_steps,
                            failed_step=step_record,  # not failed, but carries output
                            remaining_steps=[s.model_dump() for s in remaining],
                        )
                    if adapted.revised_steps and not adapted.should_abort:
                        state.current_steps = state.current_steps[:state.current_index + 1] + adapted.revised_steps
                        risk_labels = [analyze_risk(s.command) for s in state.current_steps]
                        phases = _assign_phases(risk_labels)
                        prev_phase = None
                        print_plan_adaptation(adapted.assessment, len(adapted.revised_steps))
                except Exception:
                    pass  # Adaptation failure is non-fatal, continue with original plan

            state.current_index += 1
        else:
            print_error(f"Step {step_num}/{total} failed (exit code {result.return_code})")

            with show_spinner("adapting"):
                adapted = ai.adapt_plan(
                    original_objective=prompt,
                    completed_steps=state.completed_steps,
                    failed_step=step_record,
                    remaining_steps=[s.model_dump() for s in state.remaining_steps],
                )

            if adapted.should_abort:
                print_warning(f"AI recommends aborting: {adapted.abort_reason}")
                _save_plan_for_undo(state)
                _print_summary(state, aborted=True)
                return

            print_plan_adaptation(adapted.assessment, len(adapted.revised_steps))
            state.current_steps = state.current_steps[:state.current_index + 1] + adapted.revised_steps
            risk_labels = [analyze_risk(s.command) for s in state.current_steps]
            phases = _assign_phases(risk_labels)
            prev_phase = None
            state.current_index += 1

    _print_summary(state)

    # Save last plan for undo support
    _save_plan_for_undo(state)

    # Show undo hint if any steps modified state
    has_reversible = any(
        s.is_reversible for s in state.current_steps[:len(state.completed_steps)]
    )
    if has_reversible and state.completed_steps:
        print_info(f"  [{S_DIM}]Tip: run 'zx undo' to revert these changes[/]")

    # Offer to save as recipe if plan was successful
    all_ok = all(cs.get("return_code", 0) == 0 for cs in state.completed_steps)
    if all_ok and state.completed_steps:
        _offer_save_as_recipe(state, ai, prompt)


def _save_plan_for_undo(state: PlanExecutionState) -> None:
    """Save completed plan to last_plan.json for undo support."""
    try:
        from .undo import save_last_plan
        save_last_plan(
            objective=state.objective,
            completed_steps=state.completed_steps,
            plan_steps=state.current_steps,
        )
    except Exception:
        pass  # Don't break the flow if undo save fails


def _offer_save_as_recipe(state: PlanExecutionState, ai: AIClient, prompt: str) -> None:
    """Offer to save a successful plan as a reusable recipe."""
    from .ui import print_info, print_success, is_clean_mode

    try:
        if is_clean_mode():
            choice = input("  Save as recipe? [y/N]: ").strip().lower()
        else:
            from rich.prompt import Prompt
            from .ui import console, S_AI, SYM_GEAR
            console.print()
            choice = Prompt.ask(
                f"  [{S_AI}]{SYM_GEAR}[/] [bold]Save as recipe?[/]  [dim]\\[y]es  \\[N]o[/]",
                choices=["y", "n"],
                default="n",
                show_choices=False,
            ).lower()

        if choice != "y":
            return

        if is_clean_mode():
            name = input("  Recipe name: ").strip()
        else:
            from rich.prompt import Prompt
            name = Prompt.ask("  Recipe name")

        if not name:
            return

        from .recipes import create_recipe_from_plan, save_recipe
        commands = [cs.get("command", "") for cs in state.completed_steps]

        # Try AI parameterization
        try:
            from .ui import show_spinner
            with show_spinner("thinking"):
                param_result = ai.parameterize_recipe(commands, prompt)
            if param_result.parameters:
                print_info(f"  Detected parameters: {', '.join(param_result.parameters)}")
                recipe = create_recipe_from_plan(
                    name=name,
                    description=state.objective,
                    steps=state.current_steps,
                    source_prompt=prompt,
                    parameters=param_result.parameters,
                    parameterized_commands=param_result.parameterized_commands,
                )
            else:
                recipe = create_recipe_from_plan(
                    name=name,
                    description=state.objective,
                    steps=state.current_steps,
                    source_prompt=prompt,
                )
        except Exception:
            recipe = create_recipe_from_plan(
                name=name,
                description=state.objective,
                steps=state.current_steps,
                source_prompt=prompt,
            )

        save_recipe(recipe)
        print_success(f"Recipe '{name}' saved with {len(recipe.steps)} steps.")

    except (EOFError, KeyboardInterrupt):
        pass  # User cancelled


def _print_summary(state: PlanExecutionState, aborted: bool = False) -> None:
    from .ui import print_done
    lines = [f"[bold]Objective:[/] {state.objective}", ""]
    for cs in state.completed_steps:
        status = "[green]OK[/]" if cs["return_code"] == 0 else "[red]FAIL[/]"
        lines.append(f"  {status} Step {cs['step_number']}: [dim]{cs['command']}[/]")
    if aborted:
        lines.append(f"\n  [yellow]Plan aborted after {len(state.completed_steps)} step(s).[/]")
    print_done("\n".join(lines))


def _copy_to_clipboard(command: str):
    from .ui import print_copied, print_warning
    try:
        import pyperclip
        pyperclip.copy(command)
        print_copied()
    except Exception:
        print_warning(f"Could not copy to clipboard. Command: {command}")


def _gather_system_recon(execute_command, prompt: str = "") -> str:
    """Run quick, silent diagnostic commands to gather system state for smarter planning.

    Only checks tools relevant to the prompt to keep recon fast.
    Returns a text summary of what was discovered. All commands are read-only and safe.
    """
    import platform
    import os

    prompt_lower = prompt.lower()
    recon_lines = []

    # Directory listing (top-level only, quick)
    result = execute_command("ls -la" if platform.system() != "Windows" else "dir")
    if result.success and result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        recon_lines.append(f"Current directory contents ({len(lines)} items):")
        # Limit to first 30 lines to keep context manageable
        for line in lines[:30]:
            recon_lines.append(f"  {line}")
        if len(lines) > 30:
            recon_lines.append(f"  ... and {len(lines) - 30} more")

    # Check common runtimes — only those relevant to the prompt
    all_checks = {
        "python": "python --version",
        "node": "node --version",
        "git": "git --version",
        "docker": "docker --version",
        "npm": "npm --version",
        "pip": "pip --version",
        "cargo": "cargo --version",
        "go": "go version",
        "java": "java -version",
    }

    # Map prompt keywords to relevant tools
    _TOOL_KEYWORDS = {
        "python": {"python", "pip", "django", "flask", "fastapi", "venv", "conda", "pytest", "pyproject"},
        "node": {"node", "npm", "yarn", "react", "next", "express", "typescript", "webpack", "vite"},
        "git": {"git", "commit", "push", "pull", "branch", "merge", "clone", "repo"},
        "docker": {"docker", "container", "image", "compose", "kubernetes", "k8s"},
        "npm": {"npm", "node", "yarn", "package.json", "react", "next", "express"},
        "pip": {"pip", "python", "pypi", "package", "install"},
        "cargo": {"cargo", "rust", "rustc", "crate"},
        "go": {"go", "golang", "mod"},
        "java": {"java", "maven", "gradle", "spring", "jar", "jvm"},
    }

    prompt_words = set(prompt_lower.split())

    # Always check git (very common), plus tools matching prompt keywords
    checks = {"git": all_checks["git"]}
    for tool, keywords in _TOOL_KEYWORDS.items():
        if keywords & prompt_words:
            checks[tool] = all_checks[tool]

    # If no specific tools matched, check the 4 most common ones
    if len(checks) <= 1:
        for tool in ("python", "node", "docker", "pip"):
            checks[tool] = all_checks[tool]

    installed = []
    for name, cmd in checks.items():
        result = execute_command(cmd)
        if result.success and result.stdout.strip():
            version_line = result.stdout.strip().split("\n")[0]
            installed.append(f"  {name}: {version_line}")
        elif result.success and result.stderr.strip():
            # java -version outputs to stderr
            version_line = result.stderr.strip().split("\n")[0]
            installed.append(f"  {name}: {version_line}")

    if installed:
        recon_lines.append("\nInstalled tools/runtimes:")
        recon_lines.extend(installed)

    # Check disk space (quick, useful for install tasks)
    if platform.system() != "Windows":
        result = execute_command("df -h . | tail -1")
        if result.success and result.stdout.strip():
            recon_lines.append(f"\nDisk space: {result.stdout.strip()}")
    else:
        # PowerShell or cmd approach
        drive = os.getcwd()[:2]
        result = execute_command(f'wmic logicaldisk where "DeviceID=\'{drive}\'" get FreeSpace,Size /format:value')
        if result.success and result.stdout.strip():
            recon_lines.append(f"\nDisk info: {result.stdout.strip()}")

    return "\n".join(recon_lines) if recon_lines else ""


# ── Simple-task detection helpers ────────────────────────────────────────────


# Keywords that suggest the task is complex and needs system recon
_COMPLEX_KEYWORDS = {
    "install", "setup", "create", "build", "deploy", "configure", "compile",
    "project", "database", "docker", "server", "migrate", "test", "ci",
    "kubernetes", "nginx", "apache", "systemctl", "service",
}


def _needs_recon(prompt: str) -> bool:
    """Heuristic: does this prompt need full system recon?

    Short/simple prompts (navigate, list, check) skip recon entirely.
    """
    words = set(prompt.lower().split())
    # Short prompts without complex keywords don't need recon
    if len(prompt) < 80 and not words & _COMPLEX_KEYWORDS:
        return False
    return True


def _is_cd_command(command: str) -> bool:
    """Check if a command is a directory change (cd, Set-Location, pushd)."""
    cmd = command.strip().lower()
    return (
        cmd.startswith("cd ") or cmd.startswith("cd\t")
        or cmd.startswith("set-location ")
        or cmd.startswith("pushd ")
        or cmd == "cd"
    )


def _handle_cd_command(command: str, explanation: str) -> None:
    """Handle cd commands — can't change parent shell, so offer alternatives."""
    from .ui import print_command, print_info, print_warning

    print_command(command, risk_label="SUPERSAFE", explanation=explanation)
    print_warning(
        "  'cd' runs in a subprocess and cannot change your shell's directory.\n"
        "  Copy and paste the command above, or run it directly."
    )
    try:
        import pyperclip
        pyperclip.copy(command)
        print_info("  (Copied to clipboard)")
    except Exception:
        pass
