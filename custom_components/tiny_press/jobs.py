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
from .generators import (
    crossword,
    cryptogram,
    jokes,
    math_strip,
    maze,
    spelling,
    sudoku,
    word_search,
)
from .generators.jokes import Joke
from .generators.weather import WeatherReport
from .printer import escpos
from .profiles import Profile, grade_number
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


def answer_job(entry: dict) -> PrintJob:
    """Build the answer key for a stored puzzle (see ``TinyPressStore.history``)."""
    kind = entry["type"]
    data = entry["answer"]
    print_id = entry["print_id"]
    labels = {
        PrintType.MAZE: "Maze answers",
        PrintType.WORD_SEARCH: "Word search answers",
        PrintType.MATH: "Math answers",
        PrintType.KID_SUDOKU: "Sudoku answers",
        PrintType.SUDOKU: "Sudoku answers",
        PrintType.CROSSWORD: "Crossword answers",
        PrintType.CRYPTOGRAM: "Cryptogram answer",
        PrintType.SPELLING: "Spelling answers",
        PrintType.SPELLING_SEARCH: "Word search answers",
        PrintType.JOKE: "Joke answer",
        PrintType.FACT: "Fun fact",
    }
    footer = layout.Footer(labels.get(kind, "Answers"), print_id, _today())
    if kind == PrintType.MAZE:
        puzzle = maze.generate(data["difficulty"], data["seed"])

        def build(width: int) -> Canvas:
            return layout.maze_page(width, puzzle, footer, answer=True)

    elif kind == PrintType.WORD_SEARCH:
        grid = word_search.WordSearch(
            data["size"],
            tuple(data["grid"]),
            tuple(word_search.Placement(*p) for p in data["placements"]),
        )

        def build(width: int) -> Canvas:
            return layout.word_search_page(width, grid, footer, answer=True)

    elif kind == PrintType.MATH:
        sheet = math_strip.MathStrip(
            data["grade"],
            tuple(math_strip.Problem(**p) for p in data["problems"]),
            math_strip.Problem(**data["bonus"]),
        )

        def build(width: int) -> Canvas:
            return layout.math_page(width, sheet, footer, answer=True)

    elif kind == PrintType.CROSSWORD:
        cw = crossword.Crossword(
            data["rows"],
            data["cols"],
            tuple(crossword.Entry(*e) for e in data["entries"]),
        )

        def build(width: int) -> Canvas:
            return layout.crossword_page(width, cw, footer, answer=True)

    elif kind == PrintType.CRYPTOGRAM:
        cg = cryptogram.Cryptogram(
            data["plain"],
            data["author"],
            data["cipher"],
            dict(data["key"]),
            tuple(data["hints"]),
            -1,
        )

        def build(width: int) -> Canvas:
            return layout.cryptogram_page(width, cg, footer, answer=True)

    elif kind in (PrintType.KID_SUDOKU, PrintType.SUDOKU):
        grid_puzzle = sudoku.Sudoku(
            data["size"],
            tuple(tuple(r) for r in data["puzzle"]),
            tuple(tuple(r) for r in data["solution"]),
        )

        def build(width: int) -> Canvas:
            return layout.sudoku_page(width, grid_puzzle, footer, answer=True)

    elif kind == PrintType.SPELLING:
        sheet_s = spelling.SpellingSheet(
            tuple(data["words"]),
            tuple(data["scrambled"]),
            tuple(tuple(b) for b in data["blanks"]),
        )

        def build(width: int) -> Canvas:
            return layout.spelling_page(width, sheet_s, footer, answer=True)

    elif kind == PrintType.SPELLING_SEARCH:
        grid_s = word_search.WordSearch(
            data["size"],
            tuple(data["grid"]),
            tuple(word_search.Placement(*p) for p in data["placements"]),
        )

        def build(width: int) -> Canvas:
            return layout.word_search_page(width, grid_s, footer, answer=True)

    elif kind in (PrintType.JOKE, PrintType.FACT):
        setup, punchline = data["setup"], data.get("punchline")

        def build(width: int) -> Canvas:
            return layout.joke_answer_page(width, setup, punchline, footer)

    else:
        raise ValueError(f"no answer key for {kind}")
    return PrintJob(
        type="answers",
        label=footer.label,
        print_id=print_id,
        profile=None,
        response={"answers_for": kind},
        build=build,
    )


