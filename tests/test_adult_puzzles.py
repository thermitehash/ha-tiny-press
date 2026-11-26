"""Adult puzzles: graded sudoku, crossword, cryptogram, puzzle pack."""

from __future__ import annotations

from datetime import date
import string
from typing import Any

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators import crossword, cryptogram, sudoku
from custom_components.tiny_press.generators.data import load_json
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

FOOTER = layout.Footer("Puzzle", "PZ12", date(2026, 11, 26), "medium")


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
@pytest.mark.parametrize("seed", range(3))
def test_graded_sudoku(difficulty: str, seed: int) -> None:
    puzzle = sudoku.generate_graded(difficulty, seed)
    assert puzzle.size == 9
    assert sudoku.is_valid_solution(puzzle.solution)
    assert sudoku.count_solutions([list(r) for r in puzzle.puzzle]) == 1
    assert sudoku.grade(puzzle.puzzle) == sudoku.LEVELS[difficulty]
    assert puzzle.givens >= sudoku.MIN_GIVENS[difficulty]


def test_grade_levels() -> None:
    solved = sudoku.generate_graded("easy", 1).solution
    assert sudoku.grade(solved) == 1
    almost = [list(r) for r in solved]
    almost[0][0] = 0
    assert sudoku.grade(almost) == 1


def _check_crossword(cw: crossword.Crossword) -> None:
    letters = cw.letters()
    assert cw.rows <= crossword.MAX_SIDE and cw.cols <= crossword.MAX_SIDE
    for entry in cw.entries:
        assert "".join(letters[c] for c in entry.cells()) == entry.word
        r, c = entry.cells()[0]
        dr, dc = (1, 0) if entry.direction == "down" else (0, 1)
        # No letters run on before or after an answer.
        assert (r - dr, c - dc) not in letters
        er, ec = entry.cells()[-1]
        assert (er + dr, ec + dc) not in letters
    # Every word crosses at least one other (except a lone first word).
    owners: dict[tuple[int, int], int] = {}
    for entry in cw.entries:
        for cell in entry.cells():
            owners[cell] = owners.get(cell, 0) + 1
    for entry in cw.entries:
        assert any(owners[cell] > 1 for cell in entry.cells())
    numbers = sorted({e.number for e in cw.entries})
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
@pytest.mark.parametrize("seed", range(8))
def test_crossword(difficulty: str, seed: int) -> None:
    cw = crossword.generate(difficulty, seed)
    assert len(cw.entries) >= crossword.WORD_COUNT[difficulty] - 2
    _check_crossword(cw)
    assert cw == crossword.generate(difficulty, seed)


def test_clue_bank() -> None:
    bank = load_json("crossword.json")
    assert len(bank) >= 200
    words = [e["word"] for e in bank]
    assert len(set(words)) == len(words)
    for e in bank:
        assert e["word"].isalpha() and e["word"].isupper()
        for clue in (e["clue"], e["tricky"]):
            assert clue and e["word"].lower() not in clue.lower()
    easy = crossword.generate("easy", 3)
    straight = {e["clue"] for e in bank}
    assert all(entry.clue in straight for entry in easy.entries)


@pytest.mark.parametrize("seed", range(10))
def test_cryptogram(seed: int) -> None:
    cg = cryptogram.generate("medium", seed)
    assert all(k != v for k, v in cg.key.items())
    assert sorted(cg.key.values()) == list(string.ascii_uppercase)
    assert cg.cipher == cryptogram.encode(cg.plain, cg.key)
    inverse = {v: k for k, v in cg.key.items()}
    assert "".join(inverse.get(ch, ch) for ch in cg.cipher) == cg.plain.upper()
    assert len(cg.hints) == 1
    assert len(cryptogram.generate("easy", seed).hints) == 2
    assert cryptogram.generate("hard", seed).hints == ()
    again = cryptogram.generate("medium", seed, recent=[cg.index])
    assert again.index != cg.index


def test_quotes_are_sourced() -> None:
    quotes = load_json("quotes.json")
    assert len(quotes) >= 25
    for q in quotes:
        assert q["text"] and q["author"]
        assert q["url"].startswith("https://www.nps.gov/")


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_pages(width: int) -> None:
    cw = crossword.generate("hard", 1)
    cg = cryptogram.generate("easy", 2)
    sd = sudoku.generate_graded("easy", 1)
    for page in (
        layout.crossword_page(width, cw, FOOTER),
        layout.crossword_page(width, cw, FOOTER, answer=True),
        layout.cryptogram_page(width, cg, FOOTER),
        layout.cryptogram_page(width, cg, FOOTER, answer=True),
        layout.sudoku_page(width, sd, FOOTER),
        layout.sudoku_page(width, sd, FOOTER, answer=True),
    ):
        assert page.render()[0].width == width


ADULTS = [
    {"id": "sam", "kind": "adult", "name": "Sam", "difficulty": "hard"},
    {"id": "alex", "kind": "adult", "name": "Alex", "difficulty": "easy"},
]
LIMITS = {"limits_enabled": True, "limit_cooldown_s": 3600}


async def _print(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print", data, blocking=True, return_response=True
    )


async def test_adult_prints(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    hass.config_entries.async_update_entry(
        config_entry, options={"profiles": ADULTS, **LIMITS}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    store = config_entry.runtime_data.store
    assert hass.states.get("select.tiny_press_adult_profile").state == "Sam"
    assert hass.states.get("select.tiny_press_sudoku_difficulty").state == "hard"

    res = await _print(hass, type="sudoku", seed=1)
    assert res["profile"] == "Sam"
    assert store.history[0]["answer"]["difficulty"] == "hard"
    await _print(hass, type="crossword", profile="alex", seed=1)
    assert store.history[0]["answer"]["difficulty"] == "easy"
    res = await _print(hass, type="cryptogram")
    assert store.recent("cryptogram") == [res["quote_index"]]

    # The sudoku select overrides the adult's default.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.tiny_press_sudoku_difficulty", "option": "easy"},
        blocking=True,
    )
    await _print(hass, type="sudoku", seed=2)
    assert store.history[0]["answer"]["difficulty"] == "easy"

    pack = await _print(hass, type="puzzle_pack", seed=4)
    assert len(pack["print_ids"]) == 3
    assert {h["type"] for h in store.history[:3]} == {
        "sudoku",
        "crossword",
        "cryptogram",
    }

    # Adult puzzles never hit kid-mode limits (cooldown is an hour here).
    for kind in ("sudoku", "crossword", "cryptogram"):
        answers = await hass.services.async_call(
            DOMAIN,
            "print_answers",
            {
                "print_id": next(
                    h["print_id"] for h in store.history if h["type"] == kind
                )
            },
            blocking=True,
            return_response=True,
        )
        assert answers["answers_for"] == kind
    for button in ("sudoku", "crossword", "cryptogram", "puzzle_pack"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": f"button.tiny_press_{button}"},
            blocking=True,
        )
