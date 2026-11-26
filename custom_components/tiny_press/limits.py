"""Kid-mode rate limiter: cooldown, prints per hour/day and a daily paper budget.

Enforced in the integration, so buttons, dashboard cards, voice phrases and
Siri all share the same limits. Only kid prints count. Parents bypass the
limits with ``ignore_limits: true`` on an action (or, if the option is on,
by being an admin user). Counts reset at local midnight.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import PrintType
from .store import TinyPressStore

CONF_LIMITS_ENABLED = "limits_enabled"
CONF_COOLDOWN_S = "limit_cooldown_s"
CONF_PER_HOUR = "limit_per_hour"
CONF_PER_DAY = "limit_per_day"
CONF_PAPER_MM_DAY = "limit_paper_mm_day"
CONF_ADMINS_SKIP = "limit_admins_skip"

DEFAULTS: dict[str, Any] = {
    CONF_LIMITS_ENABLED: False,
    CONF_COOLDOWN_S: 120,
    CONF_PER_HOUR: 4,
    CONF_PER_DAY: 10,
    CONF_PAPER_MM_DAY: 1500,
    CONF_ADMINS_SKIP: False,
}

KID_TYPES = frozenset(
    {
        PrintType.MAZE,
        PrintType.WORD_SEARCH,
        PrintType.MATH,
        PrintType.JOKE,
        PrintType.FACT,
        PrintType.KID_PACK,
    }
)

REASON_COOLDOWN = "cooldown"
REASON_HOUR = "hour"
REASON_DAY = "day"
REASON_PAPER = "paper"


@dataclass(frozen=True, slots=True)
class LimitStatus:
    """Where the limiter stands right now."""

    enabled: bool
    prints_today: int = 0
    prints_left_today: int | None = None
    paper_left_mm: float | None = None
    next_print_at: datetime | None = None  # None: a print is allowed now
    reason: str | None = None  # why the next print would be blocked

    def as_attributes(self) -> dict[str, Any]:
        """State attributes for the sensor (and the dashboard card)."""
        return {
            "enabled": self.enabled,
            "prints_today": self.prints_today,
            "paper_left_mm": self.paper_left_mm,
            "next_print_at": self.next_print_at.isoformat()
            if self.next_print_at
            else None,
            "blocked_reason": self.reason,
        }


class RateLimiter:
    """Reads its settings from the entry options and its counts from the store."""

    def __init__(self, store: TinyPressStore, options: dict[str, Any]) -> None:
        """Bind to the store and options."""
        self.store = store
        self.options = {
            **DEFAULTS,
            **{k: v for k, v in options.items() if k in DEFAULTS},
        }

    @property
    def enabled(self) -> bool:
        """True when kid-mode limits are on."""
        return bool(self.options[CONF_LIMITS_ENABLED])

    @property
    def admins_skip(self) -> bool:
        """True when admin users aren't limited."""
        return bool(self.options[CONF_ADMINS_SKIP])

    def _today(self, now: datetime) -> dict[str, Any]:
        day = dt_util.as_local(now).date().isoformat()
        data = self.store.data.setdefault("limits", {})
        if data.get("day") != day:
            data.clear()
            data.update({"day": day, "prints": [], "paper_mm": 0.0})
        return data

    def status(self, now: datetime | None = None) -> LimitStatus:
        """Compute what's allowed at ``now``."""
        if not self.enabled:
            return LimitStatus(enabled=False)
        now = now or dt_util.utcnow()
        data = self._today(now)
        prints = sorted(datetime.fromisoformat(p) for p in data["prints"])
        per_day = int(self.options[CONF_PER_DAY])
        per_hour = int(self.options[CONF_PER_HOUR])
        cooldown = timedelta(seconds=int(self.options[CONF_COOLDOWN_S]))
        paper_left = max(0.0, float(self.options[CONF_PAPER_MM_DAY]) - data["paper_mm"])
        left = max(0, per_day - len(prints))
        midnight = dt_util.start_of_local_day(dt_util.as_local(now)) + timedelta(days=1)
        waits: list[tuple[datetime, str]] = []
        if left == 0:
            waits.append((dt_util.as_utc(midnight), REASON_DAY))
        if paper_left <= 0:
            waits.append((dt_util.as_utc(midnight), REASON_PAPER))
        hour_ago = now - timedelta(hours=1)
        recent = [p for p in prints if p > hour_ago]
        if per_hour and len(recent) >= per_hour:
            waits.append((recent[-per_hour] + timedelta(hours=1), REASON_HOUR))
        if prints and prints[-1] + cooldown > now:
            waits.append((prints[-1] + cooldown, REASON_COOLDOWN))
        next_at, reason = max(waits) if waits else (None, None)
        return LimitStatus(True, len(prints), left, round(paper_left), next_at, reason)

    def record(self, length_mm: float, now: datetime | None = None) -> None:
        """Count a finished kid print."""
        if not self.enabled:
            return
        now = now or dt_util.utcnow()
        data = self._today(now)
        data["prints"].append(now.isoformat())
        data["paper_mm"] = round(data["paper_mm"] + length_mm, 1)
        self.store.save()