def weather_job(report: WeatherReport) -> PrintJob:
    """Build a weather print (current conditions + forecast)."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Weather", print_id, _today())
    return PrintJob(
        type=PrintType.WEATHER,
        label="Weather",
        print_id=print_id,
        response={
            "condition": report.condition,
            "temperature": report.temperature,
            "forecast_days": len(report.days),
        },
        build=lambda width: layout.weather_page(width, report, footer),
    )


KID_SUDOKU_LEVELS = {
    Difficulty.EASY: (4, "easy"),
    Difficulty.MEDIUM: (6, "easy"),
    Difficulty.HARD: (6, "hard"),
}


def kid_sudoku_level(profile: Profile) -> Difficulty:
    """Default level by grade: K-1 easy (4x4), 2-3 medium, 4-5 hard (6x6)."""
    n = grade_number(profile.puzzle_grade)
    return (
        Difficulty.EASY if n <= 1 else Difficulty.MEDIUM if n <= 3 else Difficulty.HARD
    )


def kid_sudoku_job(
    profile: Profile,
    difficulty: Difficulty | None = None,
    seed: int | None = None,
) -> PrintJob:
    """Build a 4x4 or 6x6 number sudoku."""
    seed = new_seed() if seed is None else seed
    print_id = _id("kid_sudoku", seed)
    level = difficulty or kid_sudoku_level(profile)
    size, givens = KID_SUDOKU_LEVELS[level]
    puzzle = sudoku.generate(size, givens, seed)
    footer = layout.Footer("Sudoku", print_id, _today(), f"{size}x{size}")
    answer = {**puzzle.answer(), "seed": seed}
    return PrintJob(
        type=PrintType.KID_SUDOKU,
        label="Sudoku",
        print_id=print_id,
        difficulty=level.value,
        profile=profile.name,
        answers=(
            {"print_id": print_id, "type": PrintType.KID_SUDOKU, "answer": answer},
        ),
        build=lambda width: layout.sudoku_page(width, puzzle, footer),
    )


def spelling_words_for(profile: Profile, words: list[str] | str | None) -> list[str]:
    """Words from the action, else the profile's list; raise if there are none."""
    found = spelling.parse_words(words) or spelling.parse_words(profile.spelling_words)
    if not found:
        raise ValueError("no spelling words")
    return found


def spelling_job(
    profile: Profile, words: list[str], seed: int | None = None
) -> PrintJob:
    """Build unscramble and missing-letter practice for a spelling list."""
    seed = new_seed() if seed is None else seed
    print_id = _id("spelling", seed)
    sheet = spelling.generate(words, seed)
    footer = layout.Footer("Spelling", print_id, _today(), f"{len(words)} words")
    return PrintJob(
        type=PrintType.SPELLING,
        label="Spelling",
        print_id=print_id,
        profile=profile.name,
        answers=(
            {
                "print_id": print_id,
                "type": PrintType.SPELLING,
                "answer": {**sheet.answer(), "seed": seed},
            },
        ),
        build=lambda width: layout.spelling_page(width, sheet, footer),
    )


def spelling_search_job(
    profile: Profile, words: list[str], seed: int | None = None
) -> PrintJob:
    """Build a word search that hides exactly the spelling words."""
    seed = new_seed() if seed is None else seed
    print_id = _id("spelling_search", seed)
    grade = profile.puzzle_grade
    puzzle = word_search.generate_from_words(grade, seed, words)
    footer = layout.Footer("Spelling search", print_id, _today(), f"Grade {grade}")
    return PrintJob(
        type=PrintType.SPELLING_SEARCH,
        label="Spelling search",
        print_id=print_id,
        profile=profile.name,
        answers=(
            {
                "print_id": print_id,
                "type": PrintType.SPELLING_SEARCH,
                "answer": {**puzzle.answer(), "seed": seed, "grade": grade},
            },
        ),
        build=lambda width: layout.word_search_page(width, puzzle, footer),
    )


