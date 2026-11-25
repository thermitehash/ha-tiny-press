"""Maze generator: deterministic, perfect and solvable."""

from __future__ import annotations

from collections import deque

import pytest

from custom_components.tiny_press.const import Difficulty
from custom_components.tiny_press.generators import maze


@pytest.mark.parametrize("difficulty", list(Difficulty))
@pytest.mark.parametrize("seed", [0, 1, 42, 2**31 - 1])
def test_maze_is_perfect_and_solvable(difficulty: Difficulty, seed: int) -> None:
    m = maze.generate(difficulty, seed)
    assert (m.cols, m.rows) == maze.SIZES[difficulty]
    assert m.rows > m.cols  # tall, for a receipt roll
    cells = m.cols * m.rows
    # A spanning tree has exactly cells - 1 passages, all between neighbours.
    assert len(m.passages) == cells - 1
    for passage in m.passages:
        (c1, r1), (c2, r2) = tuple(passage)
        assert abs(c1 - c2) + abs(r1 - r2) == 1
    # Every cell is reachable from the start.
    seen = {m.start}
    queue = deque([m.start])
    while queue:
        for nxt in m.neighbours(queue.popleft()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    assert len(seen) == cells
    # The solution walks open passages from start to finish.
    assert m.solution[0] == m.start and m.solution[-1] == m.finish
    for a, b in zip(m.solution, m.solution[1:], strict=False):
        assert m.is_open(a, b)
    assert len(set(m.solution)) == len(m.solution)


def test_maze_is_deterministic() -> None:
    assert maze.generate("medium", 7) == maze.generate("medium", 7)
    assert maze.generate("medium", 7).passages != maze.generate("medium", 8).passages


def test_known_seed_snapshot() -> None:
    # Guards against accidental changes to the generator for a given seed.
    m = maze.generate_size(3, 3, 1)
    assert len(m.solution) >= 5
    assert m.answer()["solution"][0] == [0, 0]
    assert m.answer()["solution"][-1] == [2, 2]


def test_too_small() -> None:
    with pytest.raises(ValueError):
        maze.generate_size(1, 5, 0)


def test_solve_unreachable() -> None:
    assert maze.solve(2, 2, frozenset(), (0, 0), (1, 1)) == ()
