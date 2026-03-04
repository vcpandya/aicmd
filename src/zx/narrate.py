"""Live Narration for zx — real-time AI commentary on command output."""

import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Callable, Optional


@dataclass
class NarrationConfig:
    """Configuration for the narration engine."""
    batch_size: int = 10        # Lines to accumulate before AI analysis
    batch_timeout: float = 3.0  # Seconds to wait before flushing a partial batch
    max_commentary: int = 50    # Max commentary entries to keep


@dataclass
class NarrationResult:
    """Result of a narrated command execution."""
    command: str
    return_code: int
    stdout: str
    stderr: str
    commentaries: list[dict] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.return_code == 0


def _get_shell_args() -> dict:
    """Get shell arguments for subprocess (same logic as executor.py)."""
    if platform.system() == "Windows":
        if os.environ.get("PSModulePath"):
            return {
                "shell": False,
                "executable": None,
                "args_prefix": ["powershell", "-NoProfile", "-Command"],
            }
        return {
            "shell": True,
            "executable": None,
            "args_prefix": [],
        }
    shell = os.environ.get("SHELL", "/bin/bash")
    return {
        "shell": True,
        "executable": shell,
        "args_prefix": [],
    }


def _stream_reader(pipe, queue: Queue, stream_name: str) -> None:
    """Read lines from a pipe and put them in the queue."""
    try:
        for line in iter(pipe.readline, ""):
            queue.put((stream_name, line))
    finally:
        pipe.close()
        queue.put((stream_name, None))


