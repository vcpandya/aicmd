"""Multi-step execution context and history tracking."""

from dataclasses import dataclass, field

MAX_OUTPUT_CHARS = 3000


@dataclass
class Step:
    number: int
    command: str
    stdout: str
    stderr: str
    return_code: int

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass
class ExecutionContext:
    objective: str
    steps: list[Step] = field(default_factory=list)
    max_steps: int = 20

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def is_at_limit(self) -> bool:
        return self.step_count >= self.max_steps

    def add_step(self, command: str, stdout: str, stderr: str, return_code: int) -> Step:
        step = Step(
            number=self.step_count + 1,
            command=command,
            stdout=_truncate(stdout, MAX_OUTPUT_CHARS),
            stderr=_truncate(stderr, MAX_OUTPUT_CHARS),
            return_code=return_code,
        )
        self.steps.append(step)
        return step

    def build_initial_message(self) -> str:
        return f"Objective: {self.objective}"

    def build_step_result_message(self, step: Step) -> str:
        parts = [
            f"Step {step.number} executed: {step.command}",
            f"Exit code: {step.return_code}",
        ]
        if step.stdout.strip():
            parts.append(f"Output:\n{step.stdout.strip()}")
        if step.stderr.strip():
            parts.append(f"Errors:\n{step.stderr.strip()}")
        parts.append(
            "What is the next command to run to fulfill the objective? "
            "If the objective is complete, respond with __DONE__"
        )
        return "\n".join(parts)

    def get_summary(self) -> str:
        lines = [f"[bold]Objective:[/] {self.objective}", ""]
        for step in self.steps:
            status = "[green]OK[/]" if step.success else "[red]FAIL[/]"
            lines.append(f"  {status} Step {step.number}: [dim]{step.command}[/]")
        return "\n".join(lines)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated, {len(text) - max_chars} chars omitted]"
