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

from ..generators.jokes import Joke
from ..generators.math_strip import MathStrip, Problem
from ..generators.maze import Maze
from ..generators.word_search import WordSearch
from .canvas import MARGIN, Canvas, font

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
    ramp = Image.new("L", (canvas.inner, 48))
    draw = ImageDraw.Draw(ramp)
    for x in range(canvas.inner):
        draw.line((x, 0, x, 47), fill=round(255 * x / (canvas.inner - 1)))
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
