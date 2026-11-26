"""Sensor history prints."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import math
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators import history as H
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

CHI = ZoneInfo("America/Chicago")
END = datetime(2026, 11, 26, 14, 0, tzinfo=UTC)
START = END - timedelta(hours=24)


def _local(dt: datetime) -> datetime:
    return dt.astimezone(CHI)


def _temps(start: datetime, n: int, step_min: int = 10) -> list[tuple[datetime, str]]:
    return [
        (
            start + timedelta(minutes=step_min * i),
            str(round(68 + 4 * math.sin(i / 20), 1)),
        )
        for i in range(n)
    ]


# ---- pure ------------------------------------------------------------------


def test_to_float_and_numeric_series() -> None:
    assert H.to_float("3.5") == 3.5
    assert H.to_float("unavailable") is None
    assert H.to_float(None) is None
    assert H.to_float("nan") is None
    series = H.numeric_series("s", "S", "°F", [(START, "1"), (END, "unknown")])
    assert series.points == ((START, 1.0),)


def test_summary_is_time_weighted() -> None:
    pts = [(START, "10"), (START + timedelta(hours=23), "20"), (END, "20")]
    summary = H.summarize(H.numeric_series("s", "S", "", pts))
    assert summary.low == 10 and summary.high == 20 and summary.now == 20
    assert summary.change == 10
    assert summary.average == pytest.approx((10 * 23 + 20 * 1) / 24)
    assert H.summarize(H.Series("s", "S")).now is None
    single = H.summarize(H.numeric_series("s", "S", "", [(START, "5")]))
    assert single.average == 5


def test_state_series_clips_and_totals() -> None:
    states = [
        (START - timedelta(hours=2), "closed"),
        (START + timedelta(hours=1), "open"),
        (START + timedelta(hours=2), "closed"),
        (START + timedelta(hours=10), "open"),
        (START + timedelta(hours=11), "unavailable"),
    ]
    series = H.state_series("d", "Door", states, END, START)
    assert series.segments[0][0] == START
    totals = {s: (t, n) for s, t, n in H.state_totals(series)}
    assert totals["open"] == (timedelta(hours=2), 2)
    assert totals["closed"] == (timedelta(hours=9), 2)
    assert "unavailable" not in totals
    changes = H.changes(series, _local, by_day=False)
    assert [c[1] for c in changes] == [
        "closed",
        "open",
        "closed",
        "open",
        "unavailable",
    ]


def test_bucket_rows_and_stats_series() -> None:
    series = H.numeric_series("s", "S", "", _temps(START, 145))
    hourly = H.bucket_rows(series, by_day=False, to_local=_local)
    assert 24 <= len(hourly) <= 25
    assert all(r.low <= r.average <= r.high for r in hourly)
    daily = H.bucket_rows(series, by_day=True, to_local=_local)
    assert len(daily) == 2
    stats = H.stats_series(
        "s",
        "S",
        "",
        [
            {"start": START.timestamp(), "mean": 5, "min": 1, "max": 9},
            {"start": START + timedelta(hours=1), "mean": 6, "min": None, "max": 8},
            {"start": "bad", "mean": 1},
            {"start": START.timestamp(), "mean": None},
        ],
    )
    assert [v for _t, v in stats.points] == [5, 6]
    assert H.summarize(stats).low == 1 and H.summarize(stats).high == 9


def test_nice_ticks_cover_range() -> None:
    for low, high in ((60.4, 72.6), (0, 0.3), (-5, 5), (100, 100)):
        ticks = layout._nice_ticks(low, high)
        assert ticks[0] <= low and ticks[-1] >= high and len(ticks) >= 2


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
@pytest.mark.parametrize("style", ["graph", "table", "both"])
@pytest.mark.parametrize("tall", [False, True])
def test_history_page_widths(width: int, style: str, tall: bool) -> None:
    footer = layout.Footer("History", "", date(2026, 11, 26), show_id=False)
    door = H.state_series(
        "d",
        "Door",
        [(START, "closed"), (START + timedelta(hours=3), "open")],
        END,
        START,
    )
    week_start = END - timedelta(days=7)
    for report in (
        H.HistoryReport(
            "Temps",
            START,
            END,
            (
                H.numeric_series("a", "A", "°F", _temps(START, 145)),
                H.numeric_series("b", "B", "°F", _temps(START, 145)),
                door,
                H.Series("c", "Missing"),
            ),
            style,
            tall,
        ),
        H.HistoryReport(
            "Week",
            week_start,
            END,
            (H.numeric_series("f", "Freezer", "°F", _temps(week_start, 168, 60)),),
            style,
            tall,
        ),
        H.HistoryReport(
            "One",
            START,
            END,
            (H.numeric_series("p", "Point", "W", [(START, "5")]),),
            style,
            tall,
        ),
    ):
        image, _ = layout.history_page(width, report, footer, _local).render(600 * 8)
        assert image.width == width


# ---- through Home Assistant with a real recorder ----------------------------


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _history(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print_history", data, blocking=True, return_response=True
    )


async def test_history_needs_recorder(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="Recorder"):
        await _history(hass, entity_id="sensor.x")
