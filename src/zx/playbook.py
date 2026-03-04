"""Playbook system for zx — incident response recipes with diagnostics and prevention."""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

PLAYBOOKS_DIR = CONFIG_DIR / "playbooks"
COMMUNITY_PLAYBOOKS_DIR = CONFIG_DIR / "community" / "playbooks"


@dataclass
class PlaybookStep:
    """A single step in a playbook (diagnostic or fix)."""
    command: str
    explanation: str
    risk: str = "SAFE"
    reversible: bool = False
    undo_command: str = ""
    what_to_look_for: str = ""


@dataclass
class Playbook:
    """An incident response playbook with diagnostics, fixes, and prevention."""
    name: str
    description: str
    category: str                               # "security", "debugging", "system"
    severity: str                               # "critical", "high", "medium", "low"
    symptoms: list[str] = field(default_factory=list)
    diagnostic_steps: list[PlaybookStep] = field(default_factory=list)
    fix_steps: list[PlaybookStep] = field(default_factory=list)
    prevention: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    platform: list[str] = field(default_factory=lambda: ["linux", "macos", "windows"])
    success_count: int = 0
    author: str = ""
    anonymous: bool = True
    created: str = ""
    version: str = "1.0.0"
    source: str = "local"                       # "local" or "community"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = "playbook"
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        data = dict(data)
        data.pop("type", None)
        diag = [PlaybookStep(**s) for s in data.pop("diagnostic_steps", [])]
        fix = [PlaybookStep(**s) for s in data.pop("fix_steps", [])]
        return cls(
            diagnostic_steps=diag,
            fix_steps=fix,
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )


def _playbook_path(name: str, community: bool = False) -> Path:
    """Get the file path for a playbook by name."""
    safe_name = re.sub(r'[^\w\-]', '_', name)
    base = COMMUNITY_PLAYBOOKS_DIR if community else PLAYBOOKS_DIR
    return base / f"{safe_name}.json"


def save_playbook(playbook: Playbook) -> Path:
    """Save a playbook to disk."""
    is_community = playbook.source == "community"
    base = COMMUNITY_PLAYBOOKS_DIR if is_community else PLAYBOOKS_DIR
    base.mkdir(parents=True, exist_ok=True)
    if not playbook.created:
        playbook.created = datetime.now(timezone.utc).isoformat()
    path = _playbook_path(playbook.name, community=is_community)
    path.write_text(json.dumps(playbook.to_dict(), indent=2))
    return path


def load_playbook(name: str) -> Optional[Playbook]:
    """Load a playbook by name. Checks local first, then community."""
    for community in (False, True):
        path = _playbook_path(name, community=community)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return Playbook.from_dict(data)
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
    return None


def list_playbooks(include_community: bool = True) -> list[Playbook]:
    """List all playbooks (local + community)."""
    playbooks = []
    dirs = [PLAYBOOKS_DIR]
    if include_community:
        dirs.append(COMMUNITY_PLAYBOOKS_DIR)

    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                playbooks.append(Playbook.from_dict(data))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
    return playbooks


