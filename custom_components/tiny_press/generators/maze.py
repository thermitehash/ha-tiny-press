"""Maze generator (Wilson's algorithm: a uniform random spanning tree).

Pure and deterministic for a given seed. Mazes are tall (more rows than
columns) to suit a receipt roll. The entrance is the top-left cell and the
exit the bottom-right cell.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random

from ..const import Difficulty

Cell = tuple[int, int]  # (col, row)

SIZES: dict[Difficulty, tuple[int, int]] = {
    Difficulty.EASY: (8, 12),
    Difficulty.MEDIUM: (12, 18),
    Difficulty.HARD: (16, 28),
}


@dataclass(frozen=True, slots=True)
class Maze:
    """A perfect maze: exactly one path between any two cells."""

    cols: int
    rows: int
    passages: frozenset[frozenset[Cell]]
    start: Cell
    finish: Cell
    solution: tuple[Cell, ...]

    def is_open(self, a: Cell, b: Cell) -> bool:
        """Return True if there is no wall between neighbouring cells."""
        return frozenset((a, b)) in self.passages

    def neighbours(self, cell: Cell) -> list[Cell]:
        """Cells reachable in one step."""
        col, row = cell
        out = []
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (col + dc, row + dr)
            if self.is_open(cell, nxt):
                out.append(nxt)
        return out

    def answer(self) -> dict[str, object]:
        """Answer-key data (stored for ``print_answers``)."""
        return {
            "cols": self.cols,
            "rows": self.rows,
            "solution": [list(c) for c in self.solution],
        }


def _grid_neighbours(cell: Cell, cols: int, rows: int) -> list[Cell]:
    col, row = cell
    return [
        (c, r)
        for c, r in ((col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1))
        if 0 <= c < cols and 0 <= r < rows
    ]


def solve(
    cols: int,
    rows: int,
    passages: frozenset[frozenset[Cell]],
    start: Cell,
    finish: Cell,
) -> tuple[Cell, ...]:
    """Breadth-first search; returns the path or an empty tuple."""
    prev: dict[Cell, Cell | None] = {start: None}
    queue: deque[Cell] = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == finish:
            path: list[Cell] = []
            node: Cell | None = cell
            while node is not None:
                path.append(node)
                node = prev[node]
            return tuple(reversed(path))
        for nxt in _grid_neighbours(cell, cols, rows):
            if nxt not in prev and frozenset((cell, nxt)) in passages:
                prev[nxt] = cell
                queue.append(nxt)
    return ()


def generate(difficulty: Difficulty | str, seed: int) -> Maze:
    """Build a maze for a difficulty."""
    cols, rows = SIZES[Difficulty(difficulty)]
    return generate_size(cols, rows, seed)


def generate_size(cols: int, rows: int, seed: int) -> Maze:
    """Build a ``cols`` x ``rows`` maze with Wilson's loop-erased random walks."""
    if cols < 2 or rows < 2:
        raise ValueError("maze must be at least 2x2")
    rng = random.Random(seed)
    cells = [(c, r) for r in range(rows) for c in range(cols)]
    in_tree: set[Cell] = {rng.choice(cells)}
    passages: set[frozenset[Cell]] = set()
    for cell in cells:
        if cell in in_tree:
            continue
        # Random walk until the tree is hit, remembering the last exit from
        # each cell (which erases loops implicitly).
        step: dict[Cell, Cell] = {}
        cur = cell
        while cur not in in_tree:
            nxt = rng.choice(_grid_neighbours(cur, cols, rows))
            step[cur] = nxt
            cur = nxt
        cur = cell
        while cur not in in_tree:
            nxt = step[cur]
            passages.add(frozenset((cur, nxt)))
            in_tree.add(cur)
            cur = nxt
    frozen = frozenset(passages)
    start, finish = (0, 0), (cols - 1, rows - 1)
    return Maze(
        cols, rows, frozen, start, finish, solve(cols, rows, frozen, start, finish)
    )
