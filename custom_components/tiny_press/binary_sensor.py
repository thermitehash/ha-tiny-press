"""Online binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TinyPressConfigEntry
from .entity import TinyPressEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TinyPressConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the online sensor."""
    async_add_entities([TinyPressOnline(entry.runtime_data, "online")])


class TinyPressOnline(TinyPressEntity, BinarySensorEntity):
    """On when the printer answers status requests and is not offline."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return True when reachable and online."""
        data = self.coordinator.data
        return bool(data and data.online and data.status and data.status.online)
