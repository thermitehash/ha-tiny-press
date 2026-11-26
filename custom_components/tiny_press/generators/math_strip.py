"""Math strip generator: ten problems plus one harder bonus.

Pure and deterministic for a given seed.

* K: add/subtract within 10.
* 1: add/subtract within 20.
* 2: two-digit add/subtract, every problem needs regrouping.
* 3: grade-2 style add/subtract, x/÷ facts to 10, simple word problems.
* 4: three-digit add/subtract, x/÷ to 12, two-digit x one-digit, word problems.
* 5: four-digit add/subtract, two-digit x two-digit, exact division, word problems.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import random

from ..profiles import grade_label, grade_number

ADD, SUB, MUL, DIV = "+", "−", "×", "÷"
NAMES = ("Sam", "Maya", "Leo", "Ava", "Max", "Zoe", "Ben", "Mia", "Eli", "Ivy")
ITEMS = ("stickers", "apples", "marbles", "shells", "books", "cookies", "crayons")


@dataclass(frozen=True, slots=True)
class Problem:
    """One problem and its answer."""

    a: int
    op: str
    b: int
    answer: int
    text: str | None = None  # word problems

    @property
    def vertical(self) -> bool:
        """Multi-digit add/subtract is written stacked, like on a worksheet."""
        return self.text is None and self.op in (ADD, SUB) and max(self.a, self.b) >= 10

    @property
    def inline(self) -> str:
        """``47 + 38 = ``."""
        return f"{self.a} {self.op} {self.b} ="

    def check(self) -> bool:
        """Recompute the answer."""
        match self.op:
            case "+":
                return self.a + self.b == self.answer
            case "−":
                return self.a - self.b == self.answer
            case "×":
                return self.a * self.b == self.answer
            case "÷":
                return self.b != 0 and self.a == self.b * self.answer
        return False

    def as_dict(self) -> dict[str, object]:
        """Answer-key data."""
        return {
            "a": self.a,
            "op": self.op,
            "b": self.b,
            "answer": self.answer,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class MathStrip:
    """A sheet of problems for one grade."""

    grade: str
    problems: tuple[Problem, ...]
    bonus: Problem

    def answer(self) -> dict[str, object]:
        """Answer-key data (stored for ``print_answers``)."""
        return {
            "grade": self.grade,
            "problems": [p.as_dict() for p in self.problems],
            "bonus": self.bonus.as_dict(),
        }


def _add(
    rng: random.Random,
    lo: int,
    hi: int,
    *,
    regroup: bool = False,
    max_total: int | None = None,
) -> Problem:
    while True:
        a, b = rng.randint(lo, hi), rng.randint(lo, hi)
        if regroup and (a % 10) + (b % 10) < 10:
            continue
        if max_total is None or a + b <= max_total:
            return Problem(a, ADD, b, a + b)


def _add_within(rng: random.Random, total: int) -> Problem:
    a = rng.randint(0, total)
    b = rng.randint(0, total - a)
    return Problem(a, ADD, b, a + b)


def _sub_within(rng: random.Random, total: int) -> Problem:
    a = rng.randint(1, total)
    b = rng.randint(0, a)
    return Problem(a, SUB, b, a - b)


def _sub(rng: random.Random, lo: int, hi: int, *, regroup: bool = False) -> Problem:
    while True:
        a, b = rng.randint(lo, hi), rng.randint(lo, hi)
        a, b = max(a, b), min(a, b)
        if a == b:
            continue
        if regroup and (a % 10) >= (b % 10):
            continue
        return Problem(a, SUB, b, a - b)


def _mul(
    rng: random.Random, a_range: tuple[int, int], b_range: tuple[int, int]
) -> Problem:
    a, b = rng.randint(*a_range), rng.randint(*b_range)
    return Problem(a, MUL, b, a * b)


def _div(
    rng: random.Random, q_range: tuple[int, int], d_range: tuple[int, int]
) -> Problem:
    q, d = rng.randint(*q_range), rng.randint(*d_range)
    return Problem(q * d, DIV, d, q)


def _word(rng: random.Random, base: Problem) -> Problem:
    name, item = rng.choice(NAMES), rng.choice(ITEMS)
    a, b = base.a, base.b
    match base.op:
        case "+":
            text = f"{name} has {a} {item} and finds {b} more. How many {item} does {name} have now?"
        case "−":
            text = f"{name} had {a} {item} and gave away {b}. How many {item} are left?"
        case "×":
            text = f"There are {a} bags with {b} {item} in each bag. How many {item} are there in all?"
        case _:
            text = f"{name} shares {a} {item} equally among {b} friends. How many {item} does each friend get?"
    return Problem(a, base.op, b, base.answer, text)


Maker = Callable[[random.Random], Problem]

MAKERS: dict[int, list[Maker]] = {
    0: [lambda r: _add_within(r, 10), lambda r: _sub_within(r, 10)],
    1: [lambda r: _add_within(r, 20), lambda r: _sub_within(r, 20)],
    2: [
        lambda r: _add(r, 11, 88, regroup=True, max_total=99),
        lambda r: _sub(r, 20, 99, regroup=True),
    ],
    3: [
        lambda r: _add(r, 15, 89, regroup=True, max_total=150),
        lambda r: _sub(r, 30, 99, regroup=True),
        lambda r: _mul(r, (2, 10), (2, 10)),
        lambda r: _div(r, (2, 10), (2, 10)),
    ],
    4: [
        lambda r: _add(r, 120, 699, regroup=True),
        lambda r: _sub(r, 200, 999, regroup=True),
        lambda r: _mul(r, (3, 12), (3, 12)),
        lambda r: _mul(r, (12, 99), (2, 9)),
        lambda r: _div(r, (3, 12), (3, 12)),
    ],
    5: [
        lambda r: _add(r, 1200, 6999, regroup=True),
        lambda r: _sub(r, 2000, 9999, regroup=True),
        lambda r: _mul(r, (12, 59), (11, 39)),
        lambda r: _div(r, (12, 99), (3, 9)),
    ],
}
# Word problems use friendly numbers from these makers.
WORD_MAKERS: dict[int, list[Maker]] = {
    3: [
        lambda r: _add(r, 12, 60),
        lambda r: _sub(r, 20, 90),
        lambda r: _mul(r, (2, 6), (2, 10)),
        lambda r: _div(r, (2, 10), (2, 5)),
    ],
    4: [
        lambda r: _add(r, 100, 500),
        lambda r: _mul(r, (3, 12), (3, 12)),
        lambda r: _div(r, (3, 12), (3, 9)),
    ],
    5: [
        lambda r: _mul(r, (12, 40), (3, 12)),
        lambda r: _div(r, (12, 60), (3, 9)),
        lambda r: _sub(r, 300, 999),
    ],
}
WORD_PROBLEMS = {3: 2, 4: 2, 5: 2}


def generate(grade: str, seed: int, count: int = 10) -> MathStrip:
    """Build ``count`` problems for a grade plus one bonus from the next grade up."""
    rng = random.Random(seed)
    n = grade_number(grade)
    words = WORD_PROBLEMS.get(n, 0)
    makers = MAKERS[n]
    problems: list[Problem] = []
    seen: set[tuple[int, str, int]] = set()
    plain = count - words
    i = 0
    while len(problems) < plain:
        problem = makers[i % len(makers)](rng)
        key = (problem.a, problem.op, problem.b)
        if key not in seen:
            seen.add(key)
            problems.append(problem)
            i += 1
    rng.shuffle(problems)
    # Display order: stacked problems first, then inline ones, then word problems.
    problems.sort(key=lambda p: 0 if p.vertical else 1)
    for j in range(words):
        maker = WORD_MAKERS[n][j % len(WORD_MAKERS[n])]
        problems.append(_word(rng, maker(rng)))
    harder = MAKERS[min(5, n + 1)]
    bonus = rng.choice(harder)(rng) if n < 5 else _mul(rng, (101, 499), (12, 49))
    return MathStrip(grade_label(n), tuple(problems), bonus)
