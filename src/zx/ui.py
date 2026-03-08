"""Rich terminal UI components for zx CLI — beautiful & witty edition."""

import os
import platform
import random
import sys
from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.align import Align
from rich import box


# ── Unicode detection ────────────────────────────────────────────────────────


def _supports_unicode() -> bool:
    try:
        encoding = sys.stdout.encoding or ""
        if encoding.lower().replace("-", "") in ("utf8", "utf16", "utf32"):
            return True
        "\u2713".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _supports_unicode()

# Symbols with ASCII fallbacks
SYM_BOLT = ">" if not _UNICODE else "\u26a1"
SYM_ARROW = "->" if not _UNICODE else "\u2192"
SYM_CHECK = "[+]" if not _UNICODE else "\u2714"
SYM_CROSS = "[x]" if not _UNICODE else "\u2718"
SYM_WARN = "[!]" if not _UNICODE else "\u26a0"
SYM_SHIELD = "(safe)" if not _UNICODE else "\U0001f6e1"
SYM_SKULL = "(DANGER)" if not _UNICODE else "\U0001f480"
SYM_BULB = "[i]" if not _UNICODE else "\U0001f4a1"
SYM_CLIP = "[C]" if not _UNICODE else "\U0001f4cb"
SYM_PIPE = "|" if not _UNICODE else "\u2502"
SYM_GEAR = "[*]" if not _UNICODE else "\u2699"
SYM_ROCKET = ">>" if not _UNICODE else "\U0001f680"
SYM_BRAIN = "[~]" if not _UNICODE else "\U0001f9e0"
SYM_SPARKLE = "*" if not _UNICODE else "\u2728"
SYM_FIRE = "(!)" if not _UNICODE else "\U0001f525"
SYM_PARTY = "(!)" if not _UNICODE else "\U0001f389"
SYM_EYES = "o.O" if not _UNICODE else "\U0001f440"
SYM_SCROLL = "[=]" if not _UNICODE else "\U0001f4dc"
SYM_LINK = "<>" if not _UNICODE else "\U0001f517"
SYM_MAG = "(o)" if not _UNICODE else "\U0001f50d"
SYM_PLAN = "[P]" if not _UNICODE else "\U0001f4cb"
SYM_UNDO = "<-" if not _UNICODE else "\u21a9"
SYM_LOCK = "[L]" if not _UNICODE else "\U0001f512"
SYM_ADAPT = "[~]" if not _UNICODE else "\U0001f504"

console = Console()

# ── Clean / Classic mode ────────────────────────────────────────────────────

_clean_mode: bool = False


def set_clean_mode(enabled: bool = True) -> None:
    """Enable or disable clean/classic mode (plain text, no Rich formatting)."""
    global _clean_mode
    _clean_mode = enabled


def is_clean_mode() -> bool:
    """Check if clean mode is active."""
    return _clean_mode


def print_info(message: str) -> None:
    """Print an informational message. Respects clean mode."""
    if _clean_mode:
        # Strip Rich markup for clean output
        import re
        clean = re.sub(r'\[/?[^\]]*\]', '', message)
        print(clean.strip())
    else:
        console.print(message)


@contextmanager
def _clean_spinner(label: str):
    """Context manager that prints 'label... done.' for clean mode."""
    print(f"{label}...", end=" ", flush=True)
    try:
        yield
    finally:
        print("done.")


# ── Style constants ──────────────────────────────────────────────────────────

S_OK = "bold green"
S_ERR = "bold red"
S_WARN = "bold yellow"
S_AI = "bold cyan"
S_STEP = "bold magenta"
S_DIM = "dim"
S_BRAND = "bold bright_cyan"
S_ACCENT = "bold bright_magenta"


# ── Witty spinner messages ───────────────────────────────────────────────────

