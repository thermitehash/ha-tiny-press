"""Spelling crossword: the generator, AI clues and the print."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.tiny_press.ai import clue_ok
from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators import crossword, spelling
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

WORDS = ["because", "friend", "said", "where", "they", "once", "people", "water"]
KID = {"id": "rosie", "kind": "kid", "name": "Rosie", "grade": "2"}
KID["spelling_todo"] = "todo.rosie_spelling"


@pytest.mark.parametrize("seed", range(6))
def test_grid_holds_the_spelling_words(seed: int) -> None:
    entries = [{"word": w, "clue": f"clue {w}"} for w in WORDS]
    puzzle, also = crossword.generate_from_words(entries, seed)
    placed = {e.word for e in puzzle.entries}
    assert placed | set(also) == {w.upper() for w in WORDS}
    assert len(placed) >= 6  # common letters: nearly all interlock
    assert puzzle.rows <= crossword.MAX_SIDE and puzzle.cols <= crossword.MAX_SIDE
    letters = puzzle.letters()
    for entry in puzzle.entries:
        assert entry.clue == f"clue {entry.word.lower()}"
        assert "".join(letters[c] for c in entry.cells()) == entry.word
    # Deterministic for a seed.
    assert crossword.generate_from_words(entries, seed)[0] == puzzle


def test_words_that_cannot_join_are_listed() -> None:
    entries = [{"word": w, "clue": "x"} for w in ("cat", "car", "bun")]
    puzzle, also = crossword.generate_from_words(entries, 1)
    assert {e.word for e in puzzle.entries} == {"CAT", "CAR"}
    assert also == ("BUN",)
    with pytest.raises(ValueError):
        crossword.generate_from_words([{"word": "1x", "clue": "x"}], 1)


def test_scramble_clue_and_clue_checks() -> None:
    clue = spelling.scramble_clue("because", 3)
    assert clue.startswith("Unscramble: ")
    scrambled = clue.removeprefix("Unscramble: ")
    assert sorted(scrambled) == sorted("BECAUSE") and scrambled != "BECAUSE"
    assert spelling.scramble_clue("because", 3) == clue
    assert clue_ok("friend", "Someone you like to play with")
    assert not clue_ok("friend", "A friend is someone kind")
    assert not clue_ok("friend", "Not unfriendly")  # longer word built on it
    assert clue_ok("in", "Not out: come ___ the house")  # short words: whole only
    assert not clue_ok("in", "Come in!")
    assert not clue_ok("said", "See https://example.com")
    assert not clue_ok("said", "x" * 91)
    assert not clue_ok("said", None)


def test_page_renders_with_left_out_words() -> None:
    entries = [{"word": w, "clue": "A clue"} for w in ("cat", "car", "bun")]
    puzzle, also = crossword.generate_from_words(entries, 1)
    footer = layout.Footer("Spelling crossword", "SC12", date(2026, 11, 26))
    for width in PAPER_DOTS.values():
        page = layout.crossword_page(
            width, puzzle, footer, title="Spelling crossword", who="Rosie", also=also
        )
        assert page.render()[0].width == width


def _todo(hass: HomeAssistant, words: list[str]) -> None:
    async def get_items(call: ServiceCall) -> dict[str, Any]:
        items = [{"summary": w, "status": "needs_action"} for w in words]
        return {call.data["entity_id"]: {"items": items}}

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )


def _ai(hass: HomeAssistant, answer: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(dict(call.data))
        return {"data": answer(call.data["structure"])}

    hass.services.async_register(
        "ai_task", "generate_data", handler, supports_response=SupportsResponse.ONLY
    )
    return calls


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(
        entry, options={"profiles": [KID], **options}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, service: str, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


def _clues(store) -> dict[str, str]:
    return {e[1]: e[5] for e in store.history[0]["answer"]["entries"]}


async def test_ai_clues_with_checks_and_cache(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _todo(hass, ["because", "friend", "said"])

    def answer(structure: dict[str, Any]) -> dict[str, str]:
        out = {}
        for key, spec in structure.items():
            word = spec["description"].split("'")[1]
            # One bad clue (it gives the word away) falls back to a scramble.
            out[key] = f"Use {word} here" if word == "said" else f"A clue for {key}"
        return out

    calls = _ai(hass, answer)
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    preview = await _call(hass, "preview", type="spelling_crossword")
    printed = await _call(
        hass, "print", type="spelling_crossword", seed=preview["seed"]
    )
    assert printed["print_id"] == preview["print_id"]
    assert printed["ai_clues"] == 2
    assert len(calls) == 1  # the preview's clues were kept for the print
    assert "grade 2" in calls[0]["instructions"]
    clues = _clues(config_entry.runtime_data.store)
    assert clues["BECAUSE"].startswith("A clue for clue_")
    assert clues["SAID"].startswith("Unscramble: ")
    # The answer key prints, titled for the spelling crossword.
    answers = await _call(hass, "print_answers")
    assert answers["answers_for"] == "spelling_crossword"


async def test_offline_clues_are_scrambles(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _todo(hass, ["because", "friend", "said"])
    await _setup(hass, config_entry)
    printed = await _call(hass, "print", type="spelling_crossword", seed=4)
    assert printed["ai_clues"] == 0
    clues = _clues(config_entry.runtime_data.store)
    assert all(c.startswith("Unscramble: ") for c in clues.values())
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.tiny_press_spelling_crossword"},
        blocking=True,
    )


async def test_failed_ai_is_asked_again(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _todo(hass, ["because", "friend"])
    calls = _ai(hass, lambda _s: {})
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    for _ in range(2):
        printed = await _call(hass, "print", type="spelling_crossword")
        assert printed["ai_clues"] == 0
    assert len(calls) == 2


async def test_needs_a_spelling_list(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _todo(hass, [])
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="no spelling words"):
        await _call(hass, "print", type="spelling_crossword")


async def test_clues_are_written_ahead(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    words = ["because", "friend"]
    _todo(hass, words)
    calls = _ai(hass, lambda structure: {k: f"A clue for {k}" for k in structure})
    hass.states.async_set("todo.rosie_spelling", "2")
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    # At startup, once the lists settle, the clues are written.
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls) == 1
    # The print then finds them ready: no wait on the AI.
    printed = await _call(hass, "print", type="spelling_crossword")
    assert printed["ai_clues"] == 2 and len(calls) == 1
    # A new word on the list gets its clue ahead too (only the new word).
    words.append("said")
    hass.states.async_set("todo.rosie_spelling", "3")
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls) == 2
    assert list(calls[1]["structure"]) == ["clue_1"]
    assert "'said'" in calls[1]["instructions"]