def delete_playbook(name: str) -> bool:
    """Delete a playbook by name. Returns True if deleted."""
    path = _playbook_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def run_playbook(playbook: Playbook) -> bool:
    """Execute a playbook: show info, run diagnostics, run fixes, show prevention.

    Returns True if all fix steps succeeded.
    """
    from .ui import (
        print_banner, print_command, print_success, print_error,
        print_warning, print_info, print_output_header, print_output_line,
        confirm_execution, show_spinner, is_clean_mode,
    )
    from .executor import execute_command
    from .safety import analyze_risk

    print_banner()

    # Show playbook info
    severity_color = {"critical": "red", "high": "yellow", "medium": "cyan", "low": "green"}.get(playbook.severity, "white")
    print_info(f"  Playbook: {playbook.name}")
    print_info(f"  Severity: {playbook.severity.upper()}")
    print_info(f"  {playbook.description}")

    if playbook.symptoms:
        print_info("\n  Symptoms:")
        for s in playbook.symptoms:
            print_info(f"    - {s}")

    # Run diagnostic steps
    if playbook.diagnostic_steps:
        print_info(f"\n  Running {len(playbook.diagnostic_steps)} diagnostic step(s)...")
        for i, step in enumerate(playbook.diagnostic_steps, 1):
            print_info(f"\n  Diagnostic {i}: {step.explanation}")
            risk = analyze_risk(step.command)
            print_command(step.command, risk_label=risk, explanation=step.explanation)

            choice = confirm_execution(
                auto_approve=(risk in ("SUPERSAFE", "SAFE")),
                is_dangerous=(risk == "DANGEROUS"),
                is_supersafe=(risk == "SUPERSAFE"),
            )
            if choice != "y":
                continue

            print_output_header()
            result = execute_command(
                step.command,
                on_stdout=lambda line: print_output_line(line),
                on_stderr=lambda line: print_output_line(line, is_stderr=True),
            )

            if step.what_to_look_for:
                print_info(f"  Look for: {step.what_to_look_for}")

    # Ask before proceeding to fixes
    if playbook.fix_steps:
        print_info(f"\n  Ready to apply {len(playbook.fix_steps)} fix step(s).")
        try:
            proceed = input("  Proceed with fixes? [y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            proceed = "n"
        if proceed != "y":
            print_info("  Fix skipped.")
            return False

    # Run fix steps
    all_ok = True
    for i, step in enumerate(playbook.fix_steps, 1):
        print_info(f"\n  Fix {i}/{len(playbook.fix_steps)}: {step.explanation}")
        risk = analyze_risk(step.command)
        print_command(step.command, risk_label=risk, explanation=step.explanation)

        choice = confirm_execution(
            auto_approve=False,
            is_dangerous=(risk == "DANGEROUS"),
            is_supersafe=(risk == "SUPERSAFE"),
        )
        if choice != "y":
            all_ok = False
            break

        print_output_header()
        result = execute_command(
            step.command,
            on_stdout=lambda line: print_output_line(line),
            on_stderr=lambda line: print_output_line(line, is_stderr=True),
        )
        if not result.success:
            print_error(f"Fix step {i} failed (exit code {result.return_code})")
            all_ok = False
            break
        print_success(f"Fix step {i} done.")

    # Prevention tips
    if playbook.prevention:
        print_info("\n  Prevention tips:")
        for tip in playbook.prevention:
            print_info(f"    - {tip}")

    # Update success count
    if all_ok and playbook.fix_steps:
        playbook.success_count += 1
        save_playbook(playbook)
        print_success(f"Playbook completed successfully! (total: {playbook.success_count} runs)")

        # Auto-report success for community playbooks
        if playbook.source == "community":
            from .config import ZxConfig
            config = ZxConfig.load()
            if not config.community_opt_out:
                try:
                    from .community import report_success
                    report_success("playbook", playbook.name)
                except Exception:
                    pass  # Silent failure for reporting

    return all_ok


def create_playbook_from_diagnosis(
    diagnosis,
    error_output: str,
    failed_command: str,
    ai_client,
) -> Optional[Playbook]:
    """Create a playbook from a successful fix session using AI to generate metadata.

    Args:
        diagnosis: DiagnosisResponse from the fix
        error_output: The original error output
        failed_command: The command that failed
        ai_client: AIClient for generating metadata

    Returns:
        Playbook instance or None if generation failed
    """
    from .ui import print_info, print_warning, show_spinner

    try:
        with show_spinner("thinking"):
            meta = ai_client.generate_playbook_metadata(
                error_output=error_output,
                failed_command=failed_command,
                fix_command=diagnosis.fix_command,
                fix_explanation=diagnosis.explanation,
            )
    except Exception as e:
        print_warning(f"Could not generate playbook metadata: {e}")
        return None

    # Build diagnostic steps from AI suggestions
    diag_steps = []
    for i, cmd in enumerate(meta.diagnostic_commands):
        expl = meta.diagnostic_explanations[i] if i < len(meta.diagnostic_explanations) else ""
        look_for = meta.what_to_look_for[i] if i < len(meta.what_to_look_for) else ""
        diag_steps.append(PlaybookStep(
            command=cmd,
            explanation=expl,
            risk="SAFE",
            what_to_look_for=look_for,
        ))

    # Build fix step from the diagnosis
    fix_steps = [PlaybookStep(
        command=diagnosis.fix_command,
        explanation=diagnosis.explanation,
        risk="MODERATE",
    )]

    # Ask user for a name
    try:
        name = input("  Playbook name: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not name:
        return None

    try:
        desc = input("  Description: ").strip()
    except (EOFError, KeyboardInterrupt):
        desc = diagnosis.root_cause

    playbook = Playbook(
        name=name,
        description=desc or diagnosis.root_cause,
        category=meta.category,
        severity=meta.severity,
        symptoms=meta.symptoms,
        diagnostic_steps=diag_steps,
        fix_steps=fix_steps,
        prevention=meta.prevention_tips,
        tags=meta.tags,
    )

    save_playbook(playbook)
    print_info(f"  Playbook '{name}' saved with {len(diag_steps)} diagnostic + {len(fix_steps)} fix steps.")
    return playbook
