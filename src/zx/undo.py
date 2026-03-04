"""Time-travel undo system for zx — reverse the last executed plan."""

import json
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

LAST_PLAN_FILE = CONFIG_DIR / "last_plan.json"


def save_last_plan(objective: str, completed_steps: list[dict], plan_steps: list) -> None:
    """Save the last executed plan for potential undo.

    Args:
        objective: The original user objective
        completed_steps: List of dicts with step results
        plan_steps: List of PlanStep objects with undo info
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    steps_data = []
    for i, cs in enumerate(completed_steps):
        # Find matching plan step for undo info
        undo_cmd = ""
        is_reversible = False
        if i < len(plan_steps):
            ps = plan_steps[i]
            if hasattr(ps, 'undo_command'):
                undo_cmd = ps.undo_command
                is_reversible = ps.is_reversible
            elif isinstance(ps, dict):
                undo_cmd = ps.get("undo_command", "")
                is_reversible = ps.get("is_reversible", False)

        steps_data.append({
            "step_number": cs.get("step_number", i + 1),
            "command": cs.get("command", ""),
            "return_code": cs.get("return_code", -1),
            "stdout": cs.get("stdout", "")[:500],
            "stderr": cs.get("stderr", "")[:500],
            "is_reversible": is_reversible,
            "undo_command": undo_cmd,
        })

    data = {
        "objective": objective,
        "steps": steps_data,
    }
    LAST_PLAN_FILE.write_text(json.dumps(data, indent=2))


def load_last_plan() -> Optional[dict]:
    """Load the last executed plan. Returns None if not available."""
    if not LAST_PLAN_FILE.exists():
        return None
    try:
        return json.loads(LAST_PLAN_FILE.read_text())
    except (json.JSONDecodeError, TypeError):
        return None


def get_undo_steps(last_plan: dict, max_steps: Optional[int] = None) -> list[dict]:
    """Get undo steps in REVERSE order from the last plan.

    Args:
        last_plan: The loaded last plan data
        max_steps: If set, only undo the last N steps

    Returns:
        List of dicts with 'original_command', 'undo_command', 'step_number', 'has_undo'
    """
    steps = last_plan.get("steps", [])
    # Only include successful steps (return_code == 0)
    successful = [s for s in steps if s.get("return_code", -1) == 0]
    # Reverse order
    successful.reverse()
    # Limit if requested
    if max_steps is not None:
        successful = successful[:max_steps]

    undo_steps = []
    for s in successful:
        undo_steps.append({
            "step_number": s.get("step_number", 0),
            "original_command": s.get("command", ""),
            "undo_command": s.get("undo_command", ""),
            "has_undo": bool(s.get("undo_command", "") and s.get("is_reversible", False)),
        })

    return undo_steps


def run_undo(
    ai_client=None,
    max_steps: Optional[int] = None,
    dry_run: bool = False,
) -> None:
    """Execute the undo flow.

    Args:
        ai_client: AIClient instance (needed for generating undo for non-reversible steps)
        max_steps: Only undo last N steps
        dry_run: Show what would be undone without executing
    """
    from .ui import (
        print_banner, print_command, print_success, print_error,
        print_warning, print_info, print_output_header, print_output_line,
        confirm_execution, show_spinner, print_done,
    )
    from .executor import execute_command
    from .safety import analyze_risk

    print_banner()

    last_plan = load_last_plan()
    if not last_plan:
        print_warning("No previous plan found. Run a plan first, then use 'zx undo'.")
        return

    print_info(f"  Objective was: {last_plan.get('objective', 'unknown')}")

    undo_steps = get_undo_steps(last_plan, max_steps)
    if not undo_steps:
        print_warning("No undoable steps found in the last plan.")
        return

    # For steps without undo commands, try AI generation
    if ai_client:
        for step in undo_steps:
            if not step["has_undo"] and step["original_command"]:
                with show_spinner("thinking"):
                    try:
                        text = ai_client._call_llm(
                            messages=[
                                {"role": "system", "content": "Return ONLY the exact shell command to undo the given command. If it cannot be undone, return 'CANNOT_UNDO'. No explanation, no markdown, just the command."},
                                {"role": "user", "content": f"Command: {step['original_command']}"},
                            ],
                            temperature=0.0,
                            max_tokens=200,
                            method_name="generate_undo",
                        )
                        undo_cmd = text.strip().strip('`').strip()
                        if undo_cmd and "CANNOT_UNDO" not in undo_cmd:
                            step["undo_command"] = undo_cmd
                            step["has_undo"] = True
                            step["ai_generated"] = True
                    except Exception:
                        pass

    # Display undo plan
    print_info("")
    if dry_run:
        print_info("  === DRY RUN — Undo Plan (nothing will be executed) ===")
    else:
        print_info("  === Undo Plan ===")
    print_info("")

    for step in undo_steps:
        if step["has_undo"]:
            ai_note = " (AI-generated)" if step.get("ai_generated") else ""
            print_info(f"  Undo step {step['step_number']}: {step['original_command']}")
            print_command(step["undo_command"], risk_label=analyze_risk(step["undo_command"]),
                          explanation=f"Reverses: {step['original_command']}{ai_note}")
        else:
            print_warning(f"  Step {step['step_number']} cannot be undone: {step['original_command']}")

    if dry_run:
        print_success("Dry run complete. No commands were executed.")
        return

    # Execute undo steps
    print_info("")
    results = []
    for step in undo_steps:
        if not step["has_undo"]:
            continue

        risk = analyze_risk(step["undo_command"])
        choice = confirm_execution(
            auto_approve=False,
            is_dangerous=(risk == "DANGEROUS"),
            is_supersafe=(risk == "SUPERSAFE"),
        )

        if choice == "n":
            print_warning(f"Skipped undo for step {step['step_number']}")
            continue
        if choice == "c":
            try:
                import pyperclip
                pyperclip.copy(step["undo_command"])
                print_success("Copied to clipboard.")
            except Exception:
                print_warning(f"Could not copy. Command: {step['undo_command']}")
            continue

        print_output_header()
        result = execute_command(
            step["undo_command"],
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
        )

        if result.success:
            print_success(f"Undid step {step['step_number']}")
        else:
            print_error(f"Undo failed for step {step['step_number']} (exit code {result.return_code})")

        results.append({
            "step_number": step["step_number"],
            "undo_command": step["undo_command"],
            "success": result.success,
        })

    # Summary
    ok_count = sum(1 for r in results if r["success"])
    total = len(results)
    if total > 0:
        lines = [f"Undone {ok_count}/{total} steps"]
        print_done("\n".join(lines))
    else:
        print_warning("No undo commands were executed.")
