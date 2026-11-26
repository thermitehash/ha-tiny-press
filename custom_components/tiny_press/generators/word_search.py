"""Word search generator.

Pure and deterministic for a given seed. Words come from the grade list plus
words related to the kid's interests. Every word in the returned list is
placed in the grid; words that don't fit are swapped for others.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
import re
import string

from ..profiles import grade_number
from .data import load_json

# (d_row, d_col)
ACROSS = (0, 1)
DOWN = (1, 0)
DIAG_DOWN = (1, 1)
DIAG_UP = (-1, 1)

DEFAULT_WORD_COUNT = {10: 8, 12: 11}
STOP_WORDS = {
    "the",
    "and",
    "her",
    "his",
    "my",
    "our",
    "likes",
    "loves",
    "love",
    "with",
    "all",
    "kinds",
    "things",
    "playing",
}


@dataclass(frozen=True, slots=True)
class Placement:
    """Where one word sits: start cell and direction."""

    word: str
    row: int
    col: int
    d_row: int
    d_col: int

    def cells(self) -> list[tuple[int, int]]:
        """Return the (row, col) of each letter."""
        return [
            (self.row + i * self.d_row, self.col + i * self.d_col)
            for i in range(len(self.word))
        ]


@dataclass(frozen=True, slots=True)
class WordSearch:
    """A filled letter grid and the words hidden in it."""

    size: int
    grid: tuple[str, ...]  # one string per row, uppercase
    placements: tuple[Placement, ...]

    @property
    def words(self) -> list[str]:
        """Hidden words in alphabetical order."""
        return sorted(p.word for p in self.placements)

    def answer(self) -> dict[str, object]:
        """Answer-key data (stored for ``print_answers``)."""
        return {
            "size": self.size,
            "grid": list(self.grid),
            "placements": [
                [p.word, p.row, p.col, p.d_row, p.d_col] for p in self.placements
            ],
        }


def size_for_grade(grade: str) -> int:
    """10x10 up to grade 3, 12x12 from grade 4."""
    return 12 if grade_number(grade) >= 4 else 10


def directions_for_grade(grade: str) -> list[tuple[int, int]]:
    """Across and down for everyone; diagonals from grade 3 (up from grade 4)."""
    n = grade_number(grade)
    dirs = [ACROSS, DOWN]
    if n >= 3:
        dirs.append(DIAG_DOWN)
    if n >= 4:
        dirs.append(DIAG_UP)
    return dirs


def interest_words(interests: str) -> list[str]:
    """Words for the free-text interests ("dinosaurs, space and horses")."""
    themes: dict[str, list[str]] = load_json("themes.json")
    out: list[str] = []
    for raw in re.split(r",|;|/|\band\b|&", interests.lower()):
        token = re.sub(r"[^a-z ]", "", raw).strip()
        if not token:
            continue
        if theme := _theme(themes, token):
            out.extend(themes[theme])
            continue
        for word in token.split():
            if word in STOP_WORDS or len(word) < 3:
                continue
            if theme := _theme(themes, word):
                out.extend(themes[theme])
            else:
                out.append(word)
    return out


def _theme(themes: dict[str, list[str]], word: str) -> str | None:
    for key in (word, word.rstrip("s"), f"{word}s"):
        if key in themes:
            return key
    return None


def word_pool(grade: str, interests: str = "") -> tuple[list[str], list[str]]:
    """(interest words, grade words), each de-duplicated, uppercase."""
    words: dict[str, list[str]] = load_json("words.json")
    n = grade_number(grade)
    # Grade list plus the grade below, so early readers get familiar words.
    grade_words = list(words[str(n) if n else "K"])
    if n >= 1:
        grade_words += words[str(n - 1) if n > 1 else "K"]

    def clean(seq: list[str]) -> list[str]:
        seen: dict[str, None] = {}
        for raw in seq:
            word = raw.upper()
            if word.isalpha() and word.isascii():
                seen.setdefault(word, None)
        return list(seen)

    return clean(interest_words(interests)), clean(grade_words)


def _try_place(
    grid: list[list[str]],
    word: str,
    dirs: list[tuple[int, int]],
    rng: random.Random,
) -> Placement | None:
    size = len(grid)
    options = []
    for d_row, d_col in dirs:
        for row in range(size):
            for col in range(size):
                end_r = row + d_row * (len(word) - 1)
                end_c = col + d_col * (len(word) - 1)
                if not (0 <= end_r < size and 0 <= end_c < size):
                    continue
                placement = Placement(word, row, col, d_row, d_col)
                cells = placement.cells()
                if all(grid[r][c] in ("", word[i]) for i, (r, c) in enumerate(cells)):
                    overlap = sum(
                        grid[r][c] == word[i] for i, (r, c) in enumerate(cells)
                    )
                    options.append((overlap, rng.random(), placement))
    if not options:
        return None
    # Prefer a little overlap (it makes the grid more interesting), then random.
    options.sort(key=lambda o: (-min(o[0], 1), o[1]))
    placement = options[0][2]
    for i, (r, c) in enumerate(placement.cells()):
        grid[r][c] = word[i]
    return placement


def generate(
    grade: str,
    seed: int,
    *,
    interests: str = "",
    size: int | None = None,
    count: int | None = None,
) -> WordSearch:
    """Build a word search for a grade (``"K"``, ``"1"`` … ``"5"``)."""
    rng = random.Random(seed)
    size = size or size_for_grade(grade)
    count = count or DEFAULT_WORD_COUNT.get(size, size - 2)
    dirs = directions_for_grade(grade)
    themed, graded = word_pool(grade, interests)
    max_len = size
    themed = [w for w in themed if 3 <= len(w) <= max_len]
    graded = [w for w in graded if 3 <= len(w) <= max_len]
    rng.shuffle(themed)
    rng.shuffle(graded)
    # Up to half the words come from the interests.
    picks = themed[: count // 2]
    candidates = picks + [w for w in graded if w not in picks] + themed[count // 2 :]
    # Longest first places more reliably.
    grid: list[list[str]] = [[""] * size for _ in range(size)]
    placements: list[Placement] = []
    chosen = sorted(candidates[:count], key=len, reverse=True)
    spare = iter(candidates[count:])
    queue = list(chosen)
    while queue and len(placements) < count:
        word = queue.pop(0)
        if any(word in p.word or p.word in word for p in placements):
            word = next(spare, "")
            if word:
                queue.append(word)
            continue
        placed = _try_place(grid, word, dirs, rng)
        if placed:
            placements.append(placed)
        elif (replacement := next(spare, None)) is not None:
            queue.append(replacement)
    letters = string.ascii_uppercase
    rows = tuple("".join(cell or rng.choice(letters) for cell in row) for row in grid)
    return WordSearch(size, rows, tuple(placements))


MAX_SIZE = 15


def generate_from_words(grade: str, seed: int, words: list[str]) -> WordSearch:
    """Hide exactly ``words`` (e.g. a spelling list); every one is placed.

    The grid starts at the grade's size (or the longest word) and grows a
    little if the words don't all fit.
    """
    clean = sorted(
        {w.upper() for w in words if w.isalpha() and len(w) >= 2},
        key=len,
        reverse=True,
    )
    if not clean:
        raise ValueError("no words to hide")
    longest = len(clean[0])
    if longest > MAX_SIZE:
        raise ValueError(f"words longer than {MAX_SIZE} letters don't fit")
    letters = sum(len(w) for w in clean)
    size = max(size_for_grade(grade), longest, math.ceil(math.sqrt(letters * 1.8)))
    dirs = directions_for_grade(grade)
    rng = random.Random(seed)
    for attempt in range(40):
        size_now = min(MAX_SIZE, size + attempt // 10)
        grid: list[list[str]] = [[""] * size_now for _ in range(size_now)]
        placements = []
        for word in clean:
            placed = _try_place(grid, word, dirs, rng)
            if not placed:
                break
            placements.append(placed)
        else:
            rows = tuple(
                "".join(cell or rng.choice(string.ascii_uppercase) for cell in row)
                for row in grid
            )
            return WordSearch(size_now, rows, tuple(placements))
    raise ValueError("too many words to fit in one grid")