def execute_with_narration(
    command: str,
    ai_client,
    config: Optional[NarrationConfig] = None,
    on_stdout: Optional[Callable[[str], None]] = None,
    on_stderr: Optional[Callable[[str], None]] = None,
    on_commentary: Optional[Callable[[str], None]] = None,
    timeout: int = 600,
) -> NarrationResult:
    """Execute a command with real-time AI narration.

    Args:
        command: The command to execute
        ai_client: AIClient for generating commentary
        config: Narration configuration
        on_stdout: Callback for each stdout line
        on_stderr: Callback for each stderr line
        on_commentary: Callback for AI commentary
        timeout: Command timeout in seconds

    Returns:
        NarrationResult with output and commentaries
    """
    if config is None:
        config = NarrationConfig()

    shell_args = _get_shell_args()
    if shell_args["args_prefix"]:
        cmd = shell_args["args_prefix"] + [command]
        use_shell = False
    else:
        cmd = command
        use_shell = shell_args["shell"]

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    commentaries: list[dict] = []

    # Batch accumulator for AI analysis
    batch_buffer: list[str] = []
    batch_lock = threading.Lock()

    def _analyze_batch(lines: list[str], is_error: bool = False) -> None:
        """Send a batch of output lines to AI for analysis."""
        if not lines:
            return
        try:
            batch_text = "\n".join(lines)
            commentary = ai_client.narrate_output(
                command=command,
                output_batch=batch_text,
                is_error=is_error,
            )
            if commentary and commentary.strip():
                entry = {
                    "text": commentary,
                    "is_error": is_error,
                    "line_count": len(lines),
                    "timestamp": time.time(),
                }
                commentaries.append(entry)
                if on_commentary:
                    on_commentary(commentary)
        except Exception:
            pass  # Don't break the flow for narration failures

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            shell=use_shell,
            executable=shell_args.get("executable"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        q: Queue = Queue()
        t_out = threading.Thread(target=_stream_reader, args=(process.stdout, q, "stdout"), daemon=True)
        t_err = threading.Thread(target=_stream_reader, args=(process.stderr, q, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        finished_streams = 0
        last_batch_time = time.time()
        error_batch: list[str] = []

        while finished_streams < 2:
            try:
                stream_name, line = q.get(timeout=0.5)
            except Empty:
                # Check if batch timeout reached
                elapsed = time.time() - last_batch_time
                if elapsed >= config.batch_timeout and batch_buffer:
                    with batch_lock:
                        to_analyze = list(batch_buffer)
                        batch_buffer.clear()
                    # Analyze in background thread
                    threading.Thread(
                        target=_analyze_batch,
                        args=(to_analyze, False),
                        daemon=True,
                    ).start()
                    last_batch_time = time.time()
                continue

            if line is None:
                finished_streams += 1
                continue

            if stream_name == "stdout":
                stdout_lines.append(line)
                if on_stdout:
                    on_stdout(line.rstrip("\n"))
                with batch_lock:
                    batch_buffer.append(line.rstrip("\n"))
                    if len(batch_buffer) >= config.batch_size:
                        to_analyze = list(batch_buffer)
                        batch_buffer.clear()
                        threading.Thread(
                            target=_analyze_batch,
                            args=(to_analyze, False),
                            daemon=True,
                        ).start()
                        last_batch_time = time.time()
            else:
                stderr_lines.append(line)
                if on_stderr:
                    on_stderr(line.rstrip("\n"))
                error_batch.append(line.rstrip("\n"))
                # Analyze errors immediately (smaller batch)
                if len(error_batch) >= 3:
                    err_lines = list(error_batch)
                    error_batch.clear()
                    threading.Thread(
                        target=_analyze_batch,
                        args=(err_lines, True),
                        daemon=True,
                    ).start()

        # Flush remaining batches
        if batch_buffer:
            _analyze_batch(list(batch_buffer), False)
        if error_batch:
            _analyze_batch(list(error_batch), True)

        process.wait(timeout=timeout)
        t_out.join(timeout=2)
        t_err.join(timeout=2)

        # Brief pause to let background analysis threads finish
        time.sleep(0.5)

    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.wait(timeout=5)
        stderr_lines.append(f"[TIMEOUT]: Command timed out after {timeout}s\n")
    except KeyboardInterrupt:
        if process:
            process.terminate()
            process.wait(timeout=5)
        stderr_lines.append("[INTERRUPTED]: Command interrupted by user\n")
    except Exception as e:
        return NarrationResult(
            command=command,
            return_code=-1,
            stdout="",
            stderr=f"[EXECUTION ERROR]: {e}",
            commentaries=commentaries,
        )

    rc = -1
    if process is not None and process.returncode is not None:
        rc = process.returncode

    return NarrationResult(
        command=command,
        return_code=rc,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
        commentaries=commentaries,
    )


def run_narrate(
    command: str,
    ai_client=None,
) -> None:
    """Main narrate flow — execute a command with live AI commentary.

    Args:
        command: The command to execute
        ai_client: AIClient instance
    """
    from .ui import (
        print_banner, print_command, print_success, print_error,
        print_warning, print_info, print_output_header, print_output_line,
        confirm_execution, show_spinner, is_clean_mode,
    )
    from .safety import analyze_risk

    print_banner()

    risk = analyze_risk(command)
    print_command(command, risk_label=risk, explanation="Narrated execution")

    choice = confirm_execution(
        auto_approve=False,
        is_dangerous=(risk == "DANGEROUS"),
        is_supersafe=(risk == "SUPERSAFE"),
    )

    if choice != "y":
        if choice == "c":
            try:
                import pyperclip
                pyperclip.copy(command)
                print_success("Copied to clipboard.")
            except Exception:
                print_warning(f"Could not copy. Command: {command}")
        else:
            print_info("  Cancelled.")
        return

    print_output_header()

    def _on_commentary(text: str) -> None:
        if is_clean_mode():
            print(f"  AI: {text}")
        else:
            from .ui import console, S_AI, SYM_BRAIN
            console.print(f"  [{S_AI}]{SYM_BRAIN} {text}[/]")

    result = execute_with_narration(
        command,
        ai_client=ai_client,
        on_stdout=lambda line: print_output_line(line),
        on_stderr=lambda line: print_output_line(line, is_stderr=True),
        on_commentary=_on_commentary,
    )

    if result.success:
        print_success(f"Done (exit code {result.return_code})")
    else:
        print_error(f"Failed (exit code {result.return_code})")

    # Summary of AI observations
    if result.commentaries:
        print_info(f"\n  AI made {len(result.commentaries)} observation(s) during execution.")
        errors = [c for c in result.commentaries if c.get("is_error")]
        if errors:
            print_warning(f"  {len(errors)} error-related observation(s) were flagged.")
