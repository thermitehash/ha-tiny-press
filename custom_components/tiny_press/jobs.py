"""Print jobs: generator output + layout + footer + answer keys.

Builders that run generators or read bundled data are meant to be called in
the executor (``TinyPressCoordinator.async_print`` accepts a builder).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import random

from homeassistant.util import dt as dt_util

from .const import PAPER_80MM, Difficulty, PrintType
from .coordinator import PrintJob
from .generators import jokes, math_strip, maze, word_search
from .generators.jokes import Joke
from .printer import escpos
from .profiles import Profile
from .render import layout
from .render.canvas import Canvas

REPO_URL = "https://github.com/thermitehash/ha-tiny-press"
QR_MM = 32.0  # approximate paper used by the test page's native QR code


def new_seed() -> int:
    """Return a random seed for when the caller didn't pass one."""
    return random.SystemRandom().randrange(2**31)


def _today() -> date:
    return dt_util.now().date()


def _id(kind: str, seed: int) -> str:
    """Derive the print ID from type and seed, so a re-print matches its key."""
    return layout.make_print_id(random.Random(f"{kind}-{seed}"))


def _grade_label(grade: str) -> str:
    return f"Grade {grade}"


def maze_job(
    difficulty: Difficulty, seed: int | None = None, profile: str | None = None
) -> PrintJob:
    """Build a maze print."""
    seed = new_seed() if seed is None else seed
    print_id = _id("maze", seed)
    puzzle = maze.generate(difficulty, seed)
    footer = layout.Footer("Maze", print_id, _today(), difficulty)
    answer = {**puzzle.answer(), "seed": seed, "difficulty": difficulty.value}
    return PrintJob(
        type=PrintType.MAZE,
        label="Maze",
        print_id=print_id,
        difficulty=difficulty.value,
        profile=profile,
        answers=({"print_id": print_id, "type": PrintType.MAZE, "answer": answer},),
        build=lambda width: layout.maze_page(width, puzzle, footer),
    )


def word_search_job(profile: Profile, seed: int | None = None) -> PrintJob:
    """Build a word search for a kid profile."""
    seed = new_seed() if seed is None else seed
    print_id = _id("word_search", seed)
    grade = profile.puzzle_grade
    puzzle = word_search.generate(grade, seed, interests=profile.interests)
    footer = layout.Footer("Word search", print_id, _today(), _grade_label(grade))
    answer = {**puzzle.answer(), "seed": seed, "grade": grade}
    return PrintJob(
        type=PrintType.WORD_SEARCH,
        label="Word search",
        print_id=print_id,
        difficulty=_grade_label(grade),
        profile=profile.name,
        answers=(
            {"print_id": print_id, "type": PrintType.WORD_SEARCH, "answer": answer},
        ),
        build=lambda width: layout.word_search_page(width, puzzle, footer),
    )


def math_job(profile: Profile, seed: int | None = None) -> PrintJob:
    """Build a math strip for a kid profile."""
    seed = new_seed() if seed is None else seed
    print_id = _id("math", seed)
    grade = profile.puzzle_grade
    sheet = math_strip.generate(grade, seed)
    footer = layout.Footer("Math", print_id, _today(), _grade_label(grade))
    answer = {**sheet.answer(), "seed": seed}
    return PrintJob(
        type=PrintType.MATH,
        label="Math",
        print_id=print_id,
        difficulty=_grade_label(grade),
        profile=profile.name,
        answers=({"print_id": print_id, "type": PrintType.MATH, "answer": answer},),
        build=lambda width: layout.math_page(width, sheet, footer),
    )


def offline_joke(kind: str, seed: int | None, recent: list[int]) -> Joke:
    """Pick a bundled joke or fact (executor: may read the data file)."""
    return jokes.pick(kind, new_seed() if seed is None else seed, recent)


def joke_job(joke: Joke, profile: Profile) -> PrintJob:
    """Build a joke or fun-fact print."""
    print_id = layout.make_print_id()
    kind = PrintType.JOKE if joke.kind == jokes.JOKE else PrintType.FACT
    footer = layout.Footer(
        "Joke" if kind is PrintType.JOKE else "Fun fact", print_id, _today()
    )
    return PrintJob(
        type=kind,
        label=footer.label,
        print_id=print_id,
        profile=profile.name,
        answers=({"print_id": print_id, "type": kind, "answer": joke.answer()},),
        response={
            "setup": joke.setup,
            "punchline": joke.punchline,
            "source": joke.source,
        },
        build=lambda width: layout.joke_page(width, joke, footer),
    )


def kid_pack_job(
    profile: Profile, maze_difficulty: Difficulty, seed: int | None = None
) -> PrintJob:
    """Maze + word search + math strip in one job (one cut)."""
    seed = new_seed() if seed is None else seed
    rng = random.Random(f"kid-pack-{seed}")
    parts = [
        maze_job(maze_difficulty, rng.randrange(2**31), profile.name),
        word_search_job(profile, rng.randrange(2**31)),
        math_job(profile, rng.randrange(2**31)),
    ]

    def build(width: int) -> Canvas:
        canvas = Canvas(width)
        for i, part in enumerate(parts):
            if i:
                canvas.space(10)
                canvas.rule(dashed=True, thickness=3, pad=16)
                canvas.space(10)
            canvas.extend(part.build(width))
        return canvas

    return PrintJob(
        type=PrintType.KID_PACK,
        label="Kid pack",
        print_id=parts[0].print_id,
        difficulty=_grade_label(profile.puzzle_grade),
        profile=profile.name,
        answers=tuple(a for part in parts for a in part.answers),
        response={"print_ids": [part.print_id for part in parts]},
        build=build,
    )


def test_page_job(paper: str, info: dict[str, str]) -> PrintJob:
    """Build the test page: fonts, dither ramp, settings and a native QR code."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Test page", print_id, _today())
    return PrintJob(
        type=PrintType.TEST_PAGE,
        label="Test page",
        print_id=print_id,
        build=lambda width: layout.test_page(width, info, footer),
        extra=escpos.align("center")
        + escpos.qr_code(REPO_URL, module=5 if paper == PAPER_80MM else 4)
        + escpos.feed(1)
        + escpos.align("left"),
        extra_mm=QR_MM,
    )


def text_job(text: str, title: str | None, size: str) -> PrintJob:
    """Build a free-text note."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Note", print_id, _today())
    return PrintJob(
        type="text",
        label="Note",
        print_id=print_id,
        build=lambda width: layout.text_page(width, text, title, size, footer),
    )


def image_job(path: Path) -> PrintJob:
    """Build a picture print from /media or /config/www."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Picture", print_id, _today())
    return PrintJob(
        type="image",
        label="Picture",
        print_id=print_id,
        build=lambda width: layout.image_page(width, path, footer),
    )
