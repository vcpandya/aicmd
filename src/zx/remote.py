"""Remote Execution for zx — SSH-based command execution on remote hosts."""

import json
import platform
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

REMOTES_FILE = CONFIG_DIR / "remotes.json"


def load_remotes() -> dict[str, dict]:
    """Load saved remote hosts.

    Returns:
        Dict of {name: {"host": "user@ip", "description": "...", ...}}
    """
    if not REMOTES_FILE.exists():
        return {}
    try:
        return json.loads(REMOTES_FILE.read_text())
    except (json.JSONDecodeError, TypeError):
        return {}


def save_remotes(remotes: dict[str, dict]) -> None:
    """Save remote hosts to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    REMOTES_FILE.write_text(json.dumps(remotes, indent=2))


def add_remote(name: str, host: str, description: str = "") -> None:
    """Add a remote host."""
    remotes = load_remotes()
    remotes[name] = {
        "host": host,
        "description": description,
    }
    save_remotes(remotes)


def remove_remote(name: str) -> bool:
    """Remove a remote host. Returns True if removed."""
    remotes = load_remotes()
    if name in remotes:
        del remotes[name]
        save_remotes(remotes)
        return True
    return False


def list_remotes() -> dict[str, dict]:
    """List all remote hosts."""
    return load_remotes()


def detect_remote_env(host: str, execute_fn=None) -> dict:
    """Detect the remote environment via SSH.

    Args:
        host: user@ip or hostname
        execute_fn: Command executor

    Returns:
        Dict with OS, shell, etc.
    """
    from .executor import execute_command as default_exec
    run = execute_fn or default_exec

    env = {"host": host}

    # Detect OS
    result = run(f'ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new {host} "uname -a 2>/dev/null || ver 2>nul"')
    if result.success and result.stdout.strip():
        env["os_info"] = result.stdout.strip().split("\n")[0]

    # Detect shell
    result = run(f'ssh -o ConnectTimeout=5 {host} "echo $SHELL"')
    if result.success and result.stdout.strip():
        env["shell"] = result.stdout.strip()

    # Detect working directory
    result = run(f'ssh -o ConnectTimeout=5 {host} "pwd"')
    if result.success and result.stdout.strip():
        env["cwd"] = result.stdout.strip()

    return env


def execute_remote(
    host: str,
    command: str,
    execute_fn=None,
    on_stdout=None,
    on_stderr=None,
) -> dict:
    """Execute a command on a remote host via SSH.

    Args:
        host: user@ip or hostname
        command: Command to execute remotely
        execute_fn: Command executor
        on_stdout: Stdout callback
        on_stderr: Stderr callback

    Returns:
        {"host": ..., "command": ..., "return_code": ..., "stdout": ..., "stderr": ...}
    """
    from .executor import execute_command as default_exec
    run = execute_fn or default_exec

    # Escape the command for SSH
    escaped = command.replace("'", "'\\''")
    ssh_cmd = f"ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new {host} '{escaped}'"

    result = run(ssh_cmd, on_stdout=on_stdout, on_stderr=on_stderr)

    return {
        "host": host,
        "command": command,
        "return_code": result.return_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": result.success,
    }


def execute_fanout(
    hosts: list[str],
    command: str,
    execute_fn=None,
) -> list[dict]:
    """Execute a command on multiple remote hosts.

    Args:
        hosts: List of user@ip strings
        command: Command to execute
        execute_fn: Command executor

    Returns:
        List of result dicts per host
    """
    import concurrent.futures

    from .executor import execute_command as default_exec
    run = execute_fn or default_exec

    results = []

    # Execute on all hosts in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(hosts), 10)) as pool:
        futures = {}
        for host in hosts:
            future = pool.submit(execute_remote, host, command, run)
            futures[future] = host

        for future in concurrent.futures.as_completed(futures):
            host = futures[future]
            try:
                result = future.result(timeout=60)
                results.append(result)
            except Exception as e:
                results.append({
                    "host": host,
                    "command": command,
                    "return_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "success": False,
                })

    return results


def run_remote(
    action: str = "",
    name: str = "",
    host: str = "",
    prompt: str = "",
    ai_client=None,
) -> None:
    """Main remote flow.

    Args:
        action: 'add', 'remove', 'list', 'run', or empty
        name: Remote name
        host: Host string (user@ip)
        prompt: Natural language prompt for remote execution
        ai_client: AIClient for command generation
    """
    from .ui import (
        print_banner, print_success, print_error, print_warning,
        print_info, print_command, print_output_header, print_output_line,
        confirm_execution, show_spinner,
    )
    from .safety import analyze_risk

    print_banner()

    if action == "add":
        if not name or not host:
            print_warning("Usage: zx remote add <name> <user@host>")
            return
        add_remote(name, host)
        print_success(f"Remote '{name}' added: {host}")
        # Test connection
        print_info("  Testing connection...")
        from .executor import execute_command
        result = execute_command(f'ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new {host} "echo OK"')
        if result.success and "OK" in result.stdout:
            print_success("Connection successful!")
        else:
            print_warning("Could not connect. Check SSH key setup.")

    elif action == "remove":
        if not name:
            print_warning("Usage: zx remote remove <name>")
            return
        if remove_remote(name):
            print_success(f"Remote '{name}' removed.")
        else:
            print_error(f"Remote '{name}' not found.")

    elif action == "list":
        remotes = list_remotes()
        if not remotes:
            print_warning("No remotes configured. Use 'zx remote add <name> <user@host>' to add one.")
            return
        print_info("\n  Configured Remotes:")
        print_info(f"  {'Name':<15} {'Host':<30} Description")
        print_info(f"  {'─'*15} {'─'*30} {'─'*30}")
        for rname, rdata in remotes.items():
            print_info(f"  {rname:<15} {rdata['host']:<30} {rdata.get('description', '')}")

    elif action == "run" and name and prompt:
        _execute_on_remote(name, prompt, ai_client)

    elif action == "fanout" and prompt:
        _execute_fanout(prompt, ai_client)

    else:
        print_warning("Usage:")
        print_info("  zx remote add <name> <user@host>  Add a remote host")
        print_info("  zx remote remove <name>           Remove a remote host")
        print_info("  zx remote list                    List configured remotes")
        print_info('  zx @<name> "prompt"               Execute on a remote host')
        print_info('  zx @all "prompt"                  Execute on all remotes')


def _execute_on_remote(name: str, prompt: str, ai_client=None) -> None:
    """Execute a natural language prompt on a specific remote host."""
    from .ui import (
        print_success, print_error, print_warning, print_info,
        print_command, print_output_header, print_output_line,
        confirm_execution, show_spinner,
    )
    from .safety import analyze_risk
    from .executor import execute_command

    remotes = load_remotes()
    if name not in remotes:
        print_error(f"Remote '{name}' not found. Use 'zx remote list' to see available remotes.")
        return

    remote = remotes[name]
    host = remote["host"]
    print_info(f"  Target: {name} ({host})")

    # Detect remote environment
    with show_spinner("analyzing"):
        remote_env = detect_remote_env(host, execute_command)

    env_summary = f"Remote: {remote_env.get('os_info', 'unknown OS')}, shell: {remote_env.get('shell', 'unknown')}"
    print_info(f"  Environment: {env_summary}")

    if not ai_client:
        print_error("AI client required for prompt-based remote execution.")
        return

    # Generate command for remote environment
    remote_prompt = f"{prompt}\n\nIMPORTANT: This will run on a REMOTE host.\n{env_summary}"
    with show_spinner("thinking"):
        resp = ai_client.generate_command(remote_prompt)

    if ai_client.is_done(resp):
        print_success("No command needed.")
        return

    cmd = resp.command
    risk = analyze_risk(cmd)
    print_command(cmd, risk_label=risk, explanation=f"[remote: {name}] {resp.explanation}")

    choice = confirm_execution(
        auto_approve=False,
        is_dangerous=(risk == "DANGEROUS"),
        is_supersafe=(risk == "SUPERSAFE"),
    )

    if choice != "y":
        print_info("  Cancelled.")
        return

    print_output_header()
    result = execute_remote(
        host, cmd, execute_command,
        on_stdout=lambda line: print_output_line(line),
        on_stderr=lambda line: print_output_line(line, is_stderr=True),
    )

    if result["success"]:
        print_success(f"Remote command completed on {name}")
    else:
        print_error(f"Remote command failed on {name} (exit code {result['return_code']})")


def _execute_fanout(prompt: str, ai_client=None) -> None:
    """Execute on all configured remotes."""
    from .ui import (
        print_success, print_error, print_warning, print_info,
        print_command, confirm_execution, show_spinner,
    )
    from .safety import analyze_risk
    from .executor import execute_command

    remotes = load_remotes()
    if not remotes:
        print_warning("No remotes configured.")
        return

    hosts = [r["host"] for r in remotes.values()]
    names = list(remotes.keys())
    print_info(f"  Fan-out to {len(hosts)} hosts: {', '.join(names)}")

    if not ai_client:
        print_error("AI client required.")
        return

    with show_spinner("thinking"):
        resp = ai_client.generate_command(prompt)

    if ai_client.is_done(resp):
        print_success("No command needed.")
        return

    cmd = resp.command
    risk = analyze_risk(cmd)
    print_command(cmd, risk_label=risk, explanation=f"[fan-out: {len(hosts)} hosts] {resp.explanation}")

    choice = confirm_execution(
        auto_approve=False,
        is_dangerous=(risk == "DANGEROUS"),
        is_supersafe=False,
    )

    if choice != "y":
        print_info("  Cancelled.")
        return

    with show_spinner("thinking"):
        results = execute_fanout(hosts, cmd, execute_command)

    print_info(f"\n  Results:")
    print_info(f"  {'Host':<30} {'Status':<10} Output")
    print_info(f"  {'─'*30} {'─'*10} {'─'*40}")
    for result in results:
        status = "OK" if result["success"] else "FAIL"
        output = (result["stdout"] or result["stderr"]).strip()[:60]
        print_info(f"  {result['host']:<30} {status:<10} {output}")

    ok = sum(1 for r in results if r["success"])
    print_success(f"Completed on {ok}/{len(results)} hosts.")
