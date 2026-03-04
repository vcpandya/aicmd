"""Context Snapshots for zx — record and diff system state."""

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

SNAPSHOTS_DIR = CONFIG_DIR / "snapshots"


def take_snapshot(name: Optional[str] = None, execute_fn=None) -> dict:
    """Capture current system state as a snapshot.

    Args:
        name: Optional name for the snapshot (auto-generated if None)
        execute_fn: Command execution function (executor.execute_command)

    Returns:
        Snapshot dict
    """
    from .executor import execute_command as default_exec
    run = execute_fn or default_exec

    if not name:
        name = datetime.now().strftime("snap_%Y%m%d_%H%M%S")

    snapshot = {
        "name": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cwd": os.getcwd(),
        "platform": platform.system(),
    }

    # File tree (top level + one deep)
    snapshot["file_tree"] = _capture_file_tree()

    # Git status
    git_result = run("git status --porcelain 2>/dev/null" if platform.system() != "Windows" else "git status --porcelain 2>nul")
    if git_result.success:
        snapshot["git_status"] = git_result.stdout.strip()
        # Git branch
        branch_result = run("git rev-parse --abbrev-ref HEAD 2>/dev/null" if platform.system() != "Windows" else "git rev-parse --abbrev-ref HEAD 2>nul")
        if branch_result.success:
            snapshot["git_branch"] = branch_result.stdout.strip()
        # Git commit
        commit_result = run("git rev-parse --short HEAD 2>/dev/null" if platform.system() != "Windows" else "git rev-parse --short HEAD 2>nul")
        if commit_result.success:
            snapshot["git_commit"] = commit_result.stdout.strip()

    # Environment variables (filtered — no secrets)
    safe_env_keys = [
        "PATH", "HOME", "USER", "SHELL", "LANG", "TERM",
        "NODE_ENV", "PYTHON_PATH", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV",
        "GOPATH", "CARGO_HOME", "JAVA_HOME",
    ]
    snapshot["env"] = {k: os.environ.get(k, "") for k in safe_env_keys if os.environ.get(k)}

    # Installed packages (detect from project files)
    snapshot["packages"] = _capture_packages(run)

    # Disk space
    snapshot["disk"] = _capture_disk(run)

    return snapshot


def _capture_file_tree(max_depth: int = 2) -> list[str]:
    """Capture file tree up to max_depth."""
    cwd = Path.cwd()
    files = []
    try:
        for item in sorted(cwd.iterdir()):
            name = item.name
            if name.startswith(".") and name not in (".git", ".env", ".gitignore"):
                continue
            if item.is_dir():
                files.append(f"{name}/")
                if max_depth > 1:
                    try:
                        for sub in sorted(item.iterdir()):
                            sub_name = sub.name
                            if sub_name.startswith("."):
                                continue
                            suffix = "/" if sub.is_dir() else ""
                            files.append(f"  {sub_name}{suffix}")
                    except PermissionError:
                        files.append("  <permission denied>")
            else:
                size = item.stat().st_size
                files.append(f"{name} ({_human_size(size)})")
    except PermissionError:
        files.append("<permission denied>")
    return files[:200]  # Cap at 200 entries


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _capture_packages(run) -> dict:
    """Capture installed package info from project files."""
    packages = {}
    cwd = Path.cwd()

    # Python
    if (cwd / "requirements.txt").exists():
        try:
            packages["python_requirements"] = (cwd / "requirements.txt").read_text()[:2000]
        except Exception:
            pass
    if (cwd / "pyproject.toml").exists():
        result = run("pip list --format=json 2>/dev/null")
        if result.success and result.stdout.strip():
            try:
                pkgs = json.loads(result.stdout)
                packages["python_pip"] = [f"{p['name']}=={p['version']}" for p in pkgs[:50]]
            except (json.JSONDecodeError, KeyError):
                pass

    # Node
    if (cwd / "package.json").exists():
        try:
            pkg = json.loads((cwd / "package.json").read_text())
            packages["node_deps"] = pkg.get("dependencies", {})
            packages["node_dev_deps"] = pkg.get("devDependencies", {})
        except (json.JSONDecodeError, KeyError):
            pass

    # Rust
    if (cwd / "Cargo.toml").exists():
        try:
            packages["cargo_toml"] = (cwd / "Cargo.toml").read_text()[:2000]
        except Exception:
            pass

    return packages


def _capture_disk(run) -> str:
    if platform.system() != "Windows":
        result = run("df -h . 2>/dev/null | tail -1")
        if result.success:
            return result.stdout.strip()
    else:
        drive = os.getcwd()[:2]
        result = run(f'wmic logicaldisk where "DeviceID=\'{drive}\'" get FreeSpace,Size /format:value 2>nul')
        if result.success:
            return result.stdout.strip()
    return ""


