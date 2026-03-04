"""Persistent command history and caching."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HISTORY_FILE = Path.home() / ".zx" / "history.json"
MAX_HISTORY = 500


def _load_entries() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _save_entries(entries: list[dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last MAX_HISTORY entries
    entries = entries[-MAX_HISTORY:]
    HISTORY_FILE.write_text(json.dumps(entries, indent=2))
    try:
        HISTORY_FILE.chmod(0o600)
    except OSError:
        pass


def add_entry(prompt: str, command: str, shell: str = "", success: bool = True) -> None:
    entries = _load_entries()
    entries.append({
        "prompt": prompt,
        "command": command,
        "shell": shell,
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_entries(entries)


def get_entries() -> list[dict]:
    return _load_entries()


def find_cached(prompt: str) -> Optional[str]:
    """Find an exact match for a prompt in history. Returns the command or None."""
    entries = _load_entries()
    prompt_lower = prompt.strip().lower()
    for entry in reversed(entries):
        if entry.get("prompt", "").strip().lower() == prompt_lower and entry.get("success", False):
            return entry.get("command")
    return None


def clear_history() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
