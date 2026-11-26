"""Kid sudoku and spelling practice."""

from __future__ import annotations

from datetime import date
import random
from typing import Any

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators import spelling, sudoku, word_search
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

FOOTER = layout.Footer("Sudoku", "SD12", date(2026, 11, 26))


@pytest.mark.parametrize("size", [4, 6, 9])
@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
@pytest.mark.parametrize("seed", range(4))
def test_sudoku_unique(size: int, difficulty: str, seed: int) -> None:
    puzzle = sudoku.generate(size, difficulty, seed)
    assert sudoku.is_valid_solution(puzzle.solution)
    assert sudoku.count_solutions([list(r) for r in puzzle.puzzle]) == 1
    for r in range(size):
        for c in range(size):
            if puzzle.puzzle[r][c]:
                assert puzzle.puzzle[r][c] == puzzle.solution[r][c]
    assert puzzle.givens >= sudoku.GIVENS[(size, difficulty)]
    assert puzzle == sudoku.generate(size, difficulty, seed)


def test_sudoku_helpers() -> None:
    with pytest.raises(ValueError):
        sudoku.generate(5, "easy", 1)
    assert sudoku.count_solutions([[0] * 4 for _ in range(4)]) == 2
    bad = [[1, 1, 2, 3], [2, 3, 4, 1], [3, 4, 1, 2], [4, 2, 3, 4]]
    assert not sudoku.is_valid_solution(bad)
    assert sudoku.count_solutions([[1, 1, 0, 0], [0] * 4, [0] * 4, [0] * 4]) == 0
    assert sudoku.generate(4, "easy", 1).answer()["size"] == 4


def test_parse_words() -> None:
    assert spelling.parse_words("Because, friend;said\nwhere, where , they're") == [
        "because",
        "friend",
        "said",
        "where",
        "theyre",
    ]
    assert spelling.parse_words(["Cat", "a", "dog"]) == ["cat", "dog"]
    assert spelling.parse_words("") == []
    many = spelling.parse_words(",".join("word" + "x" * i for i in range(60)))
    assert len(many) == spelling.MAX_PARSED
    picked = spelling.pick_words(many, 1)
    assert len(picked) == spelling.MAX_WORDS and set(picked) <= set(many)
    assert picked != spelling.pick_words(many, 2)
    assert len(spelling.generate(many, 3).words) == spelling.MAX_WORDS


@pytest.mark.parametrize("seed", range(10))
def test_spelling_sheet(seed: int) -> None:
    words = ["because", "friend", "said", "we", "eel", "aaa"]
    sheet = spelling.generate(words, seed)
    assert sorted(sheet.words) == sorted(words)
    for i, word in enumerate(sheet.words):
        assert sorted(sheet.scrambled[i]) == sorted(word)
        if len(set(word)) > 1:
            assert sheet.scrambled[i] != word
        blanks = sheet.blanks[i]
        assert blanks and 0 not in blanks and len(blanks) < len(word)
        masked = sheet.masked(i).split(" ")
        assert [masked[j] for j in blanks] == ["_"] * len(blanks)
    with pytest.raises(ValueError):
        spelling.generate([], 1)
    assert spelling.scramble("a", random.Random(1)) == "a"
    assert spelling.blank_positions("a", random.Random(1)) == []


@pytest.mark.parametrize("seed", range(10))
def test_spelling_word_search_places_all(seed: int) -> None:
    words = spelling.parse_words(
        "because, friend, said, where, again, people, school, house, would, could, "
        "their, there, through, thought"
    )
    puzzle = word_search.generate_from_words("2", seed, words)
    assert sorted(w.lower() for w in puzzle.words) == sorted(words)
    for p in puzzle.placements:
        assert "".join(puzzle.grid[r][c] for r, c in p.cells()) == p.word
    with pytest.raises(ValueError):
        word_search.generate_from_words("2", seed, [])
    with pytest.raises(ValueError):
        word_search.generate_from_words("2", seed, ["a" * 16])


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_pages_exact_width(width: int) -> None:
    pages = []
    for size in (4, 6):
        p = sudoku.generate(size, "easy", 2)
        pages += [
            layout.sudoku_page(width, p, FOOTER),
            layout.sudoku_page(width, p, FOOTER, answer=True),
        ]
    sheet = spelling.generate(["because", "friend", "said"], 1)
    pages += [
        layout.spelling_page(width, sheet, FOOTER),
        layout.spelling_page(width, sheet, FOOTER, answer=True),
    ]
    for page in pages:
        assert page.render()[0].width == width


