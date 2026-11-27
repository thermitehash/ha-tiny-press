"""Write spelling-crossword clues ahead of time.

Asking the AI for clues takes a while, so instead of making a kid wait at
the printer, Tiny Press asks whenever a kid's spelling to-do list changes
(and once at startup). Only words without a clue yet are sent. Nothing
happens without an AI task.
"""

from __future__ import annotations

import logging

from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from . import jobs
from .coordinator import TinyPressCoordinator
from .profiles import KID, profiles_of
from .services import async_spelling_clues, async_todo_words

_LOGGER = logging.getLogger(__name__)

SETTLE_S = 10.0  # wait for a burst of edits to finish before asking
WAIT_S = 90.0  # in the background there's no one waiting: allow a slow AI


class SpellingWatcher:
    """Keeps AI clues ready for every kid's spelling list."""

    def __init__(self, hass: HomeAssistant, coordinator: TinyPressCoordinator) -> None:
        """Bind to the printer."""
        self.hass = hass
        self.coordinator = coordinator
        self._unsubs: list[CALLBACK_TYPE] = []
        self._pending: dict[str, CALLBACK_TYPE] = {}

    def _kids(self):
        options = dict(self.coordinator.config_entry.options)
        return [k for k in profiles_of(options, KID) if k.spelling_todo]

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Watch the lists; returns the stop function."""
        if not self.coordinator.ai_task_entity:
            return self.async_stop
        kids = self._kids()
        lists = sorted({k.spelling_todo for k in kids})
        if lists:
            self._unsubs.append(
                async_track_state_change_event(self.hass, lists, self._changed)
            )
            for kid in kids:
                self._schedule(kid.id, SETTLE_S)
        return self.async_stop

    @callback
    def async_stop(self) -> None:
        """Stop watching."""
        for unsub in (*self._unsubs, *self._pending.values()):
            unsub()
        self._unsubs.clear()
        self._pending.clear()

    @callback
    def _changed(self, event: Event[EventStateChangedData]) -> None:
        for kid in self._kids():
            if kid.spelling_todo == event.data["entity_id"]:
                self._schedule(kid.id, SETTLE_S)

    @callback
    def _schedule(self, kid_id: str, delay: float) -> None:
        if cancel := self._pending.pop(kid_id, None):
            cancel()

        @callback
        def _run(_now) -> None:
            self._pending.pop(kid_id, None)
            self.coordinator.config_entry.async_create_background_task(
                self.hass, self.async_prepare(kid_id), f"tiny_press clues {kid_id}"
            )

        self._pending[kid_id] = async_call_later(self.hass, delay, _run)

    async def async_prepare(self, kid_id: str) -> None:
        """Ask the AI for clues to this kid's words that don't have one yet."""
        kid = next((k for k in self._kids() if k.id == kid_id), None)
        if kid is None:
            return
        try:
            words = await async_todo_words(self.hass, kid.spelling_todo, kid.name)
            found = jobs.spelling_words_for(words)
        except HomeAssistantError, ValueError:
            return  # no list, nothing left to learn, or it can't be read
        clues = await async_spelling_clues(
            self.hass, self.coordinator, kid, found, wait_s=WAIT_S, retry=True
        )
        _LOGGER.debug(
            "Spelling clues for %s: %d of %d", kid.name, len(clues), len(found)
        )
