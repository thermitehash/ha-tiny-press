"""Page layouts: turn generator output into canvases.

Everything here is synchronous Pillow work; run it in the executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import random

from PIL import Image, ImageDraw

from ..generators.crossword import Crossword
from ..generators.cryptogram import Cryptogram
from ..generators.jokes import Joke
from ..generators.math_strip import MathStrip, Problem
from ..generators.maze import Maze
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

    def fields(self) -> tuple[str, ...]:
        """Footer pieces in print order."""
        return (
            self.label,
            self.difficulty.title() if self.difficulty else "",
            self.day.strftime("%b %-d, %Y"),
            f"#{self.print_id}",
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


def maze_page(
    width: int, maze: Maze, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out a maze printout (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Maze answer" if answer else "Maze")
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
    width: int, puzzle: WordSearch, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out a word search (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Word search answers" if answer else "Word search")
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
    width: int, sheet: MathStrip, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out a math strip (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Math answers" if answer else "Math")
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


def joke_page(width: int, joke: Joke, footer: Footer) -> Canvas:
    """Lay out a joke (punchline upside down below a fold) or a fun fact."""
    canvas = Canvas(width)
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
    width: int, puzzle: Sudoku, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out a kid sudoku (or its answer key)."""
    canvas = Canvas(width)
    canvas.title("Sudoku answers" if answer else "Sudoku")
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
    width: int, sheet: SpellingSheet, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out unscramble and missing-letter practice (or the answer key)."""
    canvas = Canvas(width)
    canvas.title("Spelling answers" if answer else "Spelling practice")
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
    width: int, puzzle: Crossword, footer: Footer, *, answer: bool = False
) -> Canvas:
    """Lay out a criss-cross crossword with Across and Down clues."""
    canvas = Canvas(width)
    canvas.title("Crossword answers" if answer else "Crossword")
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