def sudoku_job(
    difficulty: Difficulty, seed: int | None = None, profile: str | None = None
) -> PrintJob:
    """Build a 9x9 sudoku graded by the techniques it needs."""
    seed = new_seed() if seed is None else seed
    print_id = _id("sudoku", seed)
    puzzle = sudoku.generate_graded(difficulty.value, seed)
    footer = layout.Footer("Sudoku", print_id, _today(), difficulty)
    answer = {**puzzle.answer(), "seed": seed, "difficulty": difficulty.value}
    return PrintJob(
        type=PrintType.SUDOKU,
        label="Sudoku",
        print_id=print_id,
        difficulty=difficulty.value,
        profile=profile,
        answers=({"print_id": print_id, "type": PrintType.SUDOKU, "answer": answer},),
        build=lambda width: layout.sudoku_page(width, puzzle, footer),
    )


def crossword_job(
    difficulty: Difficulty, seed: int | None = None, profile: str | None = None
) -> PrintJob:
    """Build a criss-cross crossword."""
    seed = new_seed() if seed is None else seed
    print_id = _id("crossword", seed)
    puzzle = crossword.generate(difficulty.value, seed)
    footer = layout.Footer("Crossword", print_id, _today(), difficulty)
    answer = {**puzzle.answer(), "seed": seed, "difficulty": difficulty.value}
    return PrintJob(
        type=PrintType.CROSSWORD,
        label="Crossword",
        print_id=print_id,
        difficulty=difficulty.value,
        profile=profile,
        answers=(
            {"print_id": print_id, "type": PrintType.CROSSWORD, "answer": answer},
        ),
        build=lambda width: layout.crossword_page(width, puzzle, footer),
    )


def cryptogram_job(
    difficulty: Difficulty,
    seed: int | None = None,
    profile: str | None = None,
    recent: list[int] | None = None,
) -> PrintJob:
    """Build a cryptogram from a bundled public-domain quote."""
    seed = new_seed() if seed is None else seed
    print_id = _id("cryptogram", seed)
    puzzle = cryptogram.generate(difficulty.value, seed, recent)
    footer = layout.Footer("Cryptogram", print_id, _today(), difficulty)
    return PrintJob(
        type=PrintType.CRYPTOGRAM,
        label="Cryptogram",
        print_id=print_id,
        difficulty=difficulty.value,
        profile=profile,
        answers=(
            {
                "print_id": print_id,
                "type": PrintType.CRYPTOGRAM,
                "answer": {**puzzle.answer(), "seed": seed},
            },
        ),
        response={"quote_index": puzzle.index},
        build=lambda width: layout.cryptogram_page(width, puzzle, footer),
    )


def puzzle_pack_job(
    difficulty: Difficulty,
    sudoku_difficulty: Difficulty,
    seed: int | None = None,
    profile: str | None = None,
    recent: list[int] | None = None,
) -> PrintJob:
    """Sudoku + crossword + cryptogram in one job (one cut)."""
    seed = new_seed() if seed is None else seed
    rng = random.Random(f"puzzle-pack-{seed}")
    parts = [
        sudoku_job(sudoku_difficulty, rng.randrange(2**31), profile),
        crossword_job(difficulty, rng.randrange(2**31), profile),
        cryptogram_job(difficulty, rng.randrange(2**31), profile, recent),
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
        type=PrintType.PUZZLE_PACK,
        label="Puzzle pack",
        print_id=parts[0].print_id,
        difficulty=difficulty.value,
        profile=profile,
        answers=tuple(a for part in parts for a in part.answers),
        response={
            "print_ids": [part.print_id for part in parts],
            "quote_index": parts[2].response["quote_index"],
        },
        build=build,
    )
