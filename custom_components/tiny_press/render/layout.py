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

from ..generators.maze import Maze
from .canvas import MARGIN, Canvas

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
