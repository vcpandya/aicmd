"""Cross-platform command execution with real-time streaming."""

import os
import platform
import subprocess
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable, Optional


@dataclass
class CommandResult:
    command: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def output(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[STDERR]: {self.stderr}")
        parts.append(f"[EXIT CODE]: {self.return_code}")
        return "\n".join(parts)


def _get_shell_args() -> dict:
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
    try:
        for line in iter(pipe.readline, ""):
            queue.put((stream_name, line))
    finally:
        pipe.close()
        queue.put((stream_name, None))


def execute_command(
    command: str,
    on_stdout: Optional[Callable[[str], None]] = None,
    on_stderr: Optional[Callable[[str], None]] = None,
    timeout: Optional[int] = 300,
) -> CommandResult:
    shell_args = _get_shell_args()

    if shell_args["args_prefix"]:
        cmd = shell_args["args_prefix"] + [command]
        use_shell = False
    else:
        cmd = command
        use_shell = shell_args["shell"]

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
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
        while finished_streams < 2:
            try:
                stream_name, line = q.get(timeout=0.1)
            except Empty:
                continue

            if line is None:
                finished_streams += 1
                continue

            if stream_name == "stdout":
                stdout_lines.append(line)
                if on_stdout:
                    on_stdout(line.rstrip("\n"))
            else:
                stderr_lines.append(line)
                if on_stderr:
                    on_stderr(line.rstrip("\n"))

        # Wait for process and threads to fully complete
        process.wait(timeout=timeout)
        t_out.join(timeout=2)
        t_err.join(timeout=2)

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
        return CommandResult(
            command=command,
            return_code=-1,
            stdout="",
            stderr=f"[EXECUTION ERROR]: {e}",
        )

    rc = -1
    if process is not None and process.returncode is not None:
        rc = process.returncode

    return CommandResult(
        command=command,
        return_code=rc,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
