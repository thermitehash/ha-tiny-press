"""1-bit print canvas.

Every printout is drawn as a white image exactly as wide as the paper's
printable width (576 dots on 80 mm, 420 on 58 mm) and sent as raster. Blocks
are drawn in greyscale, then thresholded (text, lines) or dithered (photos)
to 1-bit. All of this is CPU-bound: call it from the executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONT_DIR = Path(__file__).parent / "fonts"
FONTS = {
    ("sans", False): "AtkinsonHyperlegible-Regular.ttf",
    ("sans", True): "AtkinsonHyperlegible-Bold.ttf",
    ("mono", False): "JetBrainsMono-Regular.ttf",
    ("mono", True): "JetBrainsMono-Bold.ttf",
}
MARGIN = 8
WHITE = 255
BLACK = 0


@lru_cache(maxsize=32)
def font(
    family: str = "sans", px: int = 28, bold: bool = False
) -> ImageFont.FreeTypeFont:
    """Load a bundled font at a pixel size."""
    return ImageFont.truetype(str(FONT_DIR / FONTS[(family, bold)]), px)


def wrap(text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Greedy word wrap by rendered width; hard-breaks words that don't fit."""
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in para.split(" "):
            candidate = f"{line} {word}" if line else word
            if face.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            rest = word
            while face.getlength(rest) > width:
                cut = len(rest)
                while cut > 1 and face.getlength(rest[:cut]) > width:
                    cut -= 1
                lines.append(rest[:cut])
                rest = rest[cut:]
            line = rest
        lines.append(line)
    return lines


@dataclass
class Canvas:
    """A stack of greyscale blocks that becomes one 1-bit image."""

    width: int
    blocks: list[Image.Image] = field(default_factory=list)

    @property
    def inner(self) -> int:
        """Usable width inside the side margins."""
        return self.width - 2 * MARGIN

    @property
    def height(self) -> int:
        """Current height in dots."""
        return sum(b.height for b in self.blocks)

    def space(self, px: int) -> None:
        """Add blank paper."""
        if px > 0:
            self.blocks.append(Image.new("L", (self.width, px), WHITE))

    def text(
        self,
        value: str,
        *,
        px: int = 28,
        bold: bool = False,
        family: str = "sans",
        align: str = "left",
        line_gap: float = 0.25,
    ) -> None:
        """Add wrapped text."""
        face = font(family, px, bold)
        ascent, descent = face.getmetrics()
        line_h = ascent + descent + int(px * line_gap)
        lines = wrap(value, face, self.inner)
        block = Image.new("L", (self.width, line_h * len(lines)), WHITE)
        draw = ImageDraw.Draw(block)
        for i, line in enumerate(lines):
            w = face.getlength(line)
            if align == "center":
                x = MARGIN + (self.inner - w) / 2
            elif align == "right":
                x = MARGIN + self.inner - w
            else:
                x = MARGIN
            draw.text((x, i * line_h), line, font=face, fill=BLACK)
        self.blocks.append(block)

    def title(self, value: str, px: int = 44) -> None:
        """Add a centered bold heading."""
        self.text(value, px=px, bold=True, align="center", line_gap=0.1)

    def rule(self, *, dashed: bool = False, thickness: int = 2, pad: int = 10) -> None:
        """Add a horizontal line (solid, or dashed for "fold here")."""
        block = Image.new("L", (self.width, thickness + 2 * pad), WHITE)
        draw = ImageDraw.Draw(block)
        if dashed:
            for x in range(MARGIN, self.width - MARGIN, 16):
                draw.rectangle((x, pad, x + 9, pad + thickness - 1), fill=BLACK)
        else:
            draw.rectangle(
                (MARGIN, pad, self.width - MARGIN - 1, pad + thickness - 1), fill=BLACK
            )
        self.blocks.append(block)

    def image(self, img: Image.Image, *, dither: bool = True, fit: bool = True) -> None:
        """Add a picture, scaled to the inner width and converted to 1-bit."""
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            backdrop = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(backdrop, img)
        img = img.convert("L")
        if fit and img.width != self.inner:
            ratio = self.inner / img.width
            img = img.resize(
                (self.inner, max(1, round(img.height * ratio))),
                Image.Resampling.LANCZOS,
            )
        mono = img.convert(
            "1", dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
        )
        block = Image.new("L", (self.width, mono.height), WHITE)
        block.paste(mono.convert("L"), ((self.width - mono.width) // 2, 0))
        self.blocks.append(block)

    def drawing(self, img: Image.Image) -> None:
        """Add a full-width greyscale drawing (already laid out to ``width``)."""
        if img.width != self.width:
            raise ValueError(f"drawing must be {self.width} px wide")
        self.blocks.append(img.convert("L"))

    def footer(self, *fields: str) -> None:
        """Add the small footer line: type, difficulty, date, ID."""
        self.rule(thickness=1, pad=6)
        self.text("  ·  ".join(f for f in fields if f), px=18, align="center")

    def render(self, max_height: int | None = None) -> tuple[Image.Image, bool]:
        """Stack the blocks into one 1-bit image.

        Returns ``(image, truncated)``. When ``max_height`` is set the image is
        cut there and ends with a "trimmed" notice.
        """
        height = max(1, self.height)
        truncated = max_height is not None and height > max_height
        if truncated:
            assert max_height is not None
            notice = Canvas(self.width)
            notice.rule(dashed=True)
            notice.text("(trimmed: longest print reached)", px=20, align="center")
            keep = max(1, max_height - notice.height)
            height = keep + notice.height
        out = Image.new("L", (self.width, height), WHITE)
        y = 0
        for block in self.blocks:
            if truncated and y >= keep:
                break
            out.paste(block, (0, y))
            y += block.height
        if truncated:
            y = keep
            for block in notice.blocks:
                out.paste(block, (0, y))
                y += block.height
        return out.point(lambda p: 255 if p >= 128 else 0).convert("1"), truncated
