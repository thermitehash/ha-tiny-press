"""Criss-cross crossword generator.

Words interlock freely (no dense American-style grid), which generates
reliably. Pure and deterministic for a given seed. Clues come from the
bundled clue bank: easy uses straight clues, hard uses wordplay clues
(NYT style), medium mixes them.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from .data import load_json

ACROSS = (0, 1)
DOWN = (1, 0)
BOARD = 21  # working canvas; the result is cropped
MAX_SIDE = 13  # fits 80 mm paper with readable cells
WORD_COUNT = {"easy": 8, "medium": 10, "hard": 12}
TRICKY_SHARE = {"easy": 0.0, "medium": 0.5, "hard": 1.0}


@dataclass(frozen=True, slots=True)
class Entry:
    """One answer in the grid."""

    number: int
    word: str
    row: int
    col: int
    direction: str  # "across" or "down"
    clue: str

    def cells(self) -> list[tuple[int, int]]:
        """Grid cells (row, col) of each letter."""
        dr, dc = DOWN if self.direction == "down" else ACROSS
        return [(self.row + i * dr, self.col + i * dc) for i in range(len(self.word))]


@dataclass(frozen=True, slots=True)
class Crossword:
    """A cropped grid and its numbered entries."""

    rows: int
    cols: int
    entries: tuple[Entry, ...]

    def letters(self) -> dict[tuple[int, int], str]:
        """Every filled cell and its letter."""
        out: dict[tuple[int, int], str] = {}
        for entry in self.entries:
            for (r, c), ch in zip(entry.cells(), entry.word, strict=True):
                out[(r, c)] = ch
        return out

    def numbers(self) -> dict[tuple[int, int], int]:
        """Clue numbers by starting cell."""
        return {(e.row, e.col): e.number for e in self.entries}

    def answer(self) -> dict[str, object]:
        """Answer-key data."""
        return {
            "rows": self.rows,
            "cols": self.cols,
            "entries": [
                [e.number, e.word, e.row, e.col, e.direction, e.clue]
                for e in self.entries
            ],
        }


def clue_bank() -> list[dict[str, str]]:
    """Return the bundled words and clues."""
    return load_json("crossword.json")


def _fits(
    grid: dict[tuple[int, int], str], word: str, r: int, c: int, d: tuple[int, int]
) -> int:
    """Count crossings if ``word`` fits at (r, c) in direction d, else -1."""
    dr, dc = d
    end_r, end_c = r + dr * (len(word) - 1), c + dc * (len(word) - 1)
    if not (r >= 0 and c >= 0 and end_r < BOARD and end_c < BOARD):
        return -1
    # Cells just before and after the word must be empty.
    if grid.get((r - dr, c - dc)) or grid.get((end_r + dr, end_c + dc)):
        return -1
    crossings = 0
    for i, ch in enumerate(word):
        rr, cc = r + dr * i, c + dc * i
        existing = grid.get((rr, cc))
        if existing:
            if existing != ch:
                return -1
            crossings += 1
            continue
        # A new letter may not touch letters alongside it (no accidental words).
        side = ((rr + dc, cc + dr), (rr - dc, cc - dr))
        if any(grid.get(s) for s in side):
            return -1
    return crossings


def _extent(grid: dict[tuple[int, int], str]) -> tuple[int, int, int, int]:
    rows = [r for r, _ in grid]
    cols = [c for _, c in grid]
    return min(rows), min(cols), max(rows), max(cols)


def generate(difficulty: str, seed: int) -> Crossword:
    """Build a criss-cross crossword that fits within 13x13 cells."""
    rng = random.Random(seed)
    want = WORD_COUNT.get(difficulty, 10)
    share = TRICKY_SHARE.get(difficulty, 0.5)
    bank = [e for e in clue_bank() if 3 <= len(e["word"]) <= MAX_SIDE]
    best: list[tuple[str, int, int, tuple[int, int]]] = []
    for _attempt in range(30):
        pool = bank[:]
        rng.shuffle(pool)
        first = max(pool[:12], key=lambda e: len(e["word"]))["word"]
        grid: dict[tuple[int, int], str] = {}
        r0, c0 = BOARD // 2, (BOARD - len(first)) // 2
        placed = [(first, r0, c0, ACROSS)]
        for i, ch in enumerate(first):
            grid[(r0, c0 + i)] = ch
        used = {first}
        for entry in pool:
            if len(placed) >= want:
                break
            word = entry["word"]
            if word in used:
                continue
            options = []
            for (gr, gc), ch in list(grid.items()):
                for i, wch in enumerate(word):
                    if wch != ch:
                        continue
                    for d in (ACROSS, DOWN):
                        r, c = gr - d[0] * i, gc - d[1] * i
                        score = _fits(grid, word, r, c, d)
                        if score > 0:
                            trial = dict(grid)
                            for j, x in enumerate(word):
                                trial[(r + d[0] * j, c + d[1] * j)] = x
                            top, left, bottom, right = _extent(trial)
                            if bottom - top < MAX_SIDE and right - left < MAX_SIDE:
                                options.append((score, rng.random(), r, c, d))
            if not options:
                continue
            _s, _t, r, c, d = max(options)
            for j, ch in enumerate(word):
                grid[(r + d[0] * j, c + d[1] * j)] = ch
            placed.append((word, r, c, d))
            used.add(word)
        if len(placed) > len(best):
            best = placed
        if len(best) >= want:
            break
    # Crop, number in reading order, attach clues.
    grid = {}
    for word, r, c, d in best:
        for j, ch in enumerate(word):
            grid[(r + d[0] * j, c + d[1] * j)] = ch
    top, left, bottom, right = _extent(grid)
    clues = {e["word"]: e for e in bank}
    starts = sorted({(r - top, c - left) for _w, r, c, _d in best})
    number_of = {cell: i + 1 for i, cell in enumerate(starts)}
    entries = []
    for word, r, c, d in sorted(best, key=lambda p: (p[1], p[2], p[3] == DOWN)):
        cell = (r - top, c - left)
        bank_entry = clues[word]
        tricky = bank_entry.get("tricky") and rng.random() < share
        entries.append(
            Entry(
                number_of[cell],
                word,
                cell[0],
                cell[1],
                "down" if d == DOWN else "across",
                bank_entry["tricky"] if tricky else bank_entry["clue"],
            )
        )
    return Crossword(bottom - top + 1, right - left + 1, tuple(entries))