THINKING_MESSAGES = [
    "Consulting the AI oracle...",
    "Teaching electrons to think...",
    "Translating human to computer...",
    "Asking the silicon brain nicely...",
    "Converting vibes into commands...",
    "Doing the AI magic thing...",
    "Crunching your intent through neurons...",
    "Decoding your wishes...",
    "Summoning the command spirits...",
    "Running it through the idea machine...",
    "Turning coffee into commands...",
    "Waking up the hamsters powering AI...",
    "Parsing your brainwaves...",
    "Interpreting your human language...",
    "Let me put on my thinking cap...",
    "hold on, brilliance loading...",
    "Spinning up the neural engines...",
    "Pinging the AI mothership...",
    "Channeling inner terminal guru...",
    "Processing at the speed of thought...",
]

ANALYZING_MESSAGES = [
    "Breaking down the master plan...",
    "Plotting the course of action...",
    "Mapping out the steps...",
    "Strategizing like a chess grandmaster...",
    "Drawing up the battle plan...",
    "Loading the multi-step playbook...",
    "Decomposing your grand vision...",
    "Orchestrating the symphony of commands...",
    "Planning world domination... err, your task...",
    "Laying out the domino chain...",
]

NEXT_STEP_MESSAGES = [
    "Figuring out what's next...",
    "Reading the tea leaves of stdout...",
    "Analyzing results, plotting next move...",
    "Processing output, brain go brrr...",
    "Evaluating... thinking... almost there...",
    "Inspecting the aftermath...",
    "Studying the output like a detective...",
    "Calculating the next brilliant move...",
    "Reviewing evidence, deciding strategy...",
    "Digesting the results...",
]

REFINING_MESSAGES = [
    "Tweaking the recipe...",
    "Fine-tuning with your feedback...",
    "Adjusting the knobs...",
    "Recalibrating based on your wisdom...",
    "Ok ok, let me try again...",
    "Taking notes, adjusting approach...",
    "Incorporating your refined taste...",
    "Alright, round two, better version...",
]

EXPLAIN_MESSAGES = [
    "Putting on my professor hat...",
    "Translating nerd to English...",
    "Decoding the arcane incantation...",
    "Let me break this down for you...",
    "Consulting the ancient scrolls...",
    "Reading the command like tea leaves...",
    "Time for a mini computer science lecture...",
    "Pulling apart the command molecule...",
]

SUCCESS_MESSAGES = [
    "Nailed it!",
    "Boom! Done.",
    "Like a boss.",
    "Clean execution.",
    "Smooth as butter.",
    "Mission accomplished.",
    "That's how it's done!",
    "Flawless victory.",
    "Chef's kiss.",
    "Another one bites the dust.",
]

FAIL_MESSAGES = [
    "Oof, that didn't go as planned.",
    "Houston, we have a problem.",
    "Well, that was unexpected.",
    "The universe had other plans.",
    "Plot twist!",
    "That's not ideal.",
    "Computer says no.",
    "Error: success not found.",
]

ABORT_MESSAGES = [
    "No worries, crisis averted.",
    "Standing down. Good call.",
    "Abort mission! (Smart choice)",
    "Safety first!",
    "Living to code another day.",
    "Dodged that one!",
    "Wise restraint, padawan.",
]

DONE_MESSAGES = [
    "All tasks complete! You're welcome.",
    "Mission accomplished! Take a bow.",
    "Everything's done! That was fun.",
    "Objective complete! High five!",
    "Finished! The terminal gods are pleased.",
    "All done! That was a team effort.",
    "Complete! Another day, another task crushed.",
    "Wrapped up! Time for coffee.",
]

PLANNING_MESSAGES = [
    "Crafting the master plan...",
    "Mapping out every step...",
    "Building the blueprint...",
    "Thinking three moves ahead...",
    "Assembling the game plan...",
    "Plotting the perfect sequence...",
    "Preparing the step-by-step guide...",
    "Connecting the dots...",
    "Engineering the solution...",
    "Architecting the approach...",
]

ADAPTING_MESSAGES = [
    "Hmm, let me rethink this...",
    "Adjusting the flight plan...",
    "Recalculating route...",
    "Plan B, coming right up...",
    "Adapting to the plot twist...",
    "Pivoting like a pro...",
    "Troubleshooting in progress...",
    "Revising the strategy...",
]

