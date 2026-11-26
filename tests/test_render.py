"""Rendering: widths, footer, trimming."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import random

from PIL import Image
import pytest

from custom_components.tiny_press.const import PAPER_DOTS
from custom_components.tiny_press.generators import jokes, math_strip, maze, word_search
from custom_components.tiny_press.render import layout
from custom_components.tiny_press.render.canvas import Canvas, font, wrap

FOOTER = layout.Footer("Maze", "K7Q2", date(2026, 11, 25), "hard")


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_every_page_is_exact_width(width: int, tmp_path: Path) -> None:
    pic = tmp_path / "p.png"
    Image.new("RGBA", (1000, 300), (255, 0, 0, 128)).save(pic)
    m = maze.generate("hard", 3)
    pages = [
        layout.maze_page(width, m, FOOTER),
        layout.maze_page(width, m, FOOTER, answer=True),
        layout.text_page(width, "hello " * 100, "Title", "large", FOOTER),
        layout.text_page(width, "x", None, "small", FOOTER),
        layout.test_page(width, {"a": "b"}, FOOTER),
        layout.image_page(width, pic, FOOTER),
    ]
    for grade in ("K", "2", "3", "5"):
        puzzle = word_search.generate(grade, 1, interests="space")
        sheet = math_strip.generate(grade, 1)
        pages += [
            layout.word_search_page(width, puzzle, FOOTER),
            layout.word_search_page(width, puzzle, FOOTER, answer=True),
            layout.math_page(width, sheet, FOOTER),
            layout.math_page(width, sheet, FOOTER, answer=True),
        ]
    pages += [
        layout.joke_page(width, jokes.pick("joke", 1), FOOTER),
        layout.joke_page(width, jokes.pick("fact", 1), FOOTER),
    ]
    for page in pages:
        image, truncated = page.render()
        assert image.mode == "1"
        assert image.width == width
        assert not truncated


def test_dimensions_widths() -> None:
    assert PAPER_DOTS == {"80": 576, "58": 420}


def test_trim_to_max_length() -> None:
    canvas = Canvas(576)
    canvas.text("line\n" * 400)
    image, truncated = canvas.render(max_height=800)
    assert truncated
    assert image.height == 800
    image, truncated = canvas.render(max_height=100_000)
    assert not truncated


def test_footer_fields() -> None:
    assert FOOTER.fields() == ("Maze", "Hard", "Nov 25, 2026", "#K7Q2")
    assert layout.Footer("Note", "AAAA", date(2026, 1, 5)).fields()[1] == ""


def test_print_id_alphabet() -> None:
    ids = {layout.make_print_id(random.Random(i)) for i in range(200)}
    assert all(len(i) == 4 for i in ids)
    assert not set("".join(ids)) & set("0O1IL5S2Z8B")
    assert layout.make_print_id(random.Random(1)) == layout.make_print_id(
        random.Random(1)
    )


def test_wrap_breaks_long_words() -> None:
    face = font("sans", 28)
    lines = wrap("a" * 200, face, 200)
    assert len(lines) > 1
    assert all(face.getlength(line) <= 200 for line in lines)
    assert wrap("", face, 200) == [""]


def test_drawing_width_checked() -> None:
    with pytest.raises(ValueError):
        Canvas(576).drawing(Image.new("L", (100, 10)))


def test_maze_solution_drawn_only_on_answer() -> None:
    m = maze.generate("easy", 5)
    plain = layout.maze_drawing(576, m)
    answer = layout.maze_drawing(576, m, show_solution=True)

    def dark(img: Image.Image) -> int:
        return sum(img.histogram()[:128])

    assert dark(answer) > dark(plain)


def test_canvas_extend_checks_width() -> None:
    with pytest.raises(ValueError):
        Canvas(576).extend(Canvas(420))


def test_word_search_answers_mark_letters() -> None:
    puzzle = word_search.generate("3", 2)
    plain = layout.word_search_drawing(576, puzzle)
    marked = layout.word_search_drawing(576, puzzle, show_answers=True)
    assert sum(marked.histogram()[:128]) > sum(plain.histogram()[:128])
