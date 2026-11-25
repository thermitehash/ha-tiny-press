"""ESC/POS command builders for the Epson TM-m30III.

Pure functions that return bytes; nothing here touches the network. Command
references are Epson's ESC/POS Application Programming Guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

ESC = b"\x1b"
GS = b"\x1d"
DLE = b"\x10"
EOT = b"\x04"
LF = b"\n"

INIT = ESC + b"@"
ENCODING = "cp437"

# GS v 0 is limited by the printer's receive buffer, so images go out in
# horizontal bands. 128 rows of 576 dots is 9 KiB per command.
BAND_ROWS = 128

# DLE EOT n (real-time status transmission).
STATUS_PRINTER = 1
STATUS_OFFLINE = 2
STATUS_ERROR = 3
STATUS_PAPER = 4


def bold(on: bool) -> bytes:
    """ESC E n: emphasized mode."""
    return ESC + b"E" + (b"\x01" if on else b"\x00")


def align(mode: str) -> bytes:
    """ESC a n: justification (left, center, right)."""
    return ESC + b"a" + bytes([{"left": 0, "center": 1, "right": 2}[mode]])


def size(width: int = 1, height: int = 1) -> bytes:
    """GS ! n: character size, 1-8 times in each direction."""
    if not (1 <= width <= 8 and 1 <= height <= 8):
        raise ValueError("character size must be 1-8")
    return GS + b"!" + bytes([((width - 1) << 4) | (height - 1)])


def text(value: str) -> bytes:
    """Encode text for the printer's default code page (PC437)."""
    return value.encode(ENCODING, "replace")


def feed(lines: int) -> bytes:
    """ESC d n: print and feed n lines."""
    return ESC + b"d" + bytes([max(0, min(lines, 255))])


def cut(feed_units: int = 3) -> bytes:
    """GS V 66 n: feed to the cutter position plus n units, then partial cut."""
    return GS + b"V" + bytes([66, max(0, min(feed_units, 255))])


def status_request(n: int) -> bytes:
    """DLE EOT n: ask for one real-time status byte."""
    if n not in (STATUS_PRINTER, STATUS_OFFLINE, STATUS_ERROR, STATUS_PAPER):
        raise ValueError("DLE EOT n must be 1-4")
    return DLE + EOT + bytes([n])


def qr_code(data: str, module: int = 6, ecc: str = "M") -> bytes:
    """GS ( k: store and print a Model 2 QR code."""
    payload = data.encode("utf-8")
    if not payload or len(payload) > 7089:
        raise ValueError("QR data must be 1-7089 bytes")
    if not 1 <= module <= 16:
        raise ValueError("QR module size must be 1-16")
    level = {"L": 48, "M": 49, "Q": 50, "H": 51}[ecc]

    def fn(body: bytes) -> bytes:
        n = len(body)
        return GS + b"(k" + bytes([n & 0xFF, n >> 8]) + body

    return (
        fn(b"1A" + bytes([50, 0]))  # fn 165: model 2
        + fn(b"1C" + bytes([module]))  # fn 167: module size
        + fn(b"1E" + bytes([level]))  # fn 169: error correction
        + fn(b"1P0" + payload)  # fn 180: store data
        + fn(b"1Q0")  # fn 181: print
    )


def raster(image: Image.Image, band_rows: int = BAND_ROWS) -> bytes:
    """GS v 0: print a 1-bit image as raster bands.

    Black pixels (0 in Pillow mode "1") are printed dots. The width is padded
    to a whole byte with white.
    """
    if image.mode != "1":
        raise ValueError("raster images must be mode '1'")
    width, height = image.size
    row_bytes = (width + 7) // 8
    # Pillow packs mode "1" with 1 = white; ESC/POS wants 1 = dot.
    packed = bytes(b ^ 0xFF for b in image.tobytes())
    pad_mask = (0xFF << (row_bytes * 8 - width)) & 0xFF
    out = bytearray()
    for top in range(0, height, band_rows):
        rows = min(band_rows, height - top)
        out += GS + b"v0\x00"
        out += bytes([row_bytes & 0xFF, row_bytes >> 8, rows & 0xFF, rows >> 8])
        for y in range(top, top + rows):
            row = bytearray(packed[y * row_bytes : (y + 1) * row_bytes])
            row[-1] &= pad_mask
            out += row
    return bytes(out)


@dataclass(frozen=True, slots=True)
class PrinterStatus:
    """Parsed DLE EOT 1/2/4 responses."""

    online: bool
    cover_open: bool
    paper_near_end: bool
    paper_out: bool
    error: bool
    raw: tuple[int, int, int]

    @classmethod
    def parse(cls, printer: int, offline: int, paper: int) -> PrinterStatus:
        """Decode the three status bytes.

        * n=1 bit 3: offline.
        * n=2 bit 2: cover open; bit 5: stopped by paper end; bit 6: error.
        * n=4 bits 2-3: roll paper near-end; bits 5-6: roll paper end.
        """
        for byte in (printer, offline, paper):
            # Every DLE EOT reply has bit 1 and bit 4 set and bits 0 and 7 clear.
            if byte & 0x93 != 0x12:
                raise ValueError(f"not a DLE EOT status byte: {byte:#04x}")
        return cls(
            online=not printer & 0x08,
            cover_open=bool(offline & 0x04),
            paper_near_end=bool(paper & 0x0C),
            paper_out=bool(paper & 0x60) or bool(offline & 0x20),
            error=bool(offline & 0x40),
            raw=(printer, offline, paper),
        )
