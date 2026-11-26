"""Selects: kid and adult profiles, maze and sudoku difficulty, story length."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    SETTING_ADULT_PROFILE,
    SETTING_KID_PROFILE,
    SETTING_MAZE_DIFFICULTY,
    SETTING_STORY_LENGTH,
    SETTING_SUDOKU_DIFFICULTY,
    Difficulty,
)
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator
from .entity import TinyPressEntity
from .profiles import ADULT, KID, profiles_of

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
            TinyPressProfileSelect(coordinator, SETTING_KID_PROFILE, KID),
            TinyPressProfileSelect(coordinator, SETTING_ADULT_PROFILE, ADULT),
            TinyPressDifficultySelect(coordinator, SETTING_MAZE_DIFFICULTY),
            TinyPressDifficultySelect(coordinator, SETTING_SUDOKU_DIFFICULTY),
            TinyPressStoryLengthSelect(coordinator, SETTING_STORY_LENGTH),
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
        """Stored value (maze: easy; sudoku: the active adult's difficulty)."""
        default = Difficulty.EASY.value
        if self._key == SETTING_SUDOKU_DIFFICULTY:
            default = self.coordinator.adult_profile().difficulty
        return str(self.coordinator.store.get_setting(self._key, default))

    async def async_select_option(self, option: str) -> None:
        """Save the choice."""
        self.coordinator.store.set_setting(self._key, option)
        self.async_write_ha_state()


class TinyPressProfileSelect(TinyPressEntity, SelectEntity):
    """Which kid (or adult) the buttons and prints without a profile are for.

    Options are the profiles' names; the profile ID is stored, so a rename in
    the options keeps the selection.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TinyPressCoordinator, key: str, kind: str) -> None:
        """Build the options from the configured profiles."""
        super().__init__(coordinator, key)
        self._key = key
        self._kind = kind
        self._profiles = profiles_of(coordinator.config_entry.options, kind)
        self._attr_options = [p.name for p in self._profiles]

    @property
    def current_option(self) -> str:
        """The active profile's name."""
        if self._kind == KID:
            return self.coordinator.kid_profile().name
        return self.coordinator.adult_profile().name

    async def async_select_option(self, option: str) -> None:
        """Store the chosen profile's ID."""
        profile = next(p for p in self._profiles if p.name == option)
        self.coordinator.store.set_setting(self._key, profile.id)
        # Other entities show the active kid's state (the Next chapter button).
        self.coordinator.async_update_listeners()


class TinyPressStoryLengthSelect(TinyPressEntity, SelectEntity):
    """Short, medium or long bedtime stories (buttons and prints without one)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ["short", "medium", "long"]

    def __init__(self, coordinator: TinyPressCoordinator, key: str) -> None:
        """Remember which setting this select stores."""
        super().__init__(coordinator, key)
        self._key = key

    @property
    def current_option(self) -> str:
        """Stored length (medium by default)."""
        return str(self.coordinator.store.get_setting(self._key, "medium"))

    async def async_select_option(self, option: str) -> None:
        """Save the choice."""
        self.coordinator.store.set_setting(self._key, option)
        self.async_write_ha_state()
