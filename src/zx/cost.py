"""Cost tracking, budget enforcement, and usage reporting for zx."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import CONFIG_DIR

USAGE_FILE = CONFIG_DIR / "usage.json"


@dataclass
class UsageRecord:
    """A single AI call record."""
    timestamp: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    method: str  # "generate_command", "generate_plan", etc.


@dataclass
class CostTracker:
    """Tracks AI usage costs per session and monthly, with budget enforcement."""

    session_records: list[UsageRecord] = field(default_factory=list)

    def record(self, model: str, prompt_tokens: int, completion_tokens: int,
               cost_usd: float, method: str) -> None:
        """Record a single AI call."""
        rec = UsageRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
            method=method,
        )
        self.session_records.append(rec)
        self._append_to_monthly(rec)

    @property
    def session_cost(self) -> float:
        return sum(r.cost_usd for r in self.session_records)

    @property
    def session_tokens(self) -> int:
        return sum(r.total_tokens for r in self.session_records)

    @property
    def session_calls(self) -> int:
        return len(self.session_records)

    def monthly_cost(self, month_key: Optional[str] = None) -> float:
        """Get total cost for a month (default: current month) from disk."""
        if month_key is None:
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        data = self._load_usage_file()
        return data.get(month_key, {}).get("total_cost", 0.0)

    def monthly_tokens(self, month_key: Optional[str] = None) -> int:
        if month_key is None:
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        data = self._load_usage_file()
        return data.get(month_key, {}).get("total_tokens", 0)

    def monthly_calls(self, month_key: Optional[str] = None) -> int:
        if month_key is None:
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        data = self._load_usage_file()
        return data.get(month_key, {}).get("call_count", 0)

    def check_budget(self, config) -> tuple[bool, str]:
        """Check if budget allows another call.

        Returns (allowed, reason). Local models always allowed.
        """
        # Session budget
        if config.session_budget > 0 and self.session_cost >= config.session_budget:
            return False, f"Session budget ${config.session_budget:.2f} exceeded (spent ${self.session_cost:.4f})"

        # Monthly budget
        if config.monthly_budget > 0:
            mc = self.monthly_cost()
            if mc >= config.monthly_budget:
                return False, f"Monthly budget ${config.monthly_budget:.2f} exceeded (spent ${mc:.4f})"

        return True, ""

    def _is_local_model(self, model: str) -> bool:
        """Check if model is local (ollama, vllm) — these bypass budget checks."""
        return any(model.startswith(p) for p in ("ollama", "vllm", "local"))

    def _load_usage_file(self) -> dict:
        """Load the usage JSON file."""
        if not USAGE_FILE.exists():
            return {}
        try:
            return json.loads(USAGE_FILE.read_text())
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_usage_file(self, data: dict) -> None:
        """Save the usage JSON file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(data, indent=2))

    def _append_to_monthly(self, rec: UsageRecord) -> None:
        """Append a record to the monthly usage file."""
        data = self._load_usage_file()
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        day_key = now.strftime("%Y-%m-%d")

        if month_key not in data:
            data[month_key] = {
                "total_cost": 0.0,
                "total_tokens": 0,
                "call_count": 0,
                "by_model": {},
                "daily": {},
            }

        month = data[month_key]
        month["total_cost"] += rec.cost_usd
        month["total_tokens"] += rec.total_tokens
        month["call_count"] += 1

        # Per-model breakdown
        if rec.model not in month["by_model"]:
            month["by_model"][rec.model] = {"cost": 0.0, "tokens": 0, "calls": 0}
        month["by_model"][rec.model]["cost"] += rec.cost_usd
        month["by_model"][rec.model]["tokens"] += rec.total_tokens
        month["by_model"][rec.model]["calls"] += 1

        # Daily breakdown
        if day_key not in month["daily"]:
            month["daily"][day_key] = {"cost": 0.0, "tokens": 0, "calls": 0}
        month["daily"][day_key]["cost"] += rec.cost_usd
        month["daily"][day_key]["tokens"] += rec.total_tokens
        month["daily"][day_key]["calls"] += 1

        self._save_usage_file(data)

    def get_session_summary(self) -> str:
        """Format session cost summary for display."""
        cost = self.session_cost
        tokens = self.session_tokens
        calls = self.session_calls
        return f"Session: ${cost:.4f} | {tokens:,} tokens | {calls} call{'s' if calls != 1 else ''}"

    def get_monthly_summary(self, config=None, month_key: Optional[str] = None) -> str:
        """Format monthly cost summary."""
        if month_key is None:
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")

        # Single file read for all three values
        data = self._load_usage_file()
        month_data = data.get(month_key, {})
        cost = month_data.get("total_cost", 0.0)
        tokens = month_data.get("total_tokens", 0)
        calls = month_data.get("call_count", 0)

        # Month name
        try:
            dt = datetime.strptime(month_key, "%Y-%m")
            label = dt.strftime("%B %Y")
        except ValueError:
            label = month_key

        budget_str = ""
        if config and config.monthly_budget > 0:
            budget_str = f" / ${config.monthly_budget:.2f} budget"

        return f"{label}: ${cost:.4f}{budget_str} | {tokens:,} tokens | {calls} calls"

    def get_monthly_breakdown(self, month_key: Optional[str] = None) -> dict:
        """Get per-model and daily breakdown for a month."""
        if month_key is None:
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        data = self._load_usage_file()
        return data.get(month_key, {})

    def get_detailed_report(self) -> list[dict]:
        """Get per-call breakdown for the current session."""
        return [asdict(r) for r in self.session_records]

    def reset_month(self, month_key: Optional[str] = None) -> None:
        """Clear usage data for a given month."""
        if month_key is None:
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        data = self._load_usage_file()
        if month_key in data:
            del data[month_key]
            self._save_usage_file(data)
