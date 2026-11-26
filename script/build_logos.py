"""Build assets/logo.svg and assets/dark_logo.svg from the icon masters.

The wordmark is DM Sans Bold (SIL OFL 1.1). It is converted to outlines so
the SVG masters render identically without the font installed. The source
element it stands for is:

    <text x="280" y="146" font-family="DM Sans" font-weight="700"
          font-size="112" letter-spacing="-2">Tiny Press</text>

Run: python script/build_logos.py path/to/DMSans[opsz,wght].ttf
(needs ``fonttools``; only used when the brand changes).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TEXT = "Tiny Press"
X, Y, SIZE, SPACING = 280.0, 146.0, 112.0, -2.0
FILLS = {"logo": ("icon", "#2B3A4A"), "dark_logo": ("dark_icon", "#FFFFFF")}


def text_path(font_file: str) -> str:
    """Return SVG path data for the wordmark."""
    font = TTFont(font_file)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": 700, "opsz": 14})
    scale = SIZE / font["head"].unitsPerEm
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    pen = SVGPathPen(glyphs)
    x = X
    for char in TEXT:
        name = cmap[ord(char)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, Y)))
        x += hmtx[name][0] * scale + SPACING
    return pen.getCommands()


def main() -> None:
    """Write both logo masters."""
    path = text_path(sys.argv[1])
    for out, (icon, fill) in FILLS.items():
        body = (ASSETS / f"{icon}.svg").read_text()
        inner = re.sub(r"^<svg[^>]*>\n?|</svg>\s*$", "", body.strip())
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 216">\n'
            '<svg x="0" y="0" width="248" height="216" viewBox="4 22 248 216">\n'
            f"{inner}\n</svg>\n"
            "<!-- Tiny Press: DM Sans Bold 112, letter-spacing -2, as outlines -->\n"
            f'<path fill="{fill}" d="{path}"/>\n'
            "</svg>\n"
        )
        (ASSETS / f"{out}.svg").write_text(svg)


if __name__ == "__main__":
    main()
