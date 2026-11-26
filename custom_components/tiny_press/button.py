"""One button per print type."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PrintType
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator
from .entity import TinyPressEntity
from .services import async_print_type

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class TinyPressButtonDescription(ButtonEntityDescription):
    """Describes a print button."""

    print_type: PrintType


BUTTONS: tuple[TinyPressButtonDescription, ...] = (
    TinyPressButtonDescription(key="maze", print_type=PrintType.MAZE),
    TinyPressButtonDescription(key="word_search", print_type=PrintType.WORD_SEARCH),
    TinyPressButtonDescription(key="math", print_type=PrintType.MATH),
    TinyPressButtonDescription(key="joke", print_type=PrintType.JOKE),
    TinyPressButtonDescription(key="kid_pack", print_type=PrintType.KID_PACK),
    TinyPressButtonDescription(
        key="test_page",
        print_type=PrintType.TEST_PAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
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
    """Prints when pressed, for the profile chosen in the selects."""

    entity_description: TinyPressButtonDescription

    def __init__(
        self, coordinator: TinyPressCoordinator, description: TinyPressButtonDescription
    ) -> None:
        """Store the description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Print."""
        await async_print_type(
            self.hass, self.coordinator, self.entity_description.print_type
        )
