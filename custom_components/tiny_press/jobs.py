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
from .coordinator import PrintJob, Section
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
from .generators.feeds import Feed
from .generators.history import HistoryReport
from .generators.jokes import Joke
from .generators.morning import MorningSlip
from .generators.observances import Theme
from .generators.story import Story
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
    difficulty: Difficulty,
    seed: int | None = None,
    profile: str | None = None,
    theme: Theme | None = None,
    who: str | None = None,
) -> PrintJob:
    """Build a maze print (themed, and titled with the kid's name, when given)."""
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
        build=lambda width: layout.maze_page(
            width, puzzle, footer, theme=theme, who=who
        ),
    )


def word_search_job(
    profile: Profile, seed: int | None = None, theme: Theme | None = None
) -> PrintJob:
    """Build a word search for a kid profile (some words from the theme)."""
    seed = new_seed() if seed is None else seed
    print_id = _id("word_search", seed)
    grade = profile.puzzle_grade
    puzzle = word_search.generate(
        grade,
        seed,
        interests=profile.interests,
        theme_words=theme.words if theme else (),
    )
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
        build=lambda width: layout.word_search_page(
            width, puzzle, footer, who=profile.display_name
        ),
    )


def math_job(profile: Profile, seed: int | None = None) -> PrintJob:
    """Build a math strip for a kid profile."""
    seed = new_seed() if seed is None else seed
    print_id = _id("math", seed)
    grade = profile.math_level
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
        build=lambda width: layout.math_page(
            width, sheet, footer, who=profile.display_name
        ),
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
        build=lambda width: layout.joke_page(width, joke, footer, profile.display_name),
    )


def kid_pack_job(
    profile: Profile,
    maze_difficulty: Difficulty,
    seed: int | None = None,
    theme: Theme | None = None,
) -> PrintJob:
    """Maze + word search + math strip in one job (one cut)."""
    seed = new_seed() if seed is None else seed
    rng = random.Random(f"kid-pack-{seed}")
    parts = [
        maze_job(
            maze_difficulty,
            rng.randrange(2**31),
            profile.name,
            theme,
            profile.display_name,
        ),
        word_search_job(profile, rng.randrange(2**31), theme),
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
    footer = layout.Footer("Test page", print_id, _today(), show_id=False)
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
    footer = layout.Footer("Note", print_id, _today(), show_id=False)
    return PrintJob(
        type="text",
        label="Note",
        print_id=print_id,
        build=lambda width: layout.text_page(width, text, title, size, footer),
    )


def image_job(path: Path) -> PrintJob:
    """Build a picture print from /media or /config/www."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Picture", print_id, _today(), show_id=False)
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
    footer = layout.Footer("Weather", print_id, _today(), show_id=False)
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
    """Default level by math grade: K-1 easy (4x4), 2-3 medium, 4-5 hard (6x6)."""
    n = grade_number(profile.math_level)
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
        build=lambda width: layout.sudoku_page(
            width, puzzle, footer, who=profile.display_name
        ),
    )


def spelling_words_for(
    profile: Profile,
    words: list[str] | str | None,
    todo_words: list[str] | None = None,
) -> list[str]:
    """Words from the action, else the kid's spelling to-do list."""
    found = spelling.parse_words(words) or spelling.parse_words(todo_words)
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
    footer = layout.Footer("Spelling", print_id, _today(), f"{len(sheet.words)} words")
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
        build=lambda width: layout.spelling_page(
            width, sheet, footer, who=profile.display_name
        ),
    )


