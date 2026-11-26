"""One button per print type."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, PrintType
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator
from .entity import TinyPressEntity
from .jobs import answer_job
from .services import async_print_type, async_story

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class TinyPressButtonDescription(ButtonEntityDescription):
    """Describes a print button."""

    print_type: PrintType | None  # None: answers or next chapter (by key)


BUTTONS: tuple[TinyPressButtonDescription, ...] = (
    TinyPressButtonDescription(key="maze", print_type=PrintType.MAZE),
    TinyPressButtonDescription(key="word_search", print_type=PrintType.WORD_SEARCH),
    TinyPressButtonDescription(key="math", print_type=PrintType.MATH),
    TinyPressButtonDescription(key="joke", print_type=PrintType.JOKE),
    TinyPressButtonDescription(key="kid_pack", print_type=PrintType.KID_PACK),
    TinyPressButtonDescription(key="kid_sudoku", print_type=PrintType.KID_SUDOKU),
    TinyPressButtonDescription(key="spelling", print_type=PrintType.SPELLING),
    TinyPressButtonDescription(
        key="spelling_search", print_type=PrintType.SPELLING_SEARCH
    ),
    TinyPressButtonDescription(key="sudoku", print_type=PrintType.SUDOKU),
    TinyPressButtonDescription(key="crossword", print_type=PrintType.CROSSWORD),
    TinyPressButtonDescription(key="cryptogram", print_type=PrintType.CRYPTOGRAM),
    TinyPressButtonDescription(key="puzzle_pack", print_type=PrintType.PUZZLE_PACK),
    TinyPressButtonDescription(key="bedtime_story", print_type=PrintType.STORY),
    TinyPressButtonDescription(key="next_chapter", print_type=None),
    TinyPressButtonDescription(key="morning_slip", print_type=PrintType.MORNING_SLIP),
    TinyPressButtonDescription(key="weather", print_type=PrintType.WEATHER),
    TinyPressButtonDescription(key="answers", print_type=None),
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Next chapter: the active kid's story in progress (for the card)."""
        if self.entity_description.key != "next_chapter":
            return None
        kid = self.coordinator.kid_profile()
        series = self.coordinator.store.series(kid.id) or {}
        return {
            "profile": kid.name,
            "story": series.get("title"),
            "chapter": series.get("chapter"),
            "choices": series.get("choices"),
        }

    async def async_press(self) -> None:
        """Print."""
        kind = self.entity_description.print_type
        if self.entity_description.key == "next_chapter":
            await async_story(self.hass, self.coordinator, continuing=True)
            return
        if kind is None:
            entry = self.coordinator.store.find_answer(None)
            if entry is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_answers",
                    translation_placeholders={"print_id": "-"},
                )
            await self.coordinator.async_print(partial(answer_job, entry))
            return
        await async_print_type(self.hass, self.coordinator, kind)
