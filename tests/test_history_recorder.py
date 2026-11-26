"""Sensor history prints against a real recorder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.tiny_press.const import DOMAIN

from .fake_printer import FakePrinter

END = datetime(2026, 11, 26, 14, 0, tzinfo=UTC)
START = END - timedelta(hours=24)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations) -> None:
    """Start the recorder before Home Assistant (overrides the conftest fixture)."""


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _history(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print_history", data, blocking=True, return_response=True
    )


async def test_print_history_from_recorder(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(START)
    for i in range(12):
        hass.states.async_set(
            "sensor.bedroom",
            str(68 + i % 4),
            {"unit_of_measurement": "°F", "friendly_name": "Bedroom"},
        )
        hass.states.async_set(
            "binary_sensor.garage",
            "on" if i % 3 == 0 else "off",
            {"friendly_name": "Garage"},
        )
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=30))
    await async_wait_recording_done(hass)
    await _setup(hass, config_entry, limits_enabled=True, limit_cooldown_s=3600)
    res = await _history(
        hass,
        entity_id=["sensor.bedroom", "binary_sensor.garage", "sensor.missing"],
        hours=8,
        style="both",
    )
    assert res["type"] == "history"
    assert res["entities"] == [
        "sensor.bedroom",
        "binary_sensor.garage",
        "sensor.missing",
    ]
    assert res["empty"] == ["sensor.missing"]
    # Not a kid print: never limited.
    res = await _history(hass, entity_id="sensor.bedroom", days=5, tall=True, grid=True)
    assert res["empty"] == []
    explicit = await _history(
        hass,
        entity_id="sensor.bedroom",
        start=(START + timedelta(hours=1)).isoformat(),
        end=(START + timedelta(hours=4)).isoformat(),
        title="Bedroom",
    )
    assert explicit["start"].startswith("2026-11-25T15:00")
    with pytest.raises(ServiceValidationError, match="before the end"):
        await _history(
            hass,
            entity_id="sensor.bedroom",
            start=START.isoformat(),
            end=(START - timedelta(hours=1)).isoformat(),
        )
