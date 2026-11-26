"""Selects: maze difficulty (profiles and sudoku arrive in later versions)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import Difficulty
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator
from .entity import TinyPressEntity
from .services import SETTING_MAZE_DIFFICULTY

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TinyPressConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the selects."""
    async_add_entities(
        [TinyPressDifficultySelect(entry.runtime_data, SETTING_MAZE_DIFFICULTY)]
    )


class TinyPressDifficultySelect(TinyPressEntity, SelectEntity):
    """Default difficulty for the button and for prints without one."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [d.value for d in Difficulty]

    def __init__(self, coordinator: TinyPressCoordinator, key: str) -> None:
        """Remember which setting this select stores."""
        super().__init__(coordinator, key)
        self._key = key

    @property
    def current_option(self) -> str:
        """Stored value (easy by default)."""
        return str(self.coordinator.store.get_setting(self._key, Difficulty.EASY.value))

    async def async_select_option(self, option: str) -> None:
        """Save the choice."""
        self.coordinator.store.set_setting(self._key, option)
        self.async_write_ha_state()