def spelling_search_job(
    profile: Profile, words: list[str], seed: int | None = None
) -> PrintJob:
    """Build a word search that hides exactly the spelling words."""
    seed = new_seed() if seed is None else seed
    print_id = _id("spelling_search", seed)
    grade = profile.puzzle_grade
    puzzle = word_search.generate_from_words(
        grade, seed, spelling.pick_words(words, seed)
    )
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
        build=lambda width: layout.word_search_page(
            width, puzzle, footer, who=profile.display_name
        ),
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
    difficulty: Difficulty,
    seed: int | None = None,
    profile: str | None = None,
    theme: Theme | None = None,
) -> PrintJob:
    """Build a criss-cross crossword (a few themed entries when given a theme)."""
    seed = new_seed() if seed is None else seed
    print_id = _id("crossword", seed)
    extra = [{"word": w, "clue": c} for w, c in theme.clues.items()] if theme else None
    puzzle = crossword.generate(difficulty.value, seed, extra)
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
    *,
    theme: Theme | None = None,
) -> PrintJob:
    """Sudoku + crossword + cryptogram in one job (one cut)."""
    seed = new_seed() if seed is None else seed
    rng = random.Random(f"puzzle-pack-{seed}")
    parts = [
        sudoku_job(sudoku_difficulty, rng.randrange(2**31), profile),
        crossword_job(difficulty, rng.randrange(2**31), profile, theme),
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


def story_job(story: Story, profile: Profile, length: str) -> PrintJob:
    """Build a bedtime story (or serial chapter) print."""
    print_id = layout.make_print_id()
    label = f"Chapter {story.chapter}" if story.chapter else "Story"
    footer = layout.Footer(label, print_id, _today(), length, show_id=False)
    return PrintJob(
        type=PrintType.STORY,
        label=label,
        print_id=print_id,
        difficulty=length,
        profile=profile.name,
        response={
            "title": story.title,
            "chapter": story.chapter,
            "choices": dict(zip("AB", story.choices, strict=False)) or None,
            "source": story.source,
            "words": story.words,
        },
        build=lambda width: layout.story_page(width, story, footer),
    )


def morning_job(slip: MorningSlip) -> PrintJob:
    """Build the morning slip (with an answer key if it has a puzzle)."""
    print_id = layout.make_print_id()
    footer = layout.Footer(
        "Morning slip", print_id, slip.day, show_id=slip.puzzle is not None
    )
    answers: tuple[dict, ...] = ()
    if slip.puzzle is not None:
        answers = (
            {
                "print_id": print_id,
                "type": PrintType.SUDOKU,
                "answer": slip.puzzle.answer(),
            },
        )
    return PrintJob(
        type=PrintType.MORNING_SLIP,
        label="Morning slip",
        print_id=print_id,
        answers=answers,
        response={
            "events": len(slip.events) + slip.more_events,
            "weather": slip.weather.condition if slip.weather else None,
            "todos": sum(len(items) for _n, items in slip.todos),
        },
        build=lambda width: layout.morning_page(width, slip, footer),
    )


def history_job(report: HistoryReport) -> PrintJob:
    """Build a sensor-history print."""
    print_id = layout.make_print_id()
    footer = layout.Footer("History", print_id, _today(), show_id=False)
    return PrintJob(
        type=PrintType.HISTORY,
        label="History",
        print_id=print_id,
        response={
            "entities": [s.entity_id for s in report.series],
            "start": report.start.isoformat(),
            "end": report.end.isoformat(),
            "empty": [s.entity_id for s in report.series if s.empty],
        },
        build=lambda width: layout.history_page(
            width, report, footer, dt_util.as_local
        ),
    )


# Bytes a Model 2 QR code holds at error-correction level M, by version.
_QR_M_BYTES = (14, 26, 42, 62, 84, 106, 122, 152, 180, 213, 251, 287, 331, 362)
QR_MODULE = 3  # dots per module: small but phone-readable
MAX_QR_LINK = 300


def qr_mm(link: str, module: int = QR_MODULE) -> float:
    """Paper a native QR code for ``link`` uses, plus a little space."""
    size = len(link.encode("utf-8"))
    version = next(
        (v for v, cap in enumerate(_QR_M_BYTES, start=1) if size <= cap),
        len(_QR_M_BYTES),
    )
    modules = 17 + 4 * version + 8  # plus the quiet zone
    return round(modules * module / 8 + 2, 1)


def _qr_bytes(link: str) -> bytes:
    return (
        escpos.align("center")
        + escpos.qr_code(link, module=QR_MODULE)
        + escpos.align("left")
    )


def feed_job(
    name: str, feed: Feed, items: int, qr: bool = False, label: str = "Feed"
) -> PrintJob:
    """Build a feed print: newest headlines, with an optional QR per item."""
    print_id = layout.make_print_id()
    footer = layout.Footer(label, print_id, _today(), show_id=False)
    shown = feed.items[:items]
    printed_at = dt_util.utcnow()

    def sections(width: int) -> list[Section]:
        out = []
        for canvas, link in layout.feed_parts(
            width,
            name,
            shown,
            footer,
            to_local=dt_util.as_local,
            printed_at=printed_at,
            qr=qr,
        ):
            if link and len(link) <= MAX_QR_LINK:
                out.append(Section(canvas, _qr_bytes(link), qr_mm(link)))
            else:
                out.append(Section(canvas))
        return out

    def build(width: int) -> Canvas:
        canvas = Canvas(width)
        for part, _link in layout.feed_parts(
            width, name, shown, footer, to_local=dt_util.as_local, printed_at=printed_at
        ):
            canvas.blocks.extend(part.blocks)
        return canvas

    return PrintJob(
        type=PrintType.FEED,
        label=label,
        print_id=print_id,
        build=build,
        sections=sections if qr else None,
        response={
            "feed": name,
            "items": len(shown),
            "headlines": [item.title for item in shown],
        },
    )
