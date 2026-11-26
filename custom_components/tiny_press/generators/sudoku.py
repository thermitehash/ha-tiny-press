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


# ---- difficulty by technique (adult 9x9) ----------------------------------

LEVELS = {"easy": 1, "medium": 2, "hard": 3}
MIN_GIVENS = {"easy": 34, "medium": 28, "hard": 22}  # keeps easy puzzles friendly
Cands = list[list[set[int]]]


def _units(size: int) -> list[list[tuple[int, int]]]:
    br, bc = BOXES[size]
    rows = [[(r, c) for c in range(size)] for r in range(size)]
    cols = [[(r, c) for r in range(size)] for c in range(size)]
    boxes = [
        [(r, c) for r in range(r0, r0 + br) for c in range(c0, c0 + bc)]
        for r0 in range(0, size, br)
        for c0 in range(0, size, bc)
    ]
    return rows + cols + boxes


def _peers(size: int) -> dict[tuple[int, int], set[tuple[int, int]]]:
    peers: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for unit in _units(size):
        for cell in unit:
            peers.setdefault(cell, set()).update(unit)
    for cell, group in peers.items():
        group.discard(cell)
    return peers


def _place(
    grid: Grid, cands: Cands, peers: dict, cell: tuple[int, int], v: int
) -> None:
    r, c = cell
    grid[r][c] = v
    cands[r][c] = set()
    for pr, pc in peers[(r, c)]:
        cands[pr][pc].discard(v)


def _singles(grid: Grid, cands: Cands, units: list, peers: dict) -> bool:
    """Naked and hidden singles. Returns True if anything was placed."""
    size = len(grid)
    for r in range(size):
        for c in range(size):
            if not grid[r][c] and len(cands[r][c]) == 1:
                _place(grid, cands, peers, (r, c), next(iter(cands[r][c])))
                return True
    for unit in units:
        for v in range(1, size + 1):
            spots = [(r, c) for r, c in unit if not grid[r][c] and v in cands[r][c]]
            if len(spots) == 1:
                _place(grid, cands, peers, spots[0], v)
                return True
    return False


def _pairs_and_pointing(grid: Grid, cands: Cands, units: list) -> bool:
    """Naked pairs and box/line (pointing) eliminations."""
    size = len(grid)
    changed = False
    for unit in units:
        empty = [(r, c) for r, c in unit if not grid[r][c]]
        pairs: dict[frozenset[int], list[tuple[int, int]]] = {}
        for r, c in empty:
            if len(cands[r][c]) == 2:
                pairs.setdefault(frozenset(cands[r][c]), []).append((r, c))
        for pair, cells in pairs.items():
            if len(cells) == 2:
                for r, c in empty:
                    if (r, c) not in cells and cands[r][c] & pair:
                        cands[r][c] -= pair
                        changed = True
    boxes = units[2 * size :]
    lines = units[: 2 * size]
    for box in boxes:
        for v in range(1, size + 1):
            spots = [(r, c) for r, c in box if not grid[r][c] and v in cands[r][c]]
            if len(spots) < 2:
                continue
            for line in lines:
                if all(s in line for s in spots):
                    for r, c in line:
                        if (r, c) not in box and not grid[r][c] and v in cands[r][c]:
                            cands[r][c].discard(v)
                            changed = True
    return changed


def grade(puzzle: Grid | tuple[tuple[int, ...], ...]) -> int:
    """1: singles only; 2: also needs pairs/pointing; 3: needs more than that."""
    size = len(puzzle)
    grid = [list(row) for row in puzzle]
    units, peers = _units(size), _peers(size)
    cands: Cands = [
        [
            set()
            if grid[r][c]
            else set(range(1, size + 1)) - {grid[pr][pc] for pr, pc in peers[(r, c)]}
            for c in range(size)
        ]
        for r in range(size)
    ]
    level = 1
    while any(0 in row for row in grid):
        if _singles(grid, cands, units, peers):
            continue
        if _pairs_and_pointing(grid, cands, units):
            level = 2
            continue
        return 3
    return level


def generate_graded(difficulty: str, seed: int, size: int = 9) -> Sudoku:
    """Make a unique puzzle whose solving techniques match the difficulty."""
    target = LEVELS.get(difficulty, 2)
    best: tuple[int, Sudoku] | None = None
    for attempt in range(40):
        rng = random.Random(f"{seed}-{attempt}")
        solution: Grid = [[0] * size for _ in range(size)]
        _fill(solution, rng)
        puzzle = [row[:] for row in solution]
        cells = [(r, c) for r in range(size) for c in range(size)]
        rng.shuffle(cells)
        filled = size * size
        floor = MIN_GIVENS.get(difficulty, 22)
        for r, c in cells:
            if filled <= floor:
                break
            keep = puzzle[r][c]
            puzzle[r][c] = 0
            filled -= 1
            if (
                count_solutions([row[:] for row in puzzle]) != 1
                or grade(puzzle) > target
            ):
                puzzle[r][c] = keep
                filled += 1
        result = Sudoku(size, tuple(map(tuple, puzzle)), tuple(map(tuple, solution)))
        level = grade(puzzle)
        if level == target:
            return result
        if best is None or abs(level - target) < abs(best[0] - target):
            best = (level, result)
    assert best is not None
    return best[1]
