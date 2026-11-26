"""Bundled data files (cached after the first read).

The first read happens in the executor during setup, so lookups from the
event loop afterwards never touch the disk.
"""

from __future__ import annotations

from functools import cache
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FILES = (
    "words.json",
    "themes.json",
    "jokes.json",
    "facts.json",
    "crossword.json",
    "quotes.json",
    "stories.json",
)


@cache
def load_json(name: str) -> Any:
    """Load one bundled JSON file."""
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def preload() -> None:
    """Read every data file (call from the executor)."""
    for name in FILES:
        load_json(name)
