"""Tiny Press: a household fun-printer on an Epson receipt printer."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .card import async_register_card, async_unregister_card
from .const import DOMAIN
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator
from .generators.data import preload
from .repairs import async_clear_offline_issue
from .services import async_setup_services
from .store import TinyPressStore

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once for all printers."""
    async_setup_services(hass)
    # Read the bundled word lists, jokes and facts once, off the event loop.
    await hass.async_add_executor_job(preload)
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TinyPressConfigEntry) -> bool:
    """Set up a printer."""
    store = TinyPressStore(hass, entry.entry_id)
    await store.async_load()
    coordinator = TinyPressCoordinator(hass, entry, store)
    # An offline printer is a normal state (it's switched off at night), so
    # setup never fails on it: the entities report it instead.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TinyPressConfigEntry) -> bool:
    """Unload a printer."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.store.async_flush()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: TinyPressConfigEntry) -> None:
    """Delete stored data and any open issue when a printer is removed."""
    await TinyPressStore(hass, entry.entry_id).async_remove()
    async_clear_offline_issue(hass, entry.entry_id)
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not remaining:
        await async_unregister_card(hass)