DANGEROUS_WARNINGS = [
    "Whoa there, cowboy! This one's spicy.",
    "This command means business. Serious business.",
    "Danger zone! Auto-approve disabled for safety.",
    "I wouldn't run this in my sleep. Let's be careful.",
    "Warning: this has 'I hope you have backups' energy.",
    "Red alert! This could cause some real damage.",
    "Proceeding with extreme caution recommended.",
    "This is the 'measure twice, cut once' kind of command.",
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _pick(messages: list[str]) -> str:
    return random.choice(messages)


def get_syntax_lexer() -> str:
    if platform.system() == "Windows":
        if os.environ.get("PSModulePath"):
            return "powershell"
        return "batch"
    return "bash"


def _get_shell_display() -> str:
    if platform.system() == "Windows":
        if os.environ.get("PSModulePath"):
            return "PowerShell"
        return "cmd"
    shell = os.environ.get("SHELL", "/bin/bash")
    return os.path.basename(shell)


# ── Banner ───────────────────────────────────────────────────────────────────

_LOGO_ASCII = r"""
     ____  __
    |_  / / /
     / / / /_
    /___/\__/
"""

_LOGO_LINES = [
    "[bold bright_cyan]     ____  __[/]",
    "[bold bright_cyan]    |_  / [/][bold bright_magenta]/ /[/]",
    "[bold bright_cyan]     / / [/][bold bright_magenta]/ /_ [/]",
    "[bold bright_cyan]    /___/[/][bold bright_magenta]\\__/ [/]",
]


def print_banner() -> None:
    if _clean_mode:
        return  # No banner in clean mode
    console.print()
    logo = "\n".join(_LOGO_LINES)
    info_line = f"[dim]{_get_shell_display()} {SYM_PIPE} {platform.system()} {SYM_PIPE} v0.1.0[/]"
    tagline = f"[{S_DIM}]speak human, run machine {SYM_SPARKLE}[/]"

    banner_content = f"{logo}\n{tagline}\n{info_line}"

    console.print(
        Panel(
            Align.center(banner_content),
            border_style="bright_cyan",
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
    )
    console.print()


# ── Command display ──────────────────────────────────────────────────────────


def print_command(
    command: str,
    step: Optional[int] = None,
    risk_label: Optional[str] = None,
    explanation: Optional[str] = None,
) -> None:
    if _clean_mode:
        prefix = f"  Step {step}: " if step is not None else "  "
        print(f"{prefix}Command: {command}")
        if risk_label:
            print(f"  Risk: {risk_label}")
        if explanation:
            print(f"  Info: {explanation}")
        return

    lexer = get_syntax_lexer()
    syntax = Syntax(command, lexer, theme="monokai", word_wrap=True, padding=1)

    if step is not None:
        title = f"[{S_ACCENT}] Step {step} [/] {SYM_PIPE} [{S_AI}]Generated Command[/]"
    else:
        title = f"[{S_AI}]{SYM_BOLT} Generated Command[/]"

    subtitle = None
    border = "cyan"
    if risk_label:
        if risk_label == "SUPERSAFE":
            subtitle = f"[bold green]{SYM_SHIELD}  SUPERSAFE -- trivial read-only[/]"
            border = "green"
        elif risk_label == "SAFE":
            subtitle = f"[bold green]{SYM_SHIELD}  SAFE -- read-only operation[/]"
            border = "green"
        elif risk_label == "MODERATE":
            subtitle = f"[bold yellow]{SYM_WARN}  CAUTION -- modifies files or state[/]"
            border = "yellow"
        elif risk_label == "DANGEROUS":
            subtitle = f"[bold red]{SYM_SKULL}  DANGER -- destructive / irreversible[/]"
            border = "red"

    console.print(Panel(
        syntax,
        title=title,
        subtitle=subtitle,
        border_style=border,
        box=box.HEAVY,
        padding=(0, 0),
    ))

    if explanation:
        console.print(f"  [{S_DIM}]{SYM_BULB} {explanation}[/]")


# ── Confirmation prompt ──────────────────────────────────────────────────────


def confirm_execution(
    auto_approve: bool = False,
    is_dangerous: bool = False,
    is_supersafe: bool = False,
    is_safe: bool = False,
    plan_approved: bool = False,
) -> str:
    """Returns: 'y' (execute), 'n' (skip), 'c' (copy), 'e' (edit/refine)"""
    if is_supersafe and not is_dangerous:
        if _clean_mode:
            print("  Auto-executing (supersafe)")
        else:
            console.print(f"  [{S_DIM}]{SYM_CHECK} Supersafe -- auto-executing[/]")
        return "y"
    if plan_approved and is_safe and not is_dangerous:
        if _clean_mode:
            print("  Auto-executing (safe, plan approved)")
        else:
            console.print(f"  [{S_DIM}]{SYM_CHECK} Safe -- auto-executing (plan approved)[/]")
        return "y"
    if auto_approve and not is_dangerous:
        if _clean_mode:
            print("  Auto-approved")
        else:
            console.print(f"  [{S_DIM}]{SYM_ROCKET} Auto-approved -- running immediately[/]")
        return "y"

    if _clean_mode:
        if is_dangerous:
            print("  WARNING: This command is DANGEROUS!")
        choice = input("  Run it? [Y]es / [n]o / [c]opy / [e]dit (Y): ").strip().lower() or "y"
        return choice if choice in ("y", "n", "c", "e") else "y"

    if is_dangerous:
        console.print()
        console.print(f"  [{S_ERR}]{_pick(DANGEROUS_WARNINGS)}[/]")

    console.print()
    choice = Prompt.ask(
        f"  [{S_AI}]{SYM_GEAR}[/] [bold]Run it?[/]  [dim]\\[Y]es  \\[n]o  \\[c]opy  \\[e]dit[/]",
        choices=["y", "n", "c", "e"],
        default="y",
        show_choices=False,
    )
    return choice.lower()


def prompt_refinement() -> str:
    while True:
        if _clean_mode:
            result = input("  How should I adjust? (e.g., 'use verbose mode', 'add timeout'): ").strip()
        else:
            console.print()
            result = Prompt.ask(f"  [{S_AI}]{SYM_BRAIN} How should I adjust? [dim](e.g., 'use verbose mode')[/]").strip()
        if result:
            return result


# ── Spinners with witty messages ─────────────────────────────────────────────


def show_spinner(message_type: str = "thinking"):
    """Return a spinner context manager with a witty random message.

    message_type: 'thinking', 'analyzing', 'next_step', 'refining', 'explaining'
    """
    clean_labels = {
        "thinking": "Thinking",
        "analyzing": "Analyzing",
        "next_step": "Analyzing output",
        "refining": "Refining",
        "explaining": "Explaining",
        "planning": "Planning",
        "adapting": "Adapting plan",
    }
    if _clean_mode:
        return _clean_spinner(clean_labels.get(message_type, "Processing"))

    pools = {
        "thinking": THINKING_MESSAGES,
        "analyzing": ANALYZING_MESSAGES,
        "next_step": NEXT_STEP_MESSAGES,
        "refining": REFINING_MESSAGES,
        "explaining": EXPLAIN_MESSAGES,
        "planning": PLANNING_MESSAGES,
        "adapting": ADAPTING_MESSAGES,
    }
    pool = pools.get(message_type, THINKING_MESSAGES)
    msg = _pick(pool)
    return console.status(f"  [{S_AI}]{SYM_BRAIN} {msg}[/]", spinner="dots")


# ── Output display ───────────────────────────────────────────────────────────


def print_output_header() -> None:
    if _clean_mode:
        print(f"  {'-' * 50}")
        return
    console.print(f"  [{S_DIM}]{'-' * 50}[/]")


def print_output_line(line: str, is_stderr: bool = False) -> None:
    if _clean_mode:
        prefix = "  ERR| " if is_stderr else "  | "
        print(f"{prefix}{line}")
        return
    # Escape Rich markup in command output to prevent injection
    safe_line = rich_escape(line)
    if is_stderr:
        console.print(f"  [dim red]{SYM_PIPE}[/] [red]{safe_line}[/]")
    else:
        console.print(f"  [dim]{SYM_PIPE}[/] {safe_line}")


# ── Status messages ──────────────────────────────────────────────────────────


def print_success(message: str, witty: bool = True) -> None:
    if _clean_mode:
        print(f"  OK: {message}")
        return
    console.print()
    extra = f"  [{S_DIM}]{_pick(SUCCESS_MESSAGES)}[/]" if witty else ""
    console.print(f"  [{S_OK}]{SYM_CHECK} {message}[/]{extra}")


def print_error(message: str, witty: bool = True) -> None:
    if _clean_mode:
        print(f"  ERROR: {message}")
        return
    console.print()
    extra = f"  [{S_DIM}]{_pick(FAIL_MESSAGES)}[/]" if witty else ""
    console.print(f"  [{S_ERR}]{SYM_CROSS} {message}[/]{extra}")


def print_warning(message: str) -> None:
    if _clean_mode:
        print(f"  WARNING: {message}")
        return
    console.print(f"  [{S_WARN}]{SYM_WARN} {message}[/]")


def print_abort() -> None:
    if _clean_mode:
        print("  Aborted.")
        return
    console.print()
    console.print(f"  [{S_WARN}]{_pick(ABORT_MESSAGES)}[/]")


# ── Step headers ─────────────────────────────────────────────────────────────


def print_step_header(step_number: int) -> None:
    if _clean_mode:
        print(f"\n--- Step {step_number} ---")
        return
    console.print()
    label = f" [{S_STEP}]{SYM_ROCKET} Step {step_number}[/] "
    console.print(Rule(label, style="bright_magenta"))
    console.print()


# ── Completion panel ─────────────────────────────────────────────────────────


def print_done(summary: str) -> None:
    if _clean_mode:
        import re
        clean = re.sub(r'\[/?[^\]]*\]', '', summary)
        print(f"\n  === Objective Complete ===\n{clean}\n")
        return
    console.print()
    done_msg = _pick(DONE_MESSAGES)
    full_content = f"{summary}\n\n[{S_DIM}]{done_msg}[/]"
    console.print(Panel(
        full_content,
        title=f"[{S_OK}]{SYM_PARTY} Objective Complete[/]",
        border_style="green",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    console.print()


# ── Explain display ──────────────────────────────────────────────────────────


def print_explanation(command: str, resp) -> None:
    """Print command explanation. resp can be an ExplainResponse or a string."""
    if _clean_mode:
        print(f"\n  Command: {command}")
        if hasattr(resp, "summary"):
            if resp.summary:
                print(f"  Summary: {resp.summary}")
            if resp.breakdown:
                print("  Breakdown:")
                for item in resp.breakdown:
                    print(f"    -> {item}")
            if resp.risks:
                print(f"  Risks: {resp.risks}")
        else:
            print(f"  {resp}")
        return

    lexer = get_syntax_lexer()
    syntax = Syntax(command, lexer, theme="monokai", word_wrap=True, padding=1)

    console.print(Panel(
        syntax,
        title=f"[{S_AI}]{SYM_MAG} Command Under the Microscope[/]",
        border_style="cyan",
        box=box.HEAVY,
        padding=(0, 0),
    ))
    console.print()

    # Handle structured ExplainResponse
    if hasattr(resp, "summary"):
        lines = []
        if resp.summary:
            lines.append(f"  [bold bright_white]{resp.summary}[/]")
            lines.append("")
        if resp.breakdown:
            lines.append(f"  [{S_AI}]Breakdown:[/]")
            for item in resp.breakdown:
                lines.append(f"    [{S_ACCENT}]{SYM_ARROW}[/] {item}")
            lines.append("")
        if resp.risks:
            lines.append(f"  [{S_WARN}]{SYM_WARN} Risks:[/] {resp.risks}")

        body = "\n".join(lines) if lines else str(resp)
    else:
        body = str(resp)

    console.print(Panel(
        body,
        title=f"[{S_OK}]{SYM_BULB} Explanation[/]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 1),
    ))


# ── History table ────────────────────────────────────────────────────────────


def print_history_table(entries: list[dict]) -> None:
    if not entries:
        if _clean_mode:
            print("  No history yet.")
        else:
            console.print(f"  [{S_DIM}]{SYM_SCROLL} No history yet. Run some commands first![/]")
        return

    if _clean_mode:
        print("\n  Command History:")
        print(f"  {'#':>4}  {'Status':6}  {'Prompt':<40}  {'Command':<50}  {'When':<19}")
        print(f"  {'-'*4}  {'-'*6}  {'-'*40}  {'-'*50}  {'-'*19}")
        for i, entry in enumerate(entries[-20:], 1):
            status = "OK" if entry.get("success", True) else "FAIL"
            print(f"  {i:>4}  {status:<6}  {entry.get('prompt', '')[:40]:<40}  {entry.get('command', '')[:50]:<50}  {entry.get('timestamp', '')[:19]}")
        print()
        return

    table = Table(
        title=f"[{S_AI}]{SYM_SCROLL} Command History[/]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        show_lines=True,
        padding=(0, 1),
        title_style="bold",
    )
    table.add_column("#", style="bold bright_magenta", width=4, justify="right")
    table.add_column("Prompt", style="white", max_width=40)
    table.add_column("Command", style="bright_green", max_width=50)
    table.add_column("When", style="dim", width=19)

    for i, entry in enumerate(entries[-20:], 1):
        status = f"[green]{SYM_CHECK}[/]" if entry.get("success", True) else f"[red]{SYM_CROSS}[/]"
        table.add_row(
            f"{status} {i}",
            entry.get("prompt", "")[:40],
            entry.get("command", "")[:50],
            entry.get("timestamp", "")[:19],
        )

    console.print()
    console.print(table)
    console.print()


# ── Plan display ────────────────────────────────────────────────────────


def _assign_phases(risk_labels: list[str]) -> list[str]:
    """Derive EXPLORE / EXECUTE / VERIFY phases from risk classifications."""
    n = len(risk_labels)
    if n == 0:
        return []
    # Find last MODERATE/DANGEROUS step
    last_modify = -1
    for i, r in enumerate(risk_labels):
        if r in ("MODERATE", "DANGEROUS"):
            last_modify = i
    phases = []
    for i, r in enumerate(risk_labels):
        if r in ("MODERATE", "DANGEROUS"):
            phases.append("EXECUTE")
        elif i > last_modify and last_modify >= 0:
            phases.append("VERIFY")
        else:
            phases.append("EXPLORE")
    return phases


def print_phase_header(phase: str) -> None:
    """Print a phase transition header (EXPLORE / EXECUTE / VERIFY)."""
    _icons = {"EXPLORE": SYM_MAG, "EXECUTE": SYM_GEAR, "VERIFY": SYM_CHECK}
    _colors = {"EXPLORE": "bright_cyan", "EXECUTE": "bright_yellow", "VERIFY": "bright_green"}
    icon = _icons.get(phase, SYM_GEAR)
    color = _colors.get(phase, "white")
    if _clean_mode:
        print(f"\n  === {icon} {phase} ===")
        return
    console.print()
    console.print(Rule(f" [{color}]{icon} {phase}[/] ", style=color))


def print_plan_table(plan, risk_labels: list[str]) -> None:
    """Display the execution plan as per-step cards grouped by phase."""
    phases = _assign_phases(risk_labels)

    if _clean_mode:
        print(f"\n  Execution Plan: {plan.summary}\n")
        prev_phase = None
        for step, risk, phase in zip(plan.steps, risk_labels, phases):
            if phase != prev_phase:
                print(f"\n  === {phase} ===")
                prev_phase = phase
            undo = " (Undo: Yes)" if step.is_reversible else ""
            print(f"  [{step.step_number}] {risk:<10}| {step.command}")
            print(f"      {step.explanation}{undo}")
        if plan.warnings:
            print(f"\n  WARNING: {plan.warnings}")
        print()
        return

    # Rich mode — summary panel
    console.print()
    console.print(Panel(
        f"[bold bright_white]{plan.summary}[/]",
        title=f"[{S_AI}]{SYM_PLAN} Execution Plan[/]",
        border_style="cyan",
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
    ))

    lexer = get_syntax_lexer()
    prev_phase = None

    for step, risk, phase in zip(plan.steps, risk_labels, phases):
        # Phase header on transition
        if phase != prev_phase:
            print_phase_header(phase)
            prev_phase = phase

        # Risk badge + border color
        if risk == "SUPERSAFE":
            badge = f"[bold green]{SYM_CHECK} AUTO[/]"
            border = "green"
        elif risk == "SAFE":
            badge = f"[bold green]{SYM_SHIELD} SAFE[/]"
            border = "green"
        elif risk == "MODERATE":
            badge = f"[bold yellow]{SYM_WARN} MODERATE[/]"
            border = "yellow"
        else:
            badge = f"[bold red]{SYM_SKULL} DANGER[/]"
            border = "red"

        undo_txt = f"  [green]{SYM_UNDO} Reversible[/]" if step.is_reversible else ""

        syntax = Syntax(step.command, lexer, theme="monokai", word_wrap=True, padding=1)
        console.print(Panel(
            syntax,
            title=f"[bold bright_magenta]Step {step.step_number}[/]",
            subtitle=f"[{S_DIM}]{SYM_BULB} {step.explanation}[/]{undo_txt}  {badge}",
            border_style=border,
            box=box.ROUNDED,
            padding=(0, 0),
        ))

    if plan.warnings:
        console.print(f"\n  [{S_WARN}]{SYM_WARN} {plan.warnings}[/]")

    console.print()


def confirm_plan(has_dangerous: bool) -> str:
    """Prompt user to approve the plan. Returns: 'y', 'n', or 'e' (edit)."""
    if _clean_mode:
        if has_dangerous:
            print("  WARNING: This plan includes DANGEROUS commands!")
        choice = input("  Approve this plan? [Y]es / [n]o / [e]dit (Y): ").strip().lower() or "y"
        return choice if choice in ("y", "n", "e") else "y"

    if has_dangerous:
        console.print(f"  [{S_ERR}]{SYM_WARN} This plan includes DANGEROUS commands. Review carefully.[/]")

    console.print()
    choice = Prompt.ask(
        f"  [{S_AI}]{SYM_GEAR}[/] [bold]Approve this plan?[/]  [dim]\\[Y]es  \\[n]o  \\[e]dit[/]",
        choices=["y", "n", "e"],
        default="y",
        show_choices=False,
    )
    return choice.lower()


def print_plan_progress(current_step: int, total_steps: int, command: str) -> None:
    """Show progress header during plan execution."""
    if _clean_mode:
        print(f"\n--- Step {current_step}/{total_steps} ---")
        return
    console.print()
    progress = f" [{S_STEP}]{SYM_ROCKET} Step {current_step}/{total_steps}[/] "
    console.print(Rule(progress, style="bright_magenta"))


def print_plan_adaptation(assessment: str, new_step_count: int) -> None:
    """Show that the plan has been adapted after a failure."""
    if _clean_mode:
        print(f"\n  Plan Adapted: {assessment}")
        print(f"  Revised plan has {new_step_count} remaining step(s).\n")
        return
    console.print()
    console.print(Panel(
        f"[bold bright_white]{assessment}[/]\n\n[{S_DIM}]Revised plan has {new_step_count} remaining step(s).[/]",
        title=f"[{S_WARN}]{SYM_ADAPT} Plan Adapted[/]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print()


# ── Misc ─────────────────────────────────────────────────────────────────────


def print_copied() -> None:
    if _clean_mode:
        print("  Copied to clipboard.")
        return
    console.print(f"  [{S_OK}]{SYM_CLIP} Copied to clipboard! Paste away.[/]")


def print_piped_context(char_count: int) -> None:
    if _clean_mode:
        print(f"  Received {char_count:,} chars from stdin")
        return
    console.print(f"  [{S_DIM}]{SYM_LINK} Received {char_count:,} chars from stdin -- feeding to AI as context[/]")


# ── Cost display ────────────────────────────────────────────────────────────


SYM_COST = "$" if not _UNICODE else "\U0001f4b0"


def print_cost_summary(summary: str) -> None:
    """Print cost summary after AI operations."""
    if _clean_mode:
        print(f"  Cost: {summary}")
    else:
        console.print(f"\n  [{S_DIM}]{SYM_COST} {summary}[/]")
