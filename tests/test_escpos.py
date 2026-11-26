"""ESC/POS byte output, raster banding and status parsing."""

from __future__ import annotations

from PIL import Image, ImageDraw
import pytest

from custom_components.tiny_press.printer import escpos
from custom_components.tiny_press.printer.escpos import PrinterStatus


def test_basic_commands() -> None:
    assert escpos.INIT == b"\x1b@"
    assert escpos.bold(True) == b"\x1bE\x01"
    assert escpos.bold(False) == b"\x1bE\x00"
    assert escpos.align("center") == b"\x1ba\x01"
    assert escpos.size(2, 2) == b"\x1d!\x11"
    assert escpos.size(1, 1) == b"\x1d!\x00"
    assert escpos.feed(3) == b"\x1bd\x03"
    assert escpos.cut() == b"\x1dVB\x03"
    assert escpos.status_request(4) == b"\x10\x04\x04"
    assert escpos.text("café") == b"caf\x82"
    with pytest.raises(ValueError):
        escpos.size(9, 1)
    with pytest.raises(ValueError):
        escpos.status_request(5)


def test_qr_code_snapshot() -> None:
    assert escpos.qr_code("hi", module=4, ecc="L") == (
        b"\x1d(k\x04\x001A2\x00"
        b"\x1d(k\x03\x001C\x04"
        b"\x1d(k\x03\x001E0"
        b"\x1d(k\x05\x001P0hi"
        b"\x1d(k\x03\x001Q0"
    )
    with pytest.raises(ValueError):
        escpos.qr_code("")
    with pytest.raises(ValueError):
        escpos.qr_code("x", module=17)


def _parse_bands(data: bytes) -> list[tuple[int, int, bytes]]:
    bands = []
    i = 0
    while i < len(data):
        assert data[i : i + 4] == b"\x1dv0\x00"
        xb = data[i + 4] | data[i + 5] << 8
        rows = data[i + 6] | data[i + 7] << 8
        body = data[i + 8 : i + 8 + xb * rows]
        bands.append((xb, rows, body))
        i += 8 + xb * rows
    return bands


def test_raster_bands_576() -> None:
    img = Image.new("1", (576, 300), 1)
    ImageDraw.Draw(img).rectangle((0, 0, 7, 0), fill=0)  # first 8 dots of row 0
    bands = _parse_bands(escpos.raster(img))
    assert [rows for _xb, rows, _ in bands] == [128, 128, 44]
    assert all(xb == 72 for xb, _rows, _ in bands)
    first = bands[0][2]
    assert first[0] == 0xFF and first[1] == 0
    assert sum(len(b[2]) for b in bands) == 72 * 300
    assert len(escpos.raster(img)) <= 3 * (8 + 72 * 128)


def test_raster_pads_58mm_width_with_white() -> None:
    img = Image.new("1", (420, 2), 0)  # all black
    ((xb, rows, body),) = _parse_bands(escpos.raster(img))
    assert (xb, rows) == (53, 2)
    # 420 = 52 bytes + 4 bits: last byte keeps the top 4 bits only.
    assert body[51] == 0xFF and body[52] == 0xF0
    assert body[53 + 52] == 0xF0


def test_raster_needs_1bit() -> None:
    with pytest.raises(ValueError):
        escpos.raster(Image.new("L", (8, 8)))


@pytest.mark.parametrize(
    ("raw", "online", "cover", "near", "out", "error"),
    [
        ((0x16, 0x12, 0x12), True, False, False, False, False),
        ((0x1E, 0x16, 0x12), False, True, False, False, False),
        ((0x16, 0x12, 0x1E), True, False, True, False, False),
        ((0x1E, 0x32, 0x7E), False, False, True, True, False),
        ((0x1E, 0x52, 0x12), False, False, False, False, True),
    ],
)
def test_status_parse(raw, online, cover, near, out, error) -> None:
    status = PrinterStatus.parse(*raw)
    assert status.online is online
    assert status.cover_open is cover
    assert status.paper_near_end is near
    assert status.paper_out is out
    assert status.error is error


def test_status_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        PrinterStatus.parse(0x00, 0x12, 0x12)