KID = {
    "id": "rosie",
    "kind": "kid",
    "name": "Rosie",
    "grade": "1",
    "spelling_todo": "todo.rosie_spelling",
}
WORDS = [
    {"summary": w, "status": "needs_action"} for w in ("cat", "dog", "sun", "fish")
]
OLDER = {"id": "max", "kind": "kid", "name": "Max", "grade": "4"}


async def _print(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print", data, blocking=True, return_response=True
    )


async def test_prints_through_action(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    hass.config_entries.async_update_entry(
        config_entry, options={"profiles": [KID, OLDER]}
    )
    _todo(hass, WORDS)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    store = config_entry.runtime_data.store

    await _print(hass, type="kid_sudoku", seed=1)
    answer = store.history[0]["answer"]
    assert answer["size"] == 4  # grade 1 default
    await _print(hass, type="kid_sudoku", profile="max", seed=1)
    answer = store.history[0]["answer"]
    assert answer["size"] == 6
    await _print(hass, type="kid_sudoku", difficulty="easy", seed=2)
    assert store.history[0]["answer"]["size"] == 4

    res = await _print(hass, type="spelling", seed=3)
    assert sorted(store.history[0]["answer"]["words"]) == ["cat", "dog", "fish", "sun"]
    res = await _print(hass, type="spelling_search", seed=3)
    assert sorted(p[0] for p in store.history[0]["answer"]["placements"]) == [
        "CAT",
        "DOG",
        "FISH",
        "SUN",
    ]
    for kind in ("kid_sudoku", "spelling", "spelling_search"):
        await _print(hass, type=kind, seed=9)
        answers = await hass.services.async_call(
            DOMAIN, "print_answers", {}, blocking=True, return_response=True
        )
        assert answers["answers_for"] == kind
    with pytest.raises(ServiceValidationError, match="no spelling words"):
        await _print(hass, type="spelling", profile="max")
    preview = await hass.services.async_call(
        DOMAIN,
        "preview",
        {"type": "spelling"},
        blocking=True,
        return_response=True,
    )
    assert preview["image"].startswith("data:image/png")
    for button in ("kid_sudoku", "spelling", "spelling_search"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": f"button.tiny_press_{button}"},
            blocking=True,
        )
    assert res["type"] == "spelling_search"


def _todo(hass: HomeAssistant, items: list[dict[str, str]] | Exception) -> list[str]:
    calls: list[str] = []

    async def get_items(call):
        calls.append(call.data["entity_id"])
        if isinstance(items, Exception):
            raise items
        return {call.data["entity_id"]: {"items": items}}

    hass.services.async_register(
        "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
    )
    return calls


# An old typed list left in the options from before v0.11.2 is ignored.
TODO_KID = {**KID, "spelling_words": "typed"}


async def _setup_todo_kid(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(entry, options={"profiles": [TODO_KID]})
    assert await hass.config_entries.async_setup(entry.entry_id)


async def test_spelling_from_todo_list(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    calls = _todo(
        hass,
        [
            {"summary": "because", "status": "needs_action"},
            {"summary": "Friend!", "status": "needs_action"},
            {"summary": "said", "status": "completed"},
        ],
    )
    await _setup_todo_kid(hass, config_entry)
    await _print(hass, type="spelling", seed=1)
    store = config_entry.runtime_data.store
    assert sorted(store.history[0]["answer"]["words"]) == ["because", "friend"]
    assert calls == ["todo.rosie_spelling"]
    await _print(hass, type="spelling_search", seed=1)
    words = sorted(p[0] for p in store.history[0]["answer"]["placements"])
    assert words == ["BECAUSE", "FRIEND"]
    assert len(calls) == 2
    # Words can't be passed to the action: the linked list is required.
    with pytest.raises(vol.Invalid):
        await _print(hass, type="spelling", words="moon", seed=2)


async def test_all_words_learned(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _todo(hass, [{"summary": "said", "status": "completed"}])
    await _setup_todo_kid(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="learned every word"):
        await _print(hass, type="spelling")


async def test_unreadable_todo_has_no_words(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    from homeassistant.exceptions import HomeAssistantError

    _todo(hass, HomeAssistantError("gone"))
    await _setup_todo_kid(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="no spelling words"):
        await _print(hass, type="spelling", seed=1)


async def test_empty_todo_has_no_words(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _todo(hass, [])
    await _setup_todo_kid(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="no spelling words"):
        await _print(hass, type="spelling", seed=1)
    profiles = hass.states.get("select.tiny_press_kid_profile").attributes["profiles"]
    assert profiles[0]["spelling_todo"] == "todo.rosie_spelling"
