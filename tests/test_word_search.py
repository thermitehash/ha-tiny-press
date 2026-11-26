"""Word search generator."""

from __future__ import annotations

import pytest

from custom_components.tiny_press.generators import word_search as ws


def _find(puzzle: ws.WordSearch, placement: ws.Placement) -> str:
    return "".join(puzzle.grid[r][c] for r, c in placement.cells())


@pytest.mark.parametrize("grade", ["K", "1", "2", "3", "4", "5"])
@pytest.mark.parametrize("seed", range(8))
def test_every_word_is_placed(grade: str, seed: int) -> None:
    puzzle = ws.generate(grade, seed, interests="dinosaurs, space and horses")
    assert puzzle.size == (12 if grade in ("4", "5") else 10)
    assert len(puzzle.grid) == puzzle.size
    assert all(len(row) == puzzle.size and row.isupper() for row in puzzle.grid)
    assert len(puzzle.placements) == ws.DEFAULT_WORD_COUNT[puzzle.size]
    allowed = set(ws.directions_for_grade(grade))
    for placement in puzzle.placements:
        assert _find(puzzle, placement) == placement.word
        assert (placement.d_row, placement.d_col) in allowed
    # No word hides inside another one.
    words = puzzle.words
    assert len(set(words)) == len(words)
    for a in words:
        assert not any(a != b and a in b for b in words)


def test_directions_by_grade() -> None:
    assert ws.directions_for_grade("2") == [ws.ACROSS, ws.DOWN]
    assert ws.DIAG_DOWN in ws.directions_for_grade("3")
    assert ws.DIAG_UP not in ws.directions_for_grade("3")
    assert ws.DIAG_UP in ws.directions_for_grade("4")


def test_interests_feed_words() -> None:
    themed, _ = ws.word_pool("3", "Dinosaurs & horses, my cat Pickles")
    assert "FOSSIL" in themed and "GALLOP" in themed
    assert "PURR" in themed  # "cat" -> cats theme
    assert "PICKLES" in themed  # unknown words are used as-is
    puzzle = ws.generate("3", 1, interests="dinosaurs")
    assert set(puzzle.words) & set(themed)


def test_deterministic_and_answer() -> None:
    a = ws.generate("3", 99, interests="ocean")
    assert a == ws.generate("3", 99, interests="ocean")
    assert a != ws.generate("3", 100, interests="ocean")
    answer = a.answer()
    assert answer["grid"] == list(a.grid)
    assert len(answer["placements"]) == len(a.placements)


def test_custom_size_and_count() -> None:
    puzzle = ws.generate("5", 3, size=8, count=5)
    assert puzzle.size == 8
    assert len(puzzle.placements) == 5
    assert all(len(w) <= 8 for w in puzzle.words)
