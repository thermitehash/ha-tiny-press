"""Sensor history: numeric series, on/off (or text) timelines, summaries, tables.

Pure: built from the recorder's states or long-term statistics, which
``services.py`` fetches.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import itertools
import math
from typing import Any

MAX_SERIES = 3
MAX_TABLE_ROWS = 48
MAX_CHANGES = 20
UNAVAILABLE = {"unknown", "unavailable", "none", ""}


def to_float(value: Any) -> float | None:
    """Parse a state as a number, or None."""
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return None if math.isnan(number) else number


@dataclass(frozen=True, slots=True)
class Summary:
    """Numbers printed under a numeric graph."""

    now: float | None
    low: float | None
    high: float | None
    average: float | None
    change: float | None


@dataclass(frozen=True, slots=True)
class Series:
    """One entity's history over the period."""

    entity_id: str
    name: str
    unit: str = ""
    numeric: bool = True
    points: tuple[tuple[datetime, float], ...] = ()  # numeric samples
    lows: tuple[tuple[datetime, float], ...] = ()  # statistics: min per bucket
    highs: tuple[tuple[datetime, float], ...] = ()  # statistics: max per bucket
    segments: tuple[tuple[datetime, datetime, str], ...] = ()  # non-numeric

    @property
    def empty(self) -> bool:
        """True when there's nothing to draw."""
        return not self.points and not self.segments


def numeric_series(
    entity_id: str,
    name: str,
    unit: str,
    states: list[tuple[datetime, str]],
) -> Series:
    """Numeric samples (unavailable states dropped)."""
    points = tuple((t, v) for t, raw in states if (v := to_float(raw)) is not None)
    return Series(entity_id, name, unit, True, points)


def stats_series(
    entity_id: str, name: str, unit: str, rows: list[dict[str, Any]]
) -> Series:
    """Hourly/daily long-term statistics (mean, with min/max)."""
    points, lows, highs = [], [], []
    for row in rows:
        start = row.get("start")
        if isinstance(start, (int, float)):
            start = datetime.fromtimestamp(
                start / (1000 if start > 1e11 else 1)
            ).astimezone()
        if not isinstance(start, datetime):
            continue
        mean = to_float(row.get("mean"))
        if mean is None:
            continue
        points.append((start, mean))
        if (low := to_float(row.get("min"))) is not None:
            lows.append((start, low))
        if (high := to_float(row.get("max"))) is not None:
            highs.append((start, high))
    return Series(entity_id, name, unit, True, tuple(points), tuple(lows), tuple(highs))


def state_series(
    entity_id: str,
    name: str,
    states: list[tuple[datetime, str]],
    end: datetime,
    start: datetime | None = None,
) -> Series:
    """Timeline segments: each state until the next change, clipped to the period."""
    segments = []
    for i, (changed, state) in enumerate(states):
        stop = min(states[i + 1][0] if i + 1 < len(states) else end, end)
        begin = max(changed, start) if start else changed
        if stop > begin:
            segments.append((begin, stop, state))
    return Series(entity_id, name, "", False, segments=tuple(segments))


def summarize(series: Series) -> Summary:
    """Now, min, max, time-weighted average and change for a numeric series."""
    pts = series.points
    if not pts:
        return Summary(None, None, None, None, None)
    values = [v for _t, v in pts]
    low = min([*values, *(v for _t, v in series.lows)])
    high = max([*values, *(v for _t, v in series.highs)])
    if len(pts) > 1:
        total = 0.0
        weight = 0.0
        for (t1, v1), (t2, _v2) in itertools.pairwise(pts):
            span = (t2 - t1).total_seconds()
            total += v1 * span
            weight += span
        average = total / weight if weight else sum(values) / len(values)
    else:
        average = values[0]
    return Summary(values[-1], low, high, average, values[-1] - values[0])


def state_totals(series: Series) -> list[tuple[str, timedelta, int]]:
    """Per state: total time and how many times it started, longest first."""
    time_in: dict[str, timedelta] = defaultdict(timedelta)
    starts: dict[str, int] = defaultdict(int)
    previous = None
    for start, stop, state in series.segments:
        time_in[state] += stop - start
        if state != previous:
            starts[state] += 1
        previous = state
    return sorted(
        ((s, time_in[s], starts[s]) for s in time_in if s.lower() not in UNAVAILABLE),
        key=lambda row: row[1],
        reverse=True,
    )


@dataclass(frozen=True, slots=True)
class TableRow:
    """One hour or day: min/avg/max, or the state changes in it."""

    label: str
    low: float | None = None
    average: float | None = None
    high: float | None = None


def bucket_rows(series: Series, by_day: bool, to_local: Any) -> list[TableRow]:
    """Min/avg/max per local hour (or day) for a numeric series."""
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for t, v in series.points:
        local = to_local(t)
        key = local.replace(minute=0, second=0, microsecond=0)
        if by_day:
            key = key.replace(hour=0)
        buckets[key].append(v)
    rows = []
    for key in sorted(buckets):
        values = buckets[key]
        label = key.strftime("%a %-m/%-d") if by_day else key.strftime("%a %-I %p")
        rows.append(
            TableRow(label, min(values), sum(values) / len(values), max(values))
        )
    return rows[-MAX_TABLE_ROWS:]


def changes(series: Series, to_local: Any, by_day: bool) -> list[tuple[str, str]]:
    """(time, state) for each change of a non-numeric series, newest last."""
    out = []
    previous = None
    for start, _stop, state in series.segments:
        if state == previous:
            continue
        previous = state
        local = to_local(start)
        when = local.strftime("%a %-I:%M %p") if by_day else local.strftime("%-I:%M %p")
        out.append((when, state))
    return out[-MAX_CHANGES:]


@dataclass(frozen=True, slots=True)
class HistoryReport:
    """Everything a history print shows."""

    title: str
    start: datetime
    end: datetime
    series: tuple[Series, ...]
    style: str = "graph"  # graph | table | both
    tall: bool = False
    notes: tuple[str, ...] = field(default=())

    @property
    def by_day(self) -> bool:
        """Use daily buckets/labels for periods over two days."""
        return (self.end - self.start) > timedelta(days=2)
