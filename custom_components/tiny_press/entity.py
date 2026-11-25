"""Base entity for Tiny Press."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import TinyPressCoordinator


class TinyPressEntity(CoordinatorEntity[TinyPressCoordinator]):
    """One device per printer; entity names come from translations."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TinyPressCoordinator, key: str) -> None:
        """Set the unique ID, translation key and device."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=DEFAULT_MODEL,
            name="Tiny Press",
        )
        # Entries found by DHCP use the MAC as unique ID; registering it lets
        # DHCP follow the printer to a new IP address.
        if entry.unique_id and entry.unique_id.count(":") == 5:
            self._attr_device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, entry.unique_id)
            }
