"""Selects: active kid profile and maze difficulty."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SETTING_KID_PROFILE, SETTING_MAZE_DIFFICULTY, Difficulty
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator
from .entity import TinyPressEntity
from .profiles import KID, profiles_of

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TinyPressConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            TinyPressKidProfileSelect(coordinator, SETTING_KID_PROFILE),
            TinyPressDifficultySelect(coordinator, SETTING_MAZE_DIFFICULTY),
        ]
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


class TinyPressKidProfileSelect(TinyPressEntity, SelectEntity):
    """Which kid the buttons (and prints without a profile) are for.

    Options are the kid profiles' names; the profile ID is stored, so a
    rename in the options keeps the selection.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TinyPressCoordinator, key: str) -> None:
        """Build the options from the configured profiles."""
        super().__init__(coordinator, key)
        self._key = key
        self._profiles = profiles_of(coordinator.config_entry.options, KID)
        self._attr_options = [p.name for p in self._profiles]

    @property
    def current_option(self) -> str:
        """The active kid's name."""
        return self.coordinator.kid_profile().name

    async def async_select_option(self, option: str) -> None:
        """Store the chosen profile's ID."""
        profile = next(p for p in self._profiles if p.name == option)
        self.coordinator.store.set_setting(self._key, profile.id)
        self.async_write_ha_state()
