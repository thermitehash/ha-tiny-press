"""Morning slip: today's date, weather, calendar events, to-dos and a bit of fun.

Pure: built from what Home Assistant returns for ``calendar.get_events`` and
``todo.get_items`` (any calendar or to-do integration works, Skylight
included once something exposes it). Manual printing only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from .jokes import Joke
from .sudoku import Sudoku
from .weather import WeatherReport

MAX_EVENTS = 10
MAX_TODOS_PER_LIST = 8
BOTTOM_OPTIONS = ("joke", "fact", "puzzle", "none")


@dataclass(frozen=True, slots=True)
class Event:
    """One calendar event, ready to print."""

    when: str  # "All day" or "8:15 AM"
    title: str
    all_day: bool
    sort_key: tuple[int, str]


@dataclass(frozen=True, slots=True)
class MorningSlip:
    """Everything on the slip."""

    day: date
    weather: WeatherReport | None
    events: tuple[Event, ...]
    more_events: int
    todos: tuple[tuple[str, tuple[str, ...]], ...] = ()  # (list name, items)
    joke: Joke | None = None
    puzzle: Sudoku | None = None
    calendars_set: bool = True
    notes: tuple[str, ...] = field(default=())


def _time_label(moment: datetime) -> str:
    return moment.strftime("%-I:%M %p")


def build_events(
    raw: dict[str, list[dict[str, Any]]],
    day: date,
    to_local: Any,
) -> tuple[tuple[Event, ...], int]:
    """Today's events from every calendar: all-day first, then by start time.

    ``raw`` maps calendar entity to its events. Duplicates (same title and
    start on two calendars) print once. Returns (events, how many more).
    """
    seen: set[tuple[str, str]] = set()
    events: list[Event] = []
    for items in raw.values():
        for item in items:
            title = " ".join(str(item.get("summary") or "").split())
            start = str(item.get("start") or "")
            if not title or not start:
                continue
            key = (title.lower(), start)
            if key in seen:
                continue
            seen.add(key)
            if "T" not in start:  # all-day: a plain date
                events.append(Event("All day", title, True, (0, title.lower())))
                continue
            moment = datetime.fromisoformat(start.replace("Z", "+00:00"))
            local = to_local(moment) if moment.tzinfo else moment
            if local.date() < day:  # started yesterday, still going
                events.append(Event("Ongoing", title, False, (1, "00:00")))
                continue
            stamp = local.time().strftime("%H:%M")
            events.append(Event(_time_label(local), title, False, (2, stamp)))
    events.sort(key=lambda e: e.sort_key)
    return tuple(events[:MAX_EVENTS]), max(0, len(events) - MAX_EVENTS)


def build_todos(
    raw: dict[str, tuple[str, list[dict[str, Any]]]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Unchecked items per list, in the order the lists were chosen."""
    out = []
    for name, items in raw.values():
        open_items = [
            " ".join(str(i.get("summary") or "").split())
            for i in items
            if i.get("status") != "completed"
        ]
        open_items = [i for i in open_items if i]
        if open_items:
            extra = len(open_items) - MAX_TODOS_PER_LIST
            shown = open_items[:MAX_TODOS_PER_LIST]
            if extra > 0:
                shown.append(f"+{extra} more")
            out.append((name, tuple(shown)))
    return tuple(out)


def day_bounds(day: date, tz: Any) -> tuple[datetime, datetime]:
    """Local midnight to the next midnight."""
    start = datetime.combine(day, time.min, tz)
    end = datetime.combine(day, time.max, tz)
    return start, end
