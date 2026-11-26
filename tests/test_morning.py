"""Morning slip."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators import jokes, morning, sudoku
from custom_components.tiny_press.generators.data import load_json
from custom_components.tiny_press.generators.feeds import (
    WIKIQUOTE_API_URL,
    WIKIQUOTE_URL,
)
from custom_components.tiny_press.generators.weather import build_report
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

CHI = ZoneInfo("America/Chicago")
DAY = date(2026, 11, 26)


def _local(dt: datetime) -> datetime:
    return dt.astimezone(CHI)


def test_build_events_orders_and_dedupes() -> None:
    raw = {
        "calendar.family": [
            {"summary": "Swim lesson", "start": "2026-11-26T17:00:00-06:00"},
            {"summary": "Library books due", "start": "2026-11-26"},
            {"summary": "School drop-off", "start": "2026-11-26T14:15:00+00:00"},
            {"summary": "  ", "start": "2026-11-26"},
        ],
        "calendar.dad": [
            {"summary": "swim lesson", "start": "2026-11-26T17:00:00-06:00"},  # dup
            {"summary": "Road trip", "start": "2026-11-25T09:00:00-06:00"},  # ongoing
        ],
    }
    events, more = morning.build_events(raw, DAY, _local)
    assert [(e.when, e.title) for e in events] == [
        ("All day", "Library books due"),
        ("Ongoing", "Road trip"),
        ("8:15 AM", "School drop-off"),
        ("5:00 PM", "Swim lesson"),
    ]
    assert more == 0


def test_build_events_caps() -> None:
    raw = {
        "calendar.x": [
            {
                "summary": f"Event {i}",
                "start": f"2026-11-26T{8 + i % 10:02d}:00:00-06:00",
            }
            for i in range(14)
        ]
    }
    events, more = morning.build_events(raw, DAY, _local)
    assert len(events) == morning.MAX_EVENTS and more == 4


def test_build_todos() -> None:
    raw = {
        "todo.chores": (
            "Chores",
            [{"summary": "Feed fish", "status": "needs_action"}]
            + [{"summary": f"Task {i}", "status": "needs_action"} for i in range(10)]
            + [{"summary": "Done", "status": "completed"}],
        ),
        "todo.empty": ("Empty", [{"summary": "x", "status": "completed"}]),
    }
    ((name, items),) = morning.build_todos(raw)
    assert name == "Chores"
    assert items[0] == "Feed fish" and items[-1] == "+3 more"
    assert len(items) == morning.MAX_TODOS_PER_LIST + 1


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_morning_page_widths(width: int) -> None:
    footer = layout.Footer("Morning slip", "MS12", DAY)
    report = build_report(
        "Home",
        {"temperature": 41, "temperature_unit": "°F"},
        "partlycloudy",
        [
            {
                "datetime": "2026-11-26T15:00:00+00:00",
                "temperature": 52,
                "templow": 36,
                "precipitation_probability": 20,
            }
        ],
    )
    events, _ = morning.build_events(
        {"c": [{"summary": "A very long event title " * 4, "start": "2026-11-26"}]},
        DAY,
        _local,
    )
    variants = [
        morning.MorningSlip(
            DAY, report, events, 2, (("Chores", ("Feed fish",)),), jokes.pick("joke", 1)
        ),
        morning.MorningSlip(DAY, None, (), 0, joke=jokes.pick("fact", 1)),
        morning.MorningSlip(
            DAY, None, (), 0, puzzle=sudoku.generate(6, "easy", 1), calendars_set=False
        ),
        morning.MorningSlip(DAY, None, (), 0, quote=morning.pick_quote(1)),
        morning.MorningSlip(DAY, None, (), 0, word=morning.pick_word(1)),
        morning.MorningSlip(
            DAY, None, (), 0, word=morning.Word("terse", "adjective", "brief")
        ),
    ]
    for slip in variants:
        assert layout.morning_page(width, slip, footer).render()[0].width == width


def _services(hass: HomeAssistant, calls: list[str]) -> None:
    async def get_events(call: ServiceCall) -> dict[str, Any]:
        calls.append("calendar")
        assert call.data["start_date_time"] < call.data["end_date_time"]
        return {
            "calendar.family": {
                "events": [
                    {"summary": "Swim lesson", "start": "2026-11-26T17:00:00-06:00"},
                    {"summary": "Library day", "start": "2026-11-26"},
                ]
            }
        }

    async def get_items(call: ServiceCall) -> dict[str, Any]:
        calls.append("todo")
        return {
            call.data["entity_id"]: {
                "items": [{"summary": "Pack swim bag", "status": "needs_action"}]
            }
        }

    async def forecasts(call: ServiceCall) -> dict[str, Any]:
        return {
            call.data["entity_id"]: {
                "forecast": [
                    {
                        "datetime": "2026-11-26T15:00:00+00:00",
                        "condition": "sunny",
                        "temperature": 52,
                        "templow": 36,
                    }
                ]
            }
        }

    for domain, name, fn in (
        ("calendar", "get_events", get_events),
        ("todo", "get_items", get_items),
        ("weather", "get_forecasts", forecasts),
    ):
        hass.services.async_register(
            domain, name, fn, supports_response=SupportsResponse.ONLY
        )


def test_vocab_data() -> None:
    items = load_json("vocab.json")
    assert len(items) >= 150
    assert len({i["word"] for i in items}) == len(items)
    for item in items:
        assert item["pos"] in ("noun", "verb", "adjective")
        assert item["definition"] and len(item["definition"]) < 150
        assert item["word"] in item.get("example", item["word"]).lower()


def test_pick_quote_and_word() -> None:
    assert morning.pick_word(5) == morning.pick_word(5)
    assert morning.pick_quote(5) == morning.pick_quote(5)
    count = len(load_json("vocab.json"))
    recent = list(range(count // 2))
    for seed in range(50):
        assert morning.pick_word(seed, recent).index not in recent
    quotes = len(load_json("quotes.json"))
    everything = list(range(quotes))  # more than the list: still picks
    assert morning.pick_quote(1, everything).index is not None
    assert morning.pick_quote(1, everything).index not in everything[: quotes // 2]


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _slip(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print_morning_slip", data, blocking=True, return_response=True
    )


async def test_morning_slip_full(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    await hass.config.async_set_time_zone("America/Chicago")
    freezer.move_to(datetime(2026, 11, 26, 13, 0, tzinfo=UTC))
    hass.states.async_set(
        "weather.home", "sunny", {"temperature": 41, "temperature_unit": "°F"}
    )
    hass.states.async_set("calendar.family", "off", {"friendly_name": "Family"})
    hass.states.async_set("todo.chores", "1", {"friendly_name": "Chores"})
    calls: list[str] = []
    _services(hass, calls)
    await _setup(
        hass,
        config_entry,
        calendar_entities=["calendar.family", "calendar.gone"],
        todo_entities=["todo.chores"],
        morning_bottom="puzzle",
        limits_enabled=True,
        limit_cooldown_s=3600,
    )
    res = await _slip(hass)
    assert res["type"] == "morning_slip"
    assert res["events"] == 2 and res["todos"] == 1 and res["weather"] == "sunny"
    assert calls == ["calendar", "todo"]
    store = config_entry.runtime_data.store
    assert store.history[0]["type"] == "sudoku"
    assert store.history[0]["answer"]["size"] == 6

    # Never counts toward kid limits (cooldown is an hour), any number of times.
    await _slip(hass)
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.tiny_press_morning_slip"},
        blocking=True,
    )
    # From a kid-mode card: once a day.
    await _slip(hass, kid_mode=True)
    with pytest.raises(ServiceValidationError, match="already been printed"):
        await _slip(hass, kid_mode=True)
    freezer.tick(timedelta(days=1))
    await _slip(hass, kid_mode=True)


@pytest.mark.parametrize("bottom", ["joke", "fact", "quote", "word", "none"])
async def test_morning_slip_minimal(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
    bottom: str,
) -> None:
    aioclient_mock.get(WIKIQUOTE_API_URL, status=429)  # live quote fails: bundled
    aioclient_mock.get(WIKIQUOTE_URL, status=503)
    await _setup(hass, config_entry, morning_bottom=bottom)
    res = await _slip(hass)
    assert res["events"] == 0 and res["weather"] is None and res["todos"] == 0
    store = config_entry.runtime_data.store
    if bottom == "none":
        assert store.recent("joke") == [] and store.recent("fact") == []
    else:
        assert len(store.recent(bottom)) == 1
    with pytest.raises(ServiceValidationError, match="can't be previewed"):
        await hass.services.async_call(
            DOMAIN,
            "preview",
            {"type": "morning_slip"},
            blocking=True,
            return_response=True,
        )
    via_print = await hass.services.async_call(
        DOMAIN, "print", {"type": "morning_slip"}, blocking=True, return_response=True
    )
    assert via_print["type"] == "morning_slip"


async def test_calendar_errors_are_quiet(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    from homeassistant.exceptions import HomeAssistantError

    async def broken(call: ServiceCall) -> dict[str, Any]:
        raise HomeAssistantError("down")

    hass.services.async_register(
        "calendar", "get_events", broken, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        "todo", "get_items", broken, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("calendar.family", "off")
    hass.states.async_set("todo.chores", "1")
    await _setup(
        hass,
        config_entry,
        calendar_entities=["calendar.family"],
        todo_entities=["todo.chores"],
    )
    res = await _slip(hass)
    assert res["events"] == 0 and res["todos"] == 0
