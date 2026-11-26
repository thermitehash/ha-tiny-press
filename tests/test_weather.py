"""Weather print."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators.weather import (
    build_report,
    condition_label,
)
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

ATTRS = {
    "friendly_name": "Home",
    "temperature": 58.4,
    "apparent_temperature": 55,
    "humidity": 62,
    "wind_speed": 9,
    "wind_speed_unit": "mph",
    "temperature_unit": "°F",
}
CONDITIONS = [
    "sunny",
    "partlycloudy",
    "rainy",
    "lightning-rainy",
    "cloudy",
    "snowy",
    "fog",
    "windy",
    "clear-night",
    "pouring",
    "hail",
    "snowy-rainy",
]


def _daily(n: int = 12) -> list[dict[str, Any]]:
    start = datetime(2026, 11, 26, 12, tzinfo=UTC)
    return [
        {
            "datetime": (start + timedelta(days=i)).isoformat(),
            "condition": CONDITIONS[i % len(CONDITIONS)],
            "temperature": 60 + i,
            "templow": 40 + i,
            "precipitation_probability": (i * 10) % 100,
        }
        for i in range(n)
    ]


def test_report_caps_at_ten_days() -> None:
    report = build_report("Home", ATTRS, "sunny", _daily(12))
    assert len(report.days) == 10
    assert report.days[0].day == date(2026, 11, 26)
    assert (report.days[0].high, report.days[0].low) == (60, 40)
    assert report.temperature == 58.4 and report.temp_unit == "°F"


def test_twice_daily_rows_merge() -> None:
    rows = [
        {
            "datetime": "2026-11-26T12:00:00+00:00",
            "is_daytime": True,
            "condition": "sunny",
            "temperature": 61,
            "precipitation_probability": 10,
        },
        {
            "datetime": "2026-11-26T23:00:00+00:00",
            "is_daytime": False,
            "condition": "clear-night",
            "temperature": 41,
            "precipitation_probability": 30,
        },
    ]
    (day,) = build_report("Home", {}, None, rows).days
    assert (day.condition, day.high, day.low, day.precip_chance) == (
        "sunny",
        61,
        41,
        30,
    )


def test_labels_and_missing_values() -> None:
    assert condition_label("partlycloudy") == "Partly cloudy"
    assert condition_label(None) == "Unknown"
    assert condition_label("new-thing") == "New thing"
    report = build_report("X", {"temperature": "n/a"}, None, [{"condition": "sunny"}])
    assert report.temperature is None and report.days == ()


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_weather_page_width(width: int) -> None:
    footer = layout.Footer("Weather", "WX12", date(2026, 11, 26))
    for days in (_daily(10), []):
        report = build_report("Home", ATTRS, "partlycloudy", days)
        image, _ = layout.weather_page(width, report, footer).render()
        assert image.width == width
    for condition in [*CONDITIONS, "windy-variant", "exceptional", None]:
        assert layout.weather_icon(condition, 48).size == (48, 48)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_print_weather(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    hass.states.async_set("weather.home", "partlycloudy", ATTRS)
    hass.states.async_set("weather.cabin", "snowy", {**ATTRS, "friendly_name": "Cabin"})
    calls: list[str] = []

    async def forecasts(call: ServiceCall) -> dict[str, Any]:
        calls.append(call.data["type"])
        if call.data["type"] == "daily":
            return {call.data["entity_id"]: {"forecast": []}}  # no daily support
        return {call.data["entity_id"]: {"forecast": _daily(3)}}

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    await _setup(hass, config_entry, weather_entity="weather.home")
    response = await hass.services.async_call(
        DOMAIN, "print", {"type": "weather"}, blocking=True, return_response=True
    )
    assert calls == ["daily", "twice_daily"]
    assert response["type"] == "weather"
    assert response["condition"] == "partlycloudy"
    assert response["forecast_days"] == 3
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.tiny_press_weather"}, blocking=True
    )
    for _ in range(100):
        if len(printer.jobs) >= 2:
            break
        await asyncio.sleep(0.01)
    assert len(printer.jobs) == 2


async def test_weather_entity_choice(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    # No weather entity at all.
    with pytest.raises(ServiceValidationError, match="weather entity"):
        await hass.services.async_call(
            DOMAIN, "print", {"type": "weather"}, blocking=True
        )
    # Exactly one: used without configuring (and no forecast service: current only).
    hass.states.async_set("weather.home", "sunny", ATTRS)
    response = await hass.services.async_call(
        DOMAIN, "print", {"type": "weather"}, blocking=True, return_response=True
    )
    assert response["forecast_days"] == 0
    # Two and none chosen: ask to choose.
    hass.states.async_set("weather.cabin", "snowy", ATTRS)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "print", {"type": "weather"}, blocking=True
        )
