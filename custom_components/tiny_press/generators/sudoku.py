"""Sudoku generator with a unique-solution check.

Pure and deterministic for a given seed. Supports 4x4 (2x2 boxes), 6x6
(2-row x 3-column boxes) and 9x9 (3x3 boxes). Kid sudoku uses 4x4 and 6x6;
the adult puzzles (v0.4.0) will use 9x9.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

BOXES: dict[int, tuple[int, int]] = {4: (2, 2), 6: (2, 3), 9: (3, 3)}

# How many givens to keep for (size, difficulty). Fewer givens is harder.
GIVENS: dict[tuple[int, str], int] = {
    (4, "easy"): 8,
    (4, "medium"): 6,
    (4, "hard"): 5,
    (6, "easy"): 20,
    (6, "medium"): 16,
    (6, "hard"): 13,
    (9, "easy"): 38,
    (9, "medium"): 32,
    (9, "hard"): 27,
}

Grid = list[list[int]]  # 0 = empty


@dataclass(frozen=True, slots=True)
class Sudoku:
    """A puzzle and its (unique) solution."""

    size: int
    puzzle: tuple[tuple[int, ...], ...]
    solution: tuple[tuple[int, ...], ...]

    @property
    def box(self) -> tuple[int, int]:
        """(rows, columns) of one box."""
        return BOXES[self.size]

    @property
    def givens(self) -> int:
        """Number of filled-in cells."""
        return sum(1 for row in self.puzzle for v in row if v)

    def answer(self) -> dict[str, object]:
        """Answer-key data."""
        return {
            "size": self.size,
            "puzzle": [list(r) for r in self.puzzle],
            "solution": [list(r) for r in self.solution],
        }


def _candidates(grid: Grid, r: int, c: int, size: int) -> list[int]:
    br, bc = BOXES[size]
    used = set(grid[r]) | {grid[i][c] for i in range(size)}
    r0, c0 = r - r % br, c - c % bc
    used |= {grid[i][j] for i in range(r0, r0 + br) for j in range(c0, c0 + bc)}
    return [v for v in range(1, size + 1) if v not in used]


def count_solutions(grid: Grid, limit: int = 2) -> int:
    """Count solutions up to ``limit`` (most-constrained-cell backtracking)."""
    size = len(grid)
    best: tuple[int, int, list[int]] | None = None
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 0:
                options = _candidates(grid, r, c, size)
                if not options:
                    return 0
                if best is None or len(options) < len(best[2]):
                    best = (r, c, options)
    if best is None:
        return 1
    r, c, options = best
    total = 0
    for v in options:
        grid[r][c] = v
        total += count_solutions(grid, limit - total)
        grid[r][c] = 0
        if total >= limit:
            break
    return total


def _fill(grid: Grid, rng: random.Random, pos: int = 0) -> bool:
    size = len(grid)
    if pos == size * size:
        return True
    r, c = divmod(pos, size)
    options = _candidates(grid, r, c, size)
    rng.shuffle(options)
    for v in options:
        grid[r][c] = v
        if _fill(grid, rng, pos + 1):
            return True
    grid[r][c] = 0
    return False


def is_valid_solution(grid: Grid | tuple[tuple[int, ...], ...]) -> bool:
    """Every row, column and box holds 1..n exactly once."""
    size = len(grid)
    br, bc = BOXES[size]
    want = set(range(1, size + 1))
    rows = all(set(row) == want for row in grid)
    cols = all({grid[r][c] for r in range(size)} == want for c in range(size))
    boxes = all(
        {grid[r][c] for r in range(r0, r0 + br) for c in range(c0, c0 + bc)} == want
        for r0 in range(0, size, br)
        for c0 in range(0, size, bc)
    )
    return rows and cols and boxes


def generate(size: int, difficulty: str, seed: int) -> Sudoku:
    """Make a puzzle with exactly one solution and about the target givens."""
    if size not in BOXES:
        raise ValueError("size must be 4, 6 or 9")
    rng = random.Random(seed)
    solution: Grid = [[0] * size for _ in range(size)]
    _fill(solution, rng)
    puzzle = [row[:] for row in solution]
    target = GIVENS.get((size, difficulty), GIVENS[(size, "medium")])
    cells = [(r, c) for r in range(size) for c in range(size)]
    rng.shuffle(cells)
    filled = size * size
    for r, c in cells:
        if filled <= target:
            break
        keep = puzzle[r][c]
        puzzle[r][c] = 0
        if count_solutions([row[:] for row in puzzle]) != 1:
            puzzle[r][c] = keep
        else:
            filled -= 1
    return Sudoku(
        size,
        tuple(tuple(row) for row in puzzle),
        tuple(tuple(row) for row in solution),
    )