def save_snapshot(snapshot: dict) -> Path:
    """Save a snapshot to disk."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    name = snapshot.get("name", "snapshot")
    path = SNAPSHOTS_DIR / f"{name}.json"
    path.write_text(json.dumps(snapshot, indent=2, default=str))
    return path


def load_snapshot(name: str) -> Optional[dict]:
    """Load a snapshot by name."""
    path = SNAPSHOTS_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, TypeError):
        return None


def list_snapshots() -> list[dict]:
    """List all saved snapshots (name + timestamp)."""
    if not SNAPSHOTS_DIR.exists():
        return []
    snapshots = []
    for f in sorted(SNAPSHOTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            snapshots.append({
                "name": data.get("name", f.stem),
                "timestamp": data.get("timestamp", ""),
                "cwd": data.get("cwd", ""),
            })
        except (json.JSONDecodeError, TypeError):
            continue
    return snapshots


def delete_snapshot(name: str) -> bool:
    """Delete a snapshot by name."""
    path = SNAPSHOTS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def diff_snapshots(old: dict, new: dict) -> list[str]:
    """Compare two snapshots and return human-readable diff lines."""
    diffs = []

    # File tree diff
    old_files = set(old.get("file_tree", []))
    new_files = set(new.get("file_tree", []))
    added = new_files - old_files
    removed = old_files - new_files
    if added:
        diffs.append("Files added:")
        for f in sorted(added):
            diffs.append(f"  + {f}")
    if removed:
        diffs.append("Files removed:")
        for f in sorted(removed):
            diffs.append(f"  - {f}")

    # Git diff
    old_branch = old.get("git_branch", "")
    new_branch = new.get("git_branch", "")
    if old_branch != new_branch:
        diffs.append(f"Git branch: {old_branch} -> {new_branch}")

    old_commit = old.get("git_commit", "")
    new_commit = new.get("git_commit", "")
    if old_commit != new_commit:
        diffs.append(f"Git commit: {old_commit} -> {new_commit}")

    old_status = old.get("git_status", "")
    new_status = new.get("git_status", "")
    if old_status != new_status:
        diffs.append(f"Git status changed:")
        if old_status:
            diffs.append(f"  Before: {old_status[:200]}")
        if new_status:
            diffs.append(f"  After:  {new_status[:200]}")

    # Env diff
    old_env = old.get("env", {})
    new_env = new.get("env", {})
    all_keys = set(list(old_env.keys()) + list(new_env.keys()))
    env_changes = []
    for k in sorted(all_keys):
        ov = old_env.get(k, "<unset>")
        nv = new_env.get(k, "<unset>")
        if ov != nv:
            env_changes.append(f"  {k}: {ov[:60]} -> {nv[:60]}")
    if env_changes:
        diffs.append("Environment changes:")
        diffs.extend(env_changes)

    # Disk diff
    old_disk = old.get("disk", "")
    new_disk = new.get("disk", "")
    if old_disk != new_disk:
        diffs.append(f"Disk: {old_disk} -> {new_disk}")

    if not diffs:
        diffs.append("No differences detected.")

    return diffs


def run_snapshot(
    action: str = "",
    name: str = "",
    compare_to: str = "",
) -> None:
    """Main snapshot flow.

    Args:
        action: 'take', 'list', 'diff', 'show', 'delete', or empty
        name: Snapshot name
        compare_to: Name of snapshot to compare against (for diff)
    """
    from .ui import print_banner, print_success, print_error, print_warning, print_info, show_spinner

    print_banner()

    if action == "take":
        with show_spinner("analyzing"):
            snap = take_snapshot(name=name or None)
        path = save_snapshot(snap)
        print_success(f"Snapshot '{snap['name']}' saved ({len(snap.get('file_tree', []))} files tracked)")
        print_info(f"  Path: {path}")

    elif action == "list":
        snaps = list_snapshots()
        if not snaps:
            print_warning("No snapshots saved. Use 'zx snapshot take' to create one.")
            return
        print_info("\n  Saved Snapshots:")
        print_info(f"  {'Name':<30} {'When':<25} Directory")
        print_info(f"  {'─'*30} {'─'*25} {'─'*40}")
        for s in snaps:
            print_info(f"  {s['name']:<30} {s['timestamp'][:19]:<25} {s['cwd']}")

    elif action == "diff":
        if not name:
            # Use the most recent snapshot
            snaps = list_snapshots()
            if not snaps:
                print_warning("No snapshots to compare against.")
                return
            name = snaps[-1]["name"]
            print_info(f"  Comparing against latest snapshot: {name}")

        old_snap = load_snapshot(name)
        if not old_snap:
            print_error(f"Snapshot '{name}' not found.")
            return

        with show_spinner("analyzing"):
            new_snap = take_snapshot(name="current_state")

        diffs = diff_snapshots(old_snap, new_snap)
        print_info(f"\n  Changes since '{name}':")
        for line in diffs:
            print_info(f"  {line}")

    elif action == "show":
        if not name:
            print_warning("Specify a snapshot name: zx snapshot show <name>")
            return
        snap = load_snapshot(name)
        if not snap:
            print_error(f"Snapshot '{name}' not found.")
            return
        print_info(f"\n  Snapshot: {snap['name']}")
        print_info(f"  Taken: {snap.get('timestamp', '')[:19]}")
        print_info(f"  Dir: {snap.get('cwd', '')}")
        if snap.get("git_branch"):
            print_info(f"  Git: {snap['git_branch']} @ {snap.get('git_commit', '?')}")
        print_info(f"  Files: {len(snap.get('file_tree', []))} entries")
        if snap.get("disk"):
            print_info(f"  Disk: {snap['disk']}")

    elif action == "delete":
        if not name:
            print_warning("Specify a snapshot name: zx snapshot delete <name>")
            return
        if delete_snapshot(name):
            print_success(f"Snapshot '{name}' deleted.")
        else:
            print_error(f"Snapshot '{name}' not found.")

    else:
        print_warning("Usage:")
        print_info("  zx snapshot take [name]    Take a snapshot of current state")
        print_info("  zx snapshot list           List saved snapshots")
        print_info("  zx snapshot diff [name]    Compare current state vs snapshot")
        print_info("  zx snapshot show <name>    Show snapshot details")
        print_info("  zx snapshot delete <name>  Delete a snapshot")
