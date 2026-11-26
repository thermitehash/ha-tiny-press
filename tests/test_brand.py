"""Brand images and bundled font licenses ship with the integration."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "tiny_press"


@pytest.mark.parametrize(
    ("name", "short"),
    [
        ("icon", 256),
        ("icon@2x", 512),
        ("dark_icon", 256),
        ("dark_icon@2x", 512),
        ("logo", 256),
        ("logo@2x", 512),
        ("dark_logo", 256),
        ("dark_logo@2x", 512),
    ],
)
def test_brand_image(name: str, short: int) -> None:
    with Image.open(COMPONENT / "brand" / f"{name}.png") as img:
        assert img.format == "PNG"
        assert img.mode == "RGBA"
        assert min(img.size) == short
        if "icon" in name:
            assert img.size == (short, short)
        # Transparent background: the corners are see-through.
        assert img.getpixel((0, 0))[3] == 0


def test_fonts_have_licenses() -> None:
    fonts = COMPONENT / "render" / "fonts"
    assert (fonts / "OFL-AtkinsonHyperlegible.txt").is_file()
    assert (fonts / "OFL-JetBrainsMono.txt").is_file()
    assert len(list(fonts.glob("*.ttf"))) == 4
