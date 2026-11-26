"""Page layouts: turn generator output into canvases.

Everything here is synchronous Pillow work; run it in the executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import itertools
import math
from pathlib import Path
import random
from typing import Any

from PIL import Image, ImageDraw

from ..generators.crossword import Crossword
from ..generators.cryptogram import Cryptogram
from ..generators.feeds import FeedItem
from ..generators.history import (
    HistoryReport,
    Series,
    bucket_rows,
    changes,
    state_totals,
    summarize,
)
from ..generators.jokes import Joke
from ..generators.math_strip import MathStrip, Problem
from ..generators.maze import Maze
from ..generators.morning import MorningSlip
from ..generators.observances import Theme
from ..generators.spelling import SpellingSheet
from ..generators.story import Story
from ..generators.sudoku import Sudoku
from ..generators.weather import WeatherReport, condition_label
from ..generators.word_search import WordSearch
from .canvas import MARGIN, Canvas, font, wrap

# No 0/O, 1/I/L, 5/S, 2/Z, 8/B: the ID is read off paper by a person.
ID_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"
TEXT_PX = {"small": 22, "normal": 28, "large": 40}


def make_print_id(rng: random.Random | None = None) -> str:
    """Return a short ID like ``K7Q2``."""
    rng = rng or random.SystemRandom()
    return "".join(rng.choice(ID_ALPHABET) for _ in range(4))


@dataclass(frozen=True, slots=True)
class Footer:
    """The small line at the bottom of every printout."""

    label: str
    print_id: str
    day: date
    difficulty: str | None = None
    show_id: bool = True  # only prints with an answer key show their ID

    def fields(self) -> tuple[str, ...]:
        """Footer pieces in print order."""
        return (
            self.label,
            self.difficulty.title() if self.difficulty else "",
            self.day.strftime("%b %-d, %Y"),
            f"#{self.print_id}" if self.show_id else "",
        )


def text_page(
    width: int, text: str, title: str | None, size: str, footer: Footer
) -> Canvas:
    """Free text with an optional title."""
    canvas = Canvas(width)
    if title:
        canvas.title(title)
        canvas.space(12)
    canvas.text(text, px=TEXT_PX.get(size, TEXT_PX["normal"]))
    canvas.space(16)
    canvas.footer(*footer.fields())
    return canvas


def image_page(width: int, path: Path, footer: Footer) -> Canvas:
    """Lay out a picture from disk, dithered to 1-bit."""
    canvas = Canvas(width)
    with Image.open(path) as img:
        img.load()
        canvas.image(img)
    canvas.space(12)
    canvas.footer(*footer.fields())
    return canvas


def test_page(width: int, info: dict[str, str], footer: Footer) -> Canvas:
    """Fonts, rules, a dither ramp and printer details."""
    canvas = Canvas(width)
    canvas.title("Tiny Press")
    canvas.text("Test page", px=28, align="center")
    canvas.rule()
    canvas.text("Atkinson Hyperlegible: The quick brown fox jumps over the lazy dog.")
    canvas.text("Bold 1Il 0Oo 5S 8B", px=28, bold=True)
    canvas.text("JetBrains Mono: 0123456789 ABC", px=24, family="mono")
    canvas.space(8)
    # A light-to-white ramp shows the dithering. It stops short of solid black:
    # dense black rows make a thermal printer slow down noticeably.
    ramp = Image.new("L", (canvas.inner, 28))
    draw = ImageDraw.Draw(ramp)
    for x in range(canvas.inner):
        draw.line((x, 0, x, 27), fill=round(96 + 159 * x / (canvas.inner - 1)))
    canvas.image(ramp)
    canvas.space(8)
    canvas.rule(dashed=True)
    for key, value in info.items():
        canvas.text(f"{key}: {value}", px=22, family="mono")
    canvas.space(8)
    canvas.footer(*footer.fields())
    return canvas


def _star(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.45
        ang = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def maze_drawing(width: int, maze: Maze, *, show_solution: bool = False) -> Image.Image:
    """Draw a maze centered on a ``width``-wide strip."""
    inner = width - 2 * MARGIN
    cell = min(inner // maze.cols, 72)
    wall = max(3, cell // 12)
    grid_w, grid_h = cell * maze.cols, cell * maze.rows
    top = cell  # room for the start marker above the grid
    img = Image.new("L", (width, grid_h + 2 * cell), 255)
    draw = ImageDraw.Draw(img)
    x0 = (width - grid_w) // 2

    def xy(col: int, row: int) -> tuple[int, int]:
        return x0 + col * cell, top + row * cell

    half = wall // 2
    for row in range(maze.rows):
        for col in range(maze.cols):
            x, y = xy(col, row)
            here = (col, row)
            # Top wall (open above the start cell).
            if row == 0 and here != maze.start:
                draw.rectangle((x - half, y - half, x + cell + half, y + half), fill=0)
            # Left wall.
            if col == 0 or not maze.is_open(here, (col - 1, row)):
                draw.rectangle((x - half, y - half, x + half, y + cell + half), fill=0)
            # Bottom wall (open below the finish cell).
            below = (col, row + 1)
            if (row == maze.rows - 1 and here != maze.finish) or (
                row < maze.rows - 1 and not maze.is_open(here, below)
            ):
                yb = y + cell
                draw.rectangle(
                    (x - half, yb - half, x + cell + half, yb + half), fill=0
                )
            # Right wall on the last column.
            if col == maze.cols - 1:
                xr = x + cell
                draw.rectangle(
                    (xr - half, y - half, xr + half, y + cell + half), fill=0
                )

    if show_solution and maze.solution:
        pts = [
            (xy(c, r)[0] + cell / 2, xy(c, r)[1] + cell / 2) for c, r in maze.solution
        ]
        draw.line(pts, fill=0, width=max(3, cell // 6), joint="curve")

    # Start: a filled circle above the entrance. Finish: a star below the exit.
    sx, sy = xy(*maze.start)
    r = cell * 0.32
    draw.ellipse(
        (sx + cell / 2 - r, sy - cell / 2 - r, sx + cell / 2 + r, sy - cell / 2 + r),
        fill=0,
    )
    fx, fy = xy(*maze.finish)
    draw.polygon(_star(fx + cell / 2, fy + cell * 1.5, cell * 0.42), fill=0)
    return img


def kid_title(title: str, who: str | None) -> str:
    """Title a print for a kid: "Maze" becomes "Rosie's maze" (or "James' maze")."""
    if not who:
        return title
    owner = f"{who}'" if who.endswith(("s", "S")) else f"{who}'s"
    return f"{owner} {title[:1].lower()}{title[1:]}"


ART_MAX_PX = 26


def ascii_art(width: int, lines: tuple[str, ...], px: int = ART_MAX_PX) -> Image.Image:
    """Monospaced ASCII art, centered, as a drawing.

    Bold and slightly thickened, as large as fits (up to ``px``): thin
    anti-aliased strokes come out faint once the page is turned into 1-bit
    printer dots.
    """
    cols = max((len(line) for line in lines), default=1) or 1
    room = width - 2 * MARGIN - 4
    while px > 12 and font("mono", px, True).getlength("M") * cols > room:
        px -= 1
    face = font("mono", px, True)
    stroke = 1 if px >= 16 else 0
    ascent, descent = face.getmetrics()
    line_h = ascent + descent + 2 * stroke
    advance = face.getlength("M")  # monospaced
    widest = cols * advance
    img = Image.new("L", (width, line_h * len(lines) + 4 + 2 * stroke), 255)
    draw = ImageDraw.Draw(img)
    left = max(MARGIN, (width - widest) / 2)
    for i, line in enumerate(lines):
        # One character at a time, so the font can't join "_|_" or "-|" into
        # ligatures.
        for j, ch in enumerate(line):
            if ch != " ":
                draw.text(
                    (left + j * advance, i * line_h + stroke),
                    ch,
                    font=face,
                    fill=0,
                    stroke_width=stroke,
                    stroke_fill=0,
                )
    return img


def maze_page(
    width: int,
    maze: Maze,
    footer: Footer,
    *,
    answer: bool = False,
    theme: Theme | None = None,
    who: str | None = None,
) -> Canvas:
    """Lay out a maze printout (or its answer key), themed when given one."""
    canvas = Canvas(width)
    if theme is not None and theme.art and not answer:
        canvas.drawing(ascii_art(width, theme.art, px=22))
    name = f"{theme.name} maze" if theme is not None and not answer else "Maze"
    canvas.title("Maze answer" if answer else kid_title(name, who))
    canvas.text("Start at the dot. Find the star!", px=24, align="center")
    canvas.space(4)
    canvas.drawing(maze_drawing(width, maze, show_solution=answer))
    canvas.footer(*footer.fields())
    return canvas


def word_search_drawing(
    width: int, puzzle: WordSearch, *, show_answers: bool = False
) -> Image.Image:
    """Draw the letter grid (answers as black bars with white letters)."""
    inner = width - 2 * MARGIN
    cell = min(inner // puzzle.size, 52)
    face = font("mono", int(cell * 0.62), True)
    grid_w = cell * puzzle.size
    x0 = (width - grid_w) // 2
    img = Image.new("L", (width, grid_w + 8), 255)
    draw = ImageDraw.Draw(img)

    def center(row: int, col: int) -> tuple[float, float]:
        return x0 + col * cell + cell / 2, 4 + row * cell + cell / 2

    marked: set[tuple[int, int]] = set()
    if show_answers:
        bar = int(cell * 0.78)
        for placement in puzzle.placements:
            cells = placement.cells()
            marked.update(cells)
            start, end = center(*cells[0]), center(*cells[-1])
            draw.line((start, end), fill=0, width=bar)
            for cx, cy in (start, end):
                draw.ellipse(
                    (cx - bar / 2, cy - bar / 2, cx + bar / 2, cy + bar / 2), fill=0
                )
    for row, letters in enumerate(puzzle.grid):
        for col, letter in enumerate(letters):
            cx, cy = center(row, col)
            fill = 255 if (row, col) in marked else 0
            draw.text((cx, cy), letter, font=face, fill=fill, anchor="mm")
    return img


def _checkbox_columns(width: int, words: list[str], px: int = 26) -> Image.Image:
    """Words in two columns, each with an empty box to tick."""
    inner = width - 2 * MARGIN
    cols = 2
    face = font("sans", px, True)
    line_h = int(px * 1.45)
    rows = (len(words) + cols - 1) // cols
    img = Image.new("L", (width, rows * line_h + 4), 255)
    draw = ImageDraw.Draw(img)
    col_w = inner // cols
    box = int(px * 0.75)
    for i, word in enumerate(words):
        col, row = divmod(i, rows)
        x = MARGIN + col * col_w + 6
        y = row * line_h + 4
        draw.rectangle((x, y + 3, x + box, y + 3 + box), outline=0, width=2)
        draw.text((x + box + 12, y), word, font=face, fill=0)
    return img


def word_search_page(
    width: int,
    puzzle: WordSearch,
    footer: Footer,
    *,
    answer: bool = False,
    who: str | None = None,
) -> Canvas:
    """Lay out a word search (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Word search answers" if answer else kid_title("Word search", who))
    canvas.space(6)
    canvas.drawing(word_search_drawing(width, puzzle, show_answers=answer))
    canvas.space(10)
    canvas.drawing(_checkbox_columns(width, puzzle.words))
    canvas.footer(*footer.fields())
    return canvas


def _vertical_problem(
    num: int, problem: Problem, col_w: int, px: int, show: bool
) -> Image.Image:
    """Draw a stacked problem: label, two rows, a line and room to answer."""
    face = font("mono", px, True)
    small = font("sans", int(px * 0.5), True)
    char_w = face.getlength("0")
    digits = max(len(str(problem.a)), len(str(problem.b)), len(str(problem.answer)))
    right = col_w - 18
    row_h = int(px * 1.15)
    img = Image.new("L", (col_w, row_h * 3 + 22), 255)
    draw = ImageDraw.Draw(img)
    draw.text((4, 0), f"{num}.", font=small, fill=0)
    draw.text((right, 0), str(problem.a), font=face, fill=0, anchor="ra")
    draw.text((right, row_h), str(problem.b), font=face, fill=0, anchor="ra")
    left = right - char_w * (digits + 1.3)
    draw.text((left, row_h), problem.op, font=face, fill=0, anchor="la")
    line_y = row_h * 2 + 6
    draw.rectangle((left, line_y, right, line_y + 3), fill=0)
    if show:
        draw.text(
            (right, line_y + 10), str(problem.answer), font=face, fill=0, anchor="ra"
        )
    return img


def _inline_problem(
    num: int,
    problem: Problem,
    col_w: int,
    px: int,
    show: bool,
    *,
    label: str | None = None,
) -> Image.Image:
    answer = str(problem.answer) if show else "____"
    body = f"{problem.inline} {answer}"
    height = int(px * 1.6)
    # Shrink until the problem fits its column.
    while True:
        face = font("mono", px, True)
        small = font("sans", max(14, int(px * 0.5)), True)
        x = 4 + small.getlength(label or "10.") + 10
        if x + face.getlength(body) <= col_w - 6 or px <= 18:
            break
        px -= 2
    img = Image.new("L", (col_w, height), 255)
    draw = ImageDraw.Draw(img)
    draw.text((4, int(px * 0.25)), label or f"{num}.", font=small, fill=0)
    draw.text((x, 0), body, font=face, fill=0)
    return img


def _grid(width: int, tiles: list[Image.Image], cols: int) -> Image.Image:
    inner = width - 2 * MARGIN
    col_w = inner // cols
    rows = (len(tiles) + cols - 1) // cols
    tile_h = max((t.height for t in tiles), default=0)
    img = Image.new("L", (width, rows * (tile_h + 10)), 255)
    for i, tile in enumerate(tiles):
        row, col = divmod(i, cols)
        img.paste(tile, (MARGIN + col * col_w, row * (tile_h + 10)))
    return img


def math_page(
    width: int,
    sheet: MathStrip,
    footer: Footer,
    *,
    answer: bool = False,
    who: str | None = None,
) -> Canvas:
    """Lay out a math strip (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Math answers" if answer else kid_title("Math", who))
    canvas.space(8)
    inner = width - 2 * MARGIN
    px = 40 if width >= 500 else 34
    vertical = [p for p in sheet.problems if p.vertical]
    inline = [p for p in sheet.problems if not p.vertical and p.text is None]
    words = [p for p in sheet.problems if p.text is not None]
    num = 1
    if vertical:
        cols = 3 if width >= 500 and max(len(str(p.a)) for p in vertical) <= 3 else 2
        tiles = []
        for problem in vertical:
            tiles.append(_vertical_problem(num, problem, inner // cols, px, answer))
            num += 1
        canvas.drawing(_grid(width, tiles, cols))
    if inline:
        tiles = []
        for problem in inline:
            tiles.append(_inline_problem(num, problem, inner // 2, px - 4, answer))
            num += 1
        canvas.drawing(_grid(width, tiles, 2))
    for problem in words:
        canvas.space(6)
        canvas.text(f"{num}. {problem.text}", px=26)
        canvas.text(
            f"Answer: {problem.answer}" if answer else "Answer: ________",
            px=26,
            bold=True,
            align="right",
        )
        num += 1
    canvas.rule(dashed=True)
    bonus = Image.new("L", (width, int(px * 1.7)), 255)
    draw = ImageDraw.Draw(bonus)
    draw.polygon(_star(MARGIN + px * 0.55, px * 0.75, px * 0.5), fill=0)
    bonus.paste(
        _inline_problem(
            0, sheet.bonus, inner - int(px * 1.2), px, answer, label="Bonus!"
        ),
        (MARGIN + int(px * 1.2), 6),
    )
    canvas.drawing(bonus)
    canvas.footer(*footer.fields())
    return canvas


def joke_page(width: int, joke: Joke, footer: Footer, who: str | None = None) -> Canvas:
    """Lay out a joke (punchline upside down below a fold) or a fun fact."""
    canvas = Canvas(width)
    if who:
        canvas.title(
            f"Joke time, {who}!" if joke.punchline else f"A fun fact for {who}!"
        )
    else:
        canvas.title("Joke time!" if joke.punchline else "Fun fact!")
    canvas.space(10)
    canvas.text(joke.setup, px=34, align="center")
    if joke.punchline:
        canvas.space(14)
        canvas.rule(dashed=True)
        canvas.text("fold here, then flip for the answer", px=18, align="center")
        canvas.space(30)
        answer = Canvas(width)
        answer.text(joke.punchline, px=34, bold=True, align="center")
        flipped = Image.new("L", (width, answer.height), 255)
        y = 0
        for block in answer.blocks:
            flipped.paste(block, (0, y))
            y += block.height
        canvas.drawing(flipped.rotate(180))
    if joke.credit:
        canvas.space(8)
        canvas.text(f"Source: {joke.credit}", px=18, align="center")
    canvas.space(12)
    canvas.footer(*footer.fields())
    return canvas


def joke_answer_page(
    width: int, setup: str, punchline: str | None, footer: Footer
) -> Canvas:
    """Lay out a joke with its punchline the right way up."""
    canvas = Canvas(width)
    canvas.title("Joke answer" if punchline else "Fun fact")
    canvas.space(10)
    canvas.text(setup, px=30, align="center")
    if punchline:
        canvas.space(10)
        canvas.text(punchline, px=34, bold=True, align="center")
    canvas.space(12)
    canvas.footer(*footer.fields())
    return canvas


def _cloud(
    draw: ImageDraw.ImageDraw, x: float, y: float, s: float, fill: int = 255
) -> None:
    """Draw a cloud in a box of size ``s`` at (x, y), outlined in black."""
    w = max(2, int(s * 0.07))
    parts = [
        (x + s * 0.05, y + s * 0.45, x + s * 0.45, y + s * 0.85),
        (x + s * 0.25, y + s * 0.25, x + s * 0.7, y + s * 0.7),
        (x + s * 0.5, y + s * 0.4, x + s * 0.95, y + s * 0.85),
    ]
    for box in parts:
        draw.ellipse(box, fill=0)
    inset = [(a + w, b + w, c - w, d - w) for a, b, c, d in parts]
    for box in inset:
        draw.ellipse(box, fill=fill)
    draw.rectangle(
        (x + s * 0.25, y + s * 0.62, x + s * 0.75, y + s * 0.85 - w), fill=fill
    )
    draw.line(
        (x + s * 0.25, y + s * 0.85 - w / 2, x + s * 0.75, y + s * 0.85 - w / 2),
        fill=0,
        width=w,
    )


def _sun(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    w = max(2, int(r * 0.22))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=0, width=w)
    for i in range(8):
        ang = i * math.pi / 4
        draw.line(
            (
                cx + math.cos(ang) * r * 1.4,
                cy + math.sin(ang) * r * 1.4,
                cx + math.cos(ang) * r * 1.9,
                cy + math.sin(ang) * r * 1.9,
            ),
            fill=0,
            width=w,
        )


def weather_icon(condition: str | None, size: int) -> Image.Image:
    """Draw a simple black-and-white pictogram for a weather condition."""
    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)
    s = size
    w = max(2, int(s * 0.07))
    c = condition or ""
    if c in ("sunny", "exceptional"):
        _sun(d, s / 2, s / 2, s * 0.22)
    elif c == "clear-night":
        d.ellipse((s * 0.2, s * 0.15, s * 0.8, s * 0.75), fill=0)
        d.ellipse((s * 0.38, s * 0.05, s * 0.95, s * 0.62), fill=255)
    elif c == "partlycloudy":
        _sun(d, s * 0.62, s * 0.36, s * 0.15)
        _cloud(d, s * 0.0, s * 0.18, s * 0.82)
    elif c in ("fog",):
        for i in range(4):
            y = s * (0.3 + i * 0.14)
            d.line(
                (s * 0.12 + (i % 2) * s * 0.08, y, s * 0.88 - (i % 2) * s * 0.08, y),
                fill=0,
                width=w,
            )
    elif c in ("windy", "windy-variant"):
        for i, length in enumerate((0.7, 0.55, 0.65)):
            y = s * (0.32 + i * 0.18)
            d.line((s * 0.1, y, s * (0.1 + length), y), fill=0, width=w)
            d.arc(
                (
                    s * (0.1 + length) - s * 0.08,
                    y - s * 0.16,
                    s * (0.1 + length) + s * 0.08,
                    y,
                ),
                270,
                90,
                fill=0,
                width=w,
            )
    else:
        _cloud(d, s * 0.05, s * 0.0, s * 0.9)
        if c in ("rainy", "pouring", "lightning-rainy", "snowy-rainy"):
            drops = 4 if c == "pouring" else 3
            for i in range(drops):
                x = s * (0.28 + i * (0.44 / max(1, drops - 1)))
                d.line((x, s * 0.8, x - s * 0.06, s * 0.95), fill=0, width=w)
        if c in ("snowy", "snowy-rainy", "hail"):
            for i in range(3):
                x, y = s * (0.3 + i * 0.2), s * 0.88
                r = s * 0.05
                if c == "hail":
                    d.ellipse((x - r, y - r, x + r, y + r), fill=0)
                else:
                    d.line((x - r, y, x + r, y), fill=0, width=max(1, w // 2))
                    d.line((x, y - r, x, y + r), fill=0, width=max(1, w // 2))
                    d.line(
                        (x - r * 0.7, y - r * 0.7, x + r * 0.7, y + r * 0.7),
                        fill=0,
                        width=max(1, w // 2),
                    )
                    d.line(
                        (x - r * 0.7, y + r * 0.7, x + r * 0.7, y - r * 0.7),
                        fill=0,
                        width=max(1, w // 2),
                    )
        if c in ("lightning", "lightning-rainy"):
            d.polygon(
                [
                    (s * 0.52, s * 0.62),
                    (s * 0.4, s * 0.82),
                    (s * 0.5, s * 0.82),
                    (s * 0.44, s * 0.99),
                    (s * 0.62, s * 0.74),
                    (s * 0.52, s * 0.74),
                ],
                fill=0,
            )
    return img


def _deg(value: float | None, unit: str) -> str:
    if value is None:
        return "--"
    return f"{round(value)}°"


def weather_page(width: int, report: WeatherReport, footer: Footer) -> Canvas:
    """Lay out current conditions and a day-by-day forecast."""
    canvas = Canvas(width)
    canvas.title("Weather")
    canvas.text(report.place, px=22, align="center")
    canvas.space(8)

    # Current conditions: icon on the left, big temperature and details right.
    icon_size = 120 if width >= 500 else 96
    block = Image.new("L", (width, icon_size + 160), 255)
    block.paste(weather_icon(report.condition, icon_size), (MARGIN + 4, 4))
    draw = ImageDraw.Draw(block)
    x = MARGIN + icon_size + 24
    big = font("sans", 72 if width >= 500 else 56, True)
    big_text = _deg(report.temperature, report.temp_unit)
    if report.temperature is not None:
        big_text = f"{round(report.temperature)}{report.temp_unit}"
    draw.text((x, 0), big_text, font=big, fill=0)
    small = font("sans", 24 if width >= 500 else 20, False)
    details = [condition_label(report.condition)]
    extras = []
    if report.feels_like is not None:
        extras.append(f"Feels {_deg(report.feels_like, report.temp_unit)}")
    if report.humidity is not None:
        extras.append(f"{round(report.humidity)}% humid")
    if report.wind_speed is not None:
        extras.append(f"Wind {round(report.wind_speed)} {report.wind_unit}".strip())
    if extras:
        details.append("  ".join(extras[:2]))
        if len(extras) > 2:
            details.append(extras[2])
    y = big.getmetrics()[0] + 6
    for line in details:
        draw.text((x, y), line, font=small, fill=0)
        y += int(small.size * 1.25)
    canvas.drawing(block.crop((0, 0, width, max(icon_size + 8, y + 4))))
    canvas.space(6)

    if report.days:
        canvas.rule()
        canvas.text(
            f"{len(report.days)}-day forecast", px=24, bold=True, align="center"
        )
        canvas.space(4)
        row_h = 56 if width >= 500 else 50
        icon = row_h - 12
        name_f = font("sans", 24 if width >= 500 else 20, True)
        text_f = font("sans", 22 if width >= 500 else 18, False)
        temp_f = font("mono", 24 if width >= 500 else 20, True)
        rows = Image.new("L", (width, row_h * len(report.days)), 255)
        draw = ImageDraw.Draw(rows)
        today = report.days[0].day
        for i, day in enumerate(report.days):
            top = i * row_h
            if i:
                for xx in range(MARGIN, width - MARGIN, 6):
                    draw.point((xx, top), fill=0)
            label = "Today" if day.day == today else day.day.strftime("%a %-m/%-d")
            mid = top + row_h / 2
            draw.text((MARGIN + 2, mid), label, font=name_f, fill=0, anchor="lm")
            ix = MARGIN + int(width * 0.27)
            rows.paste(weather_icon(day.condition, icon), (ix, top + 6))
            temps = (
                f"{_deg(day.high, report.temp_unit)}/{_deg(day.low, report.temp_unit)}"
            )
            draw.text(
                (width - MARGIN - 2, mid), temps, font=temp_f, fill=0, anchor="rm"
            )
            if day.precip_chance is not None and day.precip_chance >= 10:
                rain = f"{round(day.precip_chance)}%"
                draw.text(
                    (width - MARGIN - temp_f.getlength(temps) - 18, mid),
                    rain,
                    font=text_f,
                    fill=0,
                    anchor="rm",
                )
            if width >= 500:
                draw.text(
                    (ix + icon + 10, mid),
                    condition_label(day.condition),
                    font=text_f,
                    fill=0,
                    anchor="lm",
                )
        canvas.drawing(rows)
        canvas.text("% = chance of rain or snow", px=16, align="right")
    canvas.space(8)
    canvas.footer(*footer.fields())
    return canvas


def sudoku_drawing(
    width: int, puzzle: Sudoku, *, show_answers: bool = False
) -> Image.Image:
    """Draw the grid with thick box borders; answers use a lighter weight."""
    inner = width - 2 * MARGIN
    n = puzzle.size
    cell = min(inner // n, 120 if n <= 6 else 60)
    grid = cell * n
    x0 = (width - grid) // 2
    img = Image.new("L", (width, grid + 8), 255)
    draw = ImageDraw.Draw(img)
    br, bc = puzzle.box
    face = font("mono", int(cell * 0.6), True)
    answer_face = font("mono", int(cell * 0.5), False)
    for r in range(n):
        for c in range(n):
            given = puzzle.puzzle[r][c]
            value = given or (puzzle.solution[r][c] if show_answers else 0)
            if not value:
                continue
            cx, cy = x0 + c * cell + cell / 2, 4 + r * cell + cell / 2
            draw.text(
                (cx, cy),
                str(value),
                font=face if given else answer_face,
                fill=0,
                anchor="mm",
            )
    for i in range(n + 1):
        thick_r = 5 if i % br == 0 else 2
        thick_c = 5 if i % bc == 0 else 2
        y = 4 + i * cell
        draw.rectangle(
            (x0 - 2, y - thick_r // 2, x0 + grid + 2, y + thick_r // 2), fill=0
        )
        x = x0 + i * cell
        draw.rectangle((x - thick_c // 2, 2, x + thick_c // 2, 4 + grid + 2), fill=0)
    return img


def sudoku_page(
    width: int,
    puzzle: Sudoku,
    footer: Footer,
    *,
    answer: bool = False,
    who: str | None = None,
) -> Canvas:
    """Lay out a kid sudoku (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Sudoku answers" if answer else kid_title("Sudoku", who))
    n = puzzle.size
    canvas.text(
        f"Write 1 to {n} once in every row, column and box.", px=24, align="center"
    )
    canvas.space(8)
    canvas.drawing(sudoku_drawing(width, puzzle, show_answers=answer))
    canvas.space(6)
    canvas.footer(*footer.fields())
    return canvas


def spelling_page(
    width: int,
    sheet: SpellingSheet,
    footer: Footer,
    *,
    answer: bool = False,
    who: str | None = None,
) -> Canvas:
    """Lay out unscramble and missing-letter practice (or the answer key)."""
    canvas = Canvas(width)
    canvas.title("Spelling answers" if answer else kid_title("Spelling practice", who))
    canvas.space(4)
    px = 30 if width >= 500 else 26
    mono = font("mono", px, True)
    line_h = int(px * 1.6)
    half = len(sheet.words)

    def rows(lines: list[tuple[str, str]]) -> Image.Image:
        img = Image.new("L", (width, line_h * len(lines) + 6), 255)
        draw = ImageDraw.Draw(img)
        for i, (left, right) in enumerate(lines):
            y = i * line_h + line_h / 2
            draw.text((MARGIN + 4, y), left, font=mono, fill=0, anchor="lm")
            if right:
                draw.text(
                    (width - MARGIN - 4, y), right, font=mono, fill=0, anchor="rm"
                )
            else:
                draw.line(
                    (width * 0.58, y + px * 0.45, width - MARGIN - 4, y + px * 0.45),
                    fill=0,
                    width=2,
                )
        return img

    canvas.text("Unscramble the words", px=26, bold=True)
    canvas.drawing(
        rows(
            [
                (f"{i + 1:>2}. {w.upper()}", sheet.words[i] if answer else "")
                for i, w in enumerate(sheet.scrambled)
            ]
        )
    )
    canvas.rule(dashed=True)
    canvas.text("Fill in the missing letters", px=26, bold=True)
    canvas.drawing(
        rows(
            [
                (
                    f"{i + half + 1:>2}. {sheet.masked(i)}",
                    sheet.words[i] if answer else "",
                )
                for i in range(len(sheet.words))
            ]
        )
    )
    canvas.space(6)
    canvas.footer(*footer.fields())
    return canvas


def crossword_drawing(
    width: int, puzzle: Crossword, *, show_answers: bool = False
) -> Image.Image:
    """Draw letter boxes for each answer, numbered in the corner."""
    inner = width - 2 * MARGIN
    cell = min(inner // puzzle.cols, 52)
    x0 = (width - cell * puzzle.cols) // 2
    img = Image.new("L", (width, cell * puzzle.rows + 6), 255)
    draw = ImageDraw.Draw(img)
    num_font = font("sans", max(12, cell // 3), True)
    letter_font = font("mono", int(cell * 0.6), True)
    numbers = puzzle.numbers()
    for (r, c), ch in puzzle.letters().items():
        x, y = x0 + c * cell, 3 + r * cell
        draw.rectangle((x, y, x + cell, y + cell), outline=0, width=2)
        if (r, c) in numbers:
            draw.text((x + 3, y + 1), str(numbers[(r, c)]), font=num_font, fill=0)
        if show_answers:
            draw.text(
                (x + cell / 2, y + cell * 0.58),
                ch,
                font=letter_font,
                fill=0,
                anchor="mm",
            )
    return img


def crossword_page(
    width: int,
    puzzle: Crossword,
    footer: Footer,
    *,
    answer: bool = False,
    title: str = "Crossword",
    who: str | None = None,
    also: tuple[str, ...] = (),
) -> Canvas:
    """Lay out a criss-cross crossword with Across and Down clues.

    ``also`` lists words that couldn't join the grid (a spelling crossword),
    so they still get practiced.
    """
    canvas = Canvas(width)
    canvas.title(f"{title} answers" if answer else kid_title(title, who))
    canvas.space(6)
    canvas.drawing(crossword_drawing(width, puzzle, show_answers=answer))
    canvas.space(6)
    for heading, direction in (("Across", "across"), ("Down", "down")):
        items = [e for e in puzzle.entries if e.direction == direction]
        if not items:
            continue
        canvas.text(heading, px=26, bold=True)
        for entry in sorted(items, key=lambda e: e.number):
            extra = f"  ({len(entry.word)})"
            line = f"{entry.number}. {entry.clue}{extra}"
            if answer:
                line += f"  {entry.word}"
            canvas.text(line, px=22)
        canvas.space(6)
    if also:
        canvas.text("Also practice", px=26, bold=True)
        canvas.text(", ".join(w.lower() for w in also), px=22)
        canvas.space(6)
    canvas.footer(*footer.fields())
    return canvas


def cryptogram_page(
    width: int, puzzle: Cryptogram, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out a cryptogram: code letters with a blank line under each."""
    canvas = Canvas(width)
    canvas.title("Cryptogram answer" if answer else "Cryptogram")
    canvas.text("Each letter stands for a different letter.", px=22, align="center")
    canvas.space(8)
    inner = width - 2 * MARGIN
    px = 30 if width >= 500 else 26
    face = font("mono", px, True)
    small = font("mono", int(px * 0.8), False)
    adv = int(face.getlength("M") + 4)
    per_line = max(8, inner // adv)
    hints = {c: p for c, p in puzzle.hint_pairs()}
    plain_upper = puzzle.plain.upper()
    # Wrap by words so no word splits across lines.
    lines: list[list[tuple[str, str]]] = [[]]
    for word_c, word_p in zip(
        puzzle.cipher.split(" "), plain_upper.split(" "), strict=True
    ):
        pairs = list(zip(word_c, word_p, strict=True))
        if lines[-1] and len(lines[-1]) + 1 + len(pairs) > per_line:
            lines.append([])
        if lines[-1]:
            lines[-1].append((" ", " "))
        lines[-1].extend(pairs)
    row_h = int(px * 2.6)
    img = Image.new("L", (width, row_h * len(lines) + 4), 255)
    draw = ImageDraw.Draw(img)
    for li, line in enumerate(lines):
        y = li * row_h
        x = MARGIN + (inner - adv * len(line)) // 2
        for code, plain in line:
            if code.isalpha():
                draw.text(
                    (x + adv / 2, y + px * 0.6), code, font=face, fill=0, anchor="mm"
                )
                draw.line(
                    (x + 3, y + px * 2.1, x + adv - 3, y + px * 2.1), fill=0, width=2
                )
                shown = plain if answer else hints.get(code)
                if shown:
                    draw.text(
                        (x + adv / 2, y + px * 1.65),
                        shown,
                        font=small,
                        fill=0,
                        anchor="mm",
                    )
            elif code != " ":
                draw.text(
                    (x + adv / 2, y + px * 1.6), code, font=face, fill=0, anchor="mm"
                )
            x += adv
    canvas.drawing(img)
    if hints and not answer:
        canvas.text(
            "Hints: " + ", ".join(f"{c} = {p}" for c, p in hints.items()),
            px=22,
            align="center",
        )
    if answer:
        canvas.space(4)
        canvas.text(f"\u201c{puzzle.plain}\u201d", px=24, align="center")
    canvas.text(f"\u2014 {puzzle.author}", px=22, align="right")
    canvas.space(6)
    canvas.footer(*footer.fields())
    return canvas


def story_page(width: int, story: Story, footer: Footer) -> Canvas:
    """Lay out a bedtime story or chapter, with choices for serials."""
    canvas = Canvas(width)
    canvas.title(story.title, px=38)
    if story.chapter:
        canvas.text(f"Chapter {story.chapter}", px=24, align="center")
    canvas.space(10)
    for para in story.paragraphs:
        canvas.text(para, px=26, line_gap=0.3)
        canvas.space(10)
    if story.choices:
        canvas.rule(dashed=True)
        canvas.text("What happens next? Circle one:", px=24, bold=True)
        canvas.space(4)
        for letter, choice in zip("AB", story.choices, strict=False):
            face = font("sans", 24, False)
            letter_face = font("sans", 26, True)
            inner = width - 2 * MARGIN
            lines = wrap(choice, face, inner - 56)
            line_h = int(24 * 1.35)
            block = Image.new("L", (width, max(44, line_h * len(lines)) + 8), 255)
            draw = ImageDraw.Draw(block)
            draw.ellipse((MARGIN + 2, 2, MARGIN + 40, 40), outline=0, width=3)
            draw.text((MARGIN + 21, 21), letter, font=letter_face, fill=0, anchor="mm")
            for i, line in enumerate(lines):
                draw.text((MARGIN + 54, 6 + i * line_h), line, font=face, fill=0)
            canvas.drawing(block)
            canvas.space(6)
    if story.credit:
        canvas.text(story.credit, px=18, align="right")
    canvas.space(6)
    canvas.footer(*footer.fields())
    return canvas


def _weather_line(width: int, report: WeatherReport) -> Image.Image:
    """Compact weather: icon, now, high/low and rain chance."""
    img = Image.new("L", (width, 96), 255)
    img.paste(weather_icon(report.condition, 88), (MARGIN + 4, 4))
    draw = ImageDraw.Draw(img)
    big = font("sans", 30 if width >= 500 else 26, True)
    small = font("sans", 22 if width >= 500 else 19, False)
    now = (
        f"{round(report.temperature)}{report.temp_unit}  "
        if report.temperature is not None
        else ""
    )
    draw.text(
        (MARGIN + 104, 8), now + condition_label(report.condition), font=big, fill=0
    )
    if report.days:
        today = report.days[0]
        parts = [f"High {_deg(today.high, '')}", f"Low {_deg(today.low, '')}"]
        if today.precip_chance is not None:
            parts.append(f"Rain {round(today.precip_chance)}%")
        draw.text((MARGIN + 104, 50), "  ".join(parts), font=small, fill=0)
    return img


def _rows(width: int, rows: list[tuple[str, str]], px: int = 22) -> Image.Image:
    """Two columns: a fixed label column and wrapped text."""
    label_face = font("mono", px, True)
    text_face = font("sans", px + 2, False)
    label_w = int(max((label_face.getlength(r[0]) for r in rows), default=0)) + 14
    inner = width - 2 * MARGIN - label_w
    line_h = int((px + 2) * 1.3)
    wrapped = [(label, wrap(text, text_face, inner)) for label, text in rows]
    height = sum(len(lines) * line_h + 4 for _l, lines in wrapped)
    img = Image.new("L", (width, height + 2), 255)
    draw = ImageDraw.Draw(img)
    y = 0
    for label, lines in wrapped:
        draw.text((MARGIN, y + 3), label, font=label_face, fill=0)
        for line in lines:
            draw.text((MARGIN + label_w, y), line, font=text_face, fill=0)
            y += line_h
        y += 4
    return img


def morning_page(width: int, slip: MorningSlip, footer: Footer) -> Canvas:
    """Lay out the morning slip."""
    canvas = Canvas(width)
    canvas.title("Good morning!", px=40)
    canvas.text(slip.day.strftime("%A, %B %-d"), px=26, align="center")
    if slip.banner is not None:
        canvas.space(6)
        if slip.banner.art:
            canvas.drawing(ascii_art(width, slip.banner.art))
        canvas.text(slip.banner.name, px=28, bold=True, align="center")
        canvas.text(slip.banner.banner, px=22, align="center")
        if slip.also:
            canvas.text(f"Also today: {', '.join(slip.also)}", px=18, align="center")
    canvas.rule()
    if slip.weather is not None:
        canvas.drawing(_weather_line(width, slip.weather))
        canvas.rule(dashed=True)
    canvas.text("Today", px=28, bold=True)
    if slip.events:
        canvas.drawing(_rows(width, [(e.when, e.title) for e in slip.events]))
        if slip.more_events:
            canvas.text(f"+{slip.more_events} more", px=20, align="right")
    elif slip.calendars_set:
        canvas.text("Nothing on the calendar today.", px=24)
    else:
        canvas.text("Pick calendars in Configure → Settings to see events here.", px=20)
    for name, items in slip.todos:
        canvas.rule(dashed=True)
        canvas.text(name, px=26, bold=True)
        canvas.drawing(_rows(width, [("[ ]", item) for item in items]))
    if slip.headlines is not None:
        name, items = slip.headlines
        canvas.rule(dashed=True)
        canvas.text(f"Headlines \u00b7 {name}", px=24, bold=True, align="center")
        if not items:
            canvas.text("Nothing new in this feed right now.", px=20, align="center")
        for item in items:
            canvas.text(f"\u2022 {item.title}", px=22)
    if slip.joke is not None:
        canvas.rule(dashed=True)
        if slip.joke.punchline:
            canvas.text("Joke of the day", px=24, bold=True, align="center")
            canvas.text(slip.joke.setup, px=26, align="center")
            canvas.space(6)
            answer = Canvas(width)
            answer.text(slip.joke.punchline, px=24, bold=True, align="center")
            flipped = Image.new("L", (width, answer.height), 255)
            y = 0
            for block in answer.blocks:
                flipped.paste(block, (0, y))
                y += block.height
            canvas.drawing(flipped.rotate(180))
        else:
            canvas.text("Fun fact", px=24, bold=True, align="center")
            canvas.text(slip.joke.setup, px=24, align="center")
            if slip.joke.credit:
                canvas.text(f"Source: {slip.joke.credit}", px=16, align="center")
    if slip.quote is not None:
        canvas.rule(dashed=True)
        canvas.text("Quote of the day", px=24, bold=True, align="center")
        canvas.text(f"\u201c{slip.quote.text}\u201d", px=26, align="center")
        canvas.text(f"\u2014 {slip.quote.author}", px=22, align="right")
        if slip.quote.credit:
            canvas.text(slip.quote.credit, px=14, align="right")
    if slip.word is not None:
        canvas.rule(dashed=True)
        canvas.text("Word of the day", px=24, bold=True, align="center")
        canvas.text(slip.word.word, px=36, bold=True, align="center")
        canvas.text(slip.word.pos, px=20, align="center")
        canvas.text(
            slip.word.definition[:1].upper() + slip.word.definition[1:] + ".", px=24
        )
        if slip.word.example:
            canvas.text(f"\u201c{slip.word.example}\u201d", px=22)
        canvas.text(
            "Definition: Open English WordNet (CC BY 4.0)", px=14, align="center"
        )
    if slip.puzzle is not None:
        canvas.rule(dashed=True)
        canvas.text("Puzzle of the day", px=24, bold=True, align="center")
        canvas.text(
            f"Write 1 to {slip.puzzle.size} once in every row, column and box.",
            px=20,
            align="center",
        )
        grid = sudoku_drawing(int(width * 0.7), slip.puzzle)
        half = Image.new("L", (width, grid.height), 255)
        half.paste(grid, ((width - grid.width) // 2, 0))
        canvas.drawing(half)
    canvas.space(6)
    canvas.footer(*footer.fields())
    return canvas


DASHES = ((0, 0), (14, 8), (4, 6))  # solid, dashed, dotted (on, off) in px


def _fmt_num(value: float | None, unit: str = "") -> str:
    if value is None:
        return "--"
    text = (
        f"{value:.0f}" if abs(value) >= 100 else f"{value:.1f}".rstrip("0").rstrip(".")
    )
    return (
        f"{text}{unit}" if unit in ("%", "°F", "°C", "°") else f"{text} {unit}".rstrip()
    )


def _nice_ticks(low: float, high: float, count: int = 4) -> list[float]:
    """Round tick values covering low..high."""
    if high <= low:
        high = low + 1
    raw = (high - low) / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    value = math.floor(low / step) * step
    ticks = [round(value, 6)]
    while ticks[-1] < high - step * 1e-6:
        value += step
        ticks.append(round(value, 6))
    if len(ticks) == 1:
        ticks.append(round(value + step, 6))
    return ticks


def _styled_line(
    draw: ImageDraw.ImageDraw, pts: list[tuple[float, float]], style: int, width: int
) -> None:
    on, off = DASHES[style % len(DASHES)]
    if not on:
        draw.line(pts, fill=0, width=width, joint="curve")
        return
    carry = 0.0
    drawing = True
    for (x1, y1), (x2, y2) in itertools.pairwise(pts):
        seg = math.hypot(x2 - x1, y2 - y1)
        pos = 0.0
        while pos < seg:
            limit = (on if drawing else off) - carry
            step = min(limit, seg - pos)
            if drawing and seg:
                a = pos / seg
                b = (pos + step) / seg
                draw.line(
                    (
                        x1 + (x2 - x1) * a,
                        y1 + (y2 - y1) * a,
                        x1 + (x2 - x1) * b,
                        y1 + (y2 - y1) * b,
                    ),
                    fill=0,
                    width=width,
                )
            pos += step
            carry += step
            if carry >= (on if drawing else off) - 1e-6:
                drawing = not drawing
                carry = 0.0


def _time_ticks(
    start: datetime, end: datetime, by_day: bool, to_local: Any, *, room: int = 6
) -> list[datetime]:
    """Round time ticks (hours or days), about ``room`` of them."""
    span = end - start
    if by_day:
        first = to_local(start).replace(hour=0, minute=0, second=0, microsecond=0)
        days = max(1, round(span.total_seconds() / 86400))
        every = max(1, math.ceil(days / room))
        return [first + timedelta(days=i) for i in range(1, days + 1, every)]
    hours = max(1, round(span.total_seconds() / 3600))
    every = next((h for h in (1, 2, 3, 4, 6, 8, 12, 24) if hours / h <= room), 24)
    first = to_local(start).replace(minute=0, second=0, microsecond=0)
    ticks = []
    t = first + timedelta(hours=1)
    while t <= to_local(end):
        if t.hour % every == 0:
            ticks.append(t)
        t += timedelta(hours=1)
    return ticks


def line_chart(
    width: int,
    height: int,
    report: HistoryReport,
    series: list[Series],
    to_local: Any,
) -> Image.Image:
    """Numeric series on one landscape chart (time left to right).

    Tall prints draw this chart long and rotate it onto the strip.
    """
    values = [v for s in series for _t, v in (*s.points, *s.lows, *s.highs)]
    ticks = _nice_ticks(min(values), max(values), 6 if report.grid else 4)
    lo, hi = ticks[0], ticks[-1]
    if hi == lo:
        hi = lo + 1
    label_font = font("sans", 18 if height >= 260 else 16, False)
    unit = series[0].unit
    t0, t1 = report.start.timestamp(), report.end.timestamp()
    span_t = max(1.0, t1 - t0)
    img = Image.new("L", (width, height), 255)
    left, right, top, bottom = MARGIN + 58, width - MARGIN - 26, 22, height - 34
    draw = ImageDraw.Draw(img)

    def place(t: float, v: float) -> tuple[float, float]:
        return (
            left + (t - t0) / span_t * (right - left),
            bottom - (v - lo) / (hi - lo) * (bottom - top),
        )

    for tick in ticks:
        _, y = place(t0, tick)
        for xx in range(left, right, 6):
            draw.point((xx, y), fill=0)
        draw.text((left - 6, y), _fmt_num(tick), font=label_font, fill=0, anchor="rm")
    room = max(4, (right - left) // 90)
    for tick in _time_ticks(
        report.start, report.end, report.by_day, to_local, room=room
    ):
        label = (
            tick.strftime("%a %-m/%-d") if report.by_day else tick.strftime("%-I %p")
        )
        x, _ = place(tick.timestamp(), lo)
        if report.grid:
            for yy in range(top, bottom, 6):
                draw.point((x, yy), fill=0)
        draw.line((x, bottom, x, bottom + 4), fill=0, width=2)
        draw.text((x, bottom + 8), label, font=label_font, fill=0, anchor="mt")
    draw.line((left, bottom, right, bottom), fill=0, width=2)
    if report.grid:
        draw.rectangle((left, top, right, bottom), outline=0, width=1)
    for i, s in enumerate(series):
        for band in (s.lows, s.highs):
            if len(band) > 1:
                _styled_line(draw, [place(t.timestamp(), v) for t, v in band], 2, 1)
        pts = [place(t.timestamp(), v) for t, v in s.points]
        if len(pts) == 1:
            x, y = pts[0]
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=0)
        elif pts:
            _styled_line(draw, pts, i, 3)
    if unit:
        draw.text((MARGIN, 0), unit, font=label_font, fill=0)
    return img


def _legend(width: int, group: list[Series]) -> Image.Image:
    legend = Image.new("L", (width, 30 * len(group)), 255)
    draw = ImageDraw.Draw(legend)
    lf = font("sans", 20, False)
    for i, s in enumerate(group):
        y = 15 + i * 30
        _styled_line(draw, [(MARGIN, y), (MARGIN + 60, y)], i, 3)
        draw.text((MARGIN + 72, y), s.name, font=lf, fill=0, anchor="lm")
    return legend


def _summary_lines(s: Series) -> list[str]:
    summary = summarize(s)
    u = s.unit
    change = summary.change
    sign = "+" if change and change > 0 else ""
    return [
        f"Now {_fmt_num(summary.now, u)}   Min {_fmt_num(summary.low, u)}   "
        f"Max {_fmt_num(summary.high, u)}",
        f"Average {_fmt_num(summary.average, u)}   Change {sign}{_fmt_num(change, u)}",
    ]


def tall_block(
    paper: int,
    report: HistoryReport,
    group: list[Series],
    to_local: Any,
    footer: Footer | None = None,
) -> Image.Image:
    """Draw a landscape page (header left, long chart right) rotated onto the strip.

    Turn the receipt sideways and everything reads normally; the header ends
    up at the bottom of the strip and time runs the same way as the data.
    """
    hours = max(1.0, (report.end - report.start).total_seconds() / 3600)
    chart_len = int(min(2400, max(700, hours * 14)))
    header_w = 300
    header = Canvas(header_w)
    header.title(report.title, px=30)
    start, end = to_local(report.start), to_local(report.end)
    header.text(f"{start.strftime('%a %b %-d %-I:%M %p')}", px=16, align="center")
    header.text(f"to {end.strftime('%a %b %-d %-I:%M %p')}", px=16, align="center")
    header.space(6)
    if len(group) > 1:
        header.drawing(_legend(header_w, group))
    for s in group:
        if len(group) > 1:
            header.text(s.name, px=18, bold=True)
        for line in _summary_lines(s):
            header.text(line, px=16)
    if footer is not None:
        header.space(6)
        header.footer(*footer.fields())
    head_img, _ = header.render()
    page = Image.new("L", (header_w + chart_len, paper), 255)
    page.paste(
        head_img.convert("L").crop((0, 0, header_w, min(head_img.height, paper))),
        (0, 8),
    )
    page.paste(line_chart(chart_len, paper, report, group, to_local), (header_w, 0))
    return page.rotate(90, expand=True)


def _hatch(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float]) -> None:
    """Light diagonal hatching (solid black slows a thermal printer down)."""
    x1, y1, x2, y2 = box
    draw.rectangle(box, outline=0, width=2)
    step = 7
    height = y2 - y1
    x = x1 - height
    while x < x2:
        a = (max(x, x1), y1 + max(0, x1 - x))
        b = (min(x + height, x2), y1 + min(height, x2 - x))
        if a[0] < b[0]:
            draw.line((a, b), fill=0, width=1)
        x += step


def timeline_chart(width: int, report: HistoryReport, series: Series) -> Image.Image:
    """One lane per state (up to four), hatched where that state was active."""
    totals = [row[0] for row in state_totals(series)][:4]
    lane_h = 34
    label_font = font("sans", 18 if width >= 500 else 16, True)
    label_w = int(max((label_font.getlength(s) for s in totals), default=40)) + 12
    left, right = MARGIN + label_w, width - MARGIN
    img = Image.new("L", (width, lane_h * len(totals) + 6), 255)
    draw = ImageDraw.Draw(img)
    t0, t1 = report.start.timestamp(), report.end.timestamp()
    span_t = max(1.0, t1 - t0)
    for lane, state in enumerate(totals):
        y = lane * lane_h + 4
        draw.text(
            (MARGIN, y + lane_h / 2 - 2), state, font=label_font, fill=0, anchor="lm"
        )
        draw.line((left, y + lane_h - 4, right, y + lane_h - 4), fill=0, width=1)
        for start, stop, seg_state in series.segments:
            if seg_state != state:
                continue
            xa = left + (start.timestamp() - t0) / span_t * (right - left)
            xb = left + (stop.timestamp() - t0) / span_t * (right - left)
            _hatch(draw, (xa, y + 4, max(xa + 2, xb), y + lane_h - 6))
    return img


def _duration(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h"


def table_image(
    width: int, headers: list[str], rows: list[list[str]], px: int = 19
) -> Image.Image:
    """Draw a ruled table: header row, column and row divider lines."""
    head_face = font("sans", px, True)
    face = font("mono", px, False)
    inner = width - 2 * MARGIN
    first = (
        max([head_face.getlength(headers[0]), *(face.getlength(r[0]) for r in rows)])
        + 16
    )
    other = (inner - first) / max(1, len(headers) - 1)
    widths = [first] + [other] * (len(headers) - 1)
    row_h = int(px * 1.7)
    img = Image.new("L", (width, row_h * (len(rows) + 1) + 4), 255)
    draw = ImageDraw.Draw(img)
    x_edges = [MARGIN]
    for w in widths:
        x_edges.append(x_edges[-1] + w)
    bottom = row_h * (len(rows) + 1)
    for r, cells in enumerate([headers, *rows]):
        y = r * row_h
        for c, cell in enumerate(cells):
            cx = (x_edges[c] + x_edges[c + 1]) / 2 if c else x_edges[0] + 8
            anchor = "mm" if c else "lm"
            draw.text(
                (cx, y + row_h / 2),
                cell,
                font=head_face if r == 0 else face,
                fill=0,
                anchor=anchor,
            )
        draw.line((MARGIN, y, x_edges[-1], y), fill=0, width=2 if r <= 1 else 1)
    draw.line((MARGIN, bottom, x_edges[-1], bottom), fill=0, width=2)
    for x in x_edges:
        draw.line(
            (x, 0, x, bottom), fill=0, width=2 if x in (x_edges[0], x_edges[-1]) else 1
        )
    return img


def history_page(
    width: int, report: HistoryReport, footer: Footer, to_local: Any
) -> Canvas:
    """Lay out a history print: graphs/timelines, summaries and optional tables."""
    canvas = Canvas(width)
    show_graph = report.style in ("graph", "both")
    only_charts = all(s.numeric or s.empty for s in report.series)
    if not (report.tall and show_graph and only_charts):
        # Tall prints carry the header inside the rotated chart instead.
        canvas.title(report.title, px=34)
        start, end = to_local(report.start), to_local(report.end)
        fmt = "%a %b %-d, %-I:%M %p"
        canvas.text(
            f"{start.strftime(fmt)} to {end.strftime(fmt)}", px=18, align="center"
        )
        canvas.space(6)
    show_table = report.style in ("table", "both")
    numeric = [s for s in report.series if s.numeric and s.points]
    others = [s for s in report.series if not s.numeric and s.segments]
    missing = [s for s in report.series if s.empty]
    # Numeric series share a chart per unit.
    by_unit: dict[str, list[Series]] = {}
    for s in numeric:
        by_unit.setdefault(s.unit, []).append(s)
    for group in by_unit.values():
        if show_graph:
            if report.tall:
                inline_footer = footer if only_charts and len(by_unit) == 1 else None
                canvas.drawing(
                    tall_block(width, report, group, to_local, inline_footer)
                )
            else:
                height = 300 if width >= 500 else 250
                canvas.drawing(line_chart(width, height, report, group, to_local))
                if len(group) > 1:
                    canvas.drawing(_legend(width, group))
        for s in group:
            if not (show_graph and report.tall):
                if len(report.series) > 1:
                    canvas.text(s.name, px=22, bold=True)
                for line in _summary_lines(s):
                    canvas.text(line, px=21)
            if show_table:
                rows = bucket_rows(s, report.by_day, to_local)
                if show_graph and report.tall and len(group) > 1:
                    canvas.text(s.name, px=22, bold=True)
                canvas.space(4)
                canvas.drawing(
                    table_image(
                        width,
                        ["Day" if report.by_day else "Hour", "Min", "Avg", "Max"],
                        [
                            [
                                r.label,
                                _fmt_num(r.low),
                                _fmt_num(r.average),
                                _fmt_num(r.high),
                            ]
                            for r in rows
                        ],
                    )
                )
            canvas.space(8)
    for s in others:
        canvas.rule(dashed=True)
        canvas.text(s.name, px=24, bold=True)
        if show_graph:
            canvas.drawing(timeline_chart(width, report, s))
        totals = state_totals(s)
        canvas.text(
            "   ".join(
                f"{state}: {_duration(spent)}" + (f" ({n}x)" if n > 1 else "")
                for state, spent, n in totals[:4]
            ),
            px=20,
        )
        if show_table:
            canvas.space(4)
            canvas.drawing(
                table_image(
                    width,
                    ["Time", "State"],
                    [list(row) for row in changes(s, to_local, report.by_day)],
                )
            )
        canvas.space(6)
    for s in missing:
        canvas.text(f"{s.name}: no history for this period.", px=20)
    for note in report.notes:
        canvas.text(note, px=18)
    canvas.space(4)
    if not (report.tall and show_graph and only_charts and len(by_unit) == 1):
        canvas.footer(*footer.fields())
    return canvas


def feed_parts(
    width: int,
    name: str,
    items: tuple[FeedItem, ...],
    footer: Footer,
    *,
    to_local: Any,
    printed_at: datetime,
    qr: bool = False,
) -> list[tuple[Canvas, str | None]]:
    """Lay out a feed print as parts, each optionally followed by an item's QR.

    Returns ``[(canvas, link for a QR after it or None)]``.
    """
    head = Canvas(width)
    head.title(name, px=36)
    head.text(
        to_local(printed_at).strftime("%A, %B %-d · %-I:%M %p"),
        px=20,
        align="center",
    )
    head.rule()
    parts: list[tuple[Canvas, str | None]] = []
    canvas = head
    if not items:
        canvas.text("Nothing new in this feed right now.", px=24)
    for i, item in enumerate(items):
        if i:
            canvas.rule(dashed=True)
        if item.title:
            canvas.text(item.title, px=26, bold=True)
        if item.published is not None:
            canvas.text(
                to_local(item.published).strftime("%a %b %-d, %-I:%M %p"), px=18
            )
        if item.summary:
            canvas.space(4)
            canvas.text(item.summary, px=22)
        if qr and item.link:
            canvas.space(6)
            parts.append((canvas, item.link))
            canvas = Canvas(width)
            canvas.space(4)
    canvas.space(6)
    canvas.footer(*footer.fields())
    parts.append((canvas, None))
    return parts
