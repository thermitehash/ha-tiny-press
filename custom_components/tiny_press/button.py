"""One button per print type."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import Difficulty
from .coordinator import PrintJob, TinyPressConfigEntry, TinyPressCoordinator
from .entity import TinyPressEntity
from .services import SETTING_MAZE_DIFFICULTY, maze_job, test_page_job

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class TinyPressButtonDescription(ButtonEntityDescription):
    """Describes a print button."""

    job: Callable[[TinyPressCoordinator], PrintJob]


def _maze(coordinator: TinyPressCoordinator) -> PrintJob:
    difficulty = coordinator.store.get_setting(SETTING_MAZE_DIFFICULTY, Difficulty.EASY)
    return maze_job(coordinator, Difficulty(difficulty))


BUTTONS: tuple[TinyPressButtonDescription, ...] = (
    TinyPressButtonDescription(key="maze", job=_maze),
    TinyPressButtonDescription(
        key="test_page", job=test_page_job, entity_category=EntityCategory.DIAGNOSTIC
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TinyPressConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the buttons."""
    async_add_entities(
        TinyPressButton(entry.runtime_data, description) for description in BUTTONS
    )


class TinyPressButton(TinyPressEntity, ButtonEntity):
    """Prints when pressed."""

    entity_description: TinyPressButtonDescription

    def __init__(
        self, coordinator: TinyPressCoordinator, description: TinyPressButtonDescription
    ) -> None:
        """Store the description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Print."""
        await self.coordinator.async_print(
            self.entity_description.job(self.coordinator)
        )
