"""Paper, paper used and last print sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PaperState
from .coordinator import TinyPressConfigEntry
from .entity import TinyPressEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TinyPressConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            TinyPressPaper(coordinator, "paper"),
            TinyPressPaperUsed(coordinator, "paper_used"),
            TinyPressLastPrint(coordinator, "last_print"),
        ]
    )


class TinyPressPaper(TinyPressEntity, SensorEntity):
    """ok, near_end, out, cover_open or offline."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [s.value for s in PaperState]

    @property
    def native_value(self) -> str:
        """Collapsed paper state."""
        data = self.coordinator.data
        return (data.paper if data else PaperState.OFFLINE).value


class TinyPressPaperUsed(TinyPressEntity, SensorEntity):
    """Running total of millimetres printed (estimated from print length)."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float:
        """Total paper used, from the store."""
        return self.coordinator.store.paper_used_mm


class TinyPressLastPrint(TinyPressEntity, SensorEntity):
    """The type of the last print; details in attributes."""

    @property
    def native_value(self) -> str | None:
        """Last print type."""
        last = self.coordinator.store.last_print
        return last["type"] if last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """ID, time, length, profile and difficulty."""
        last = self.coordinator.store.last_print
        return {k: v for k, v in last.items() if k != "type"} if last else None
