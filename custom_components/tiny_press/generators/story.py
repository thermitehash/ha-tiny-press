"""Bedtime stories: the story model, length rules and bundled offline stories.

AI stories come from ``ai.py``; this module is pure (validation, trimming
and choosing a bundled story by length).
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import re

from .data import load_json

LENGTHS: dict[str, tuple[int, int]] = {
    "short": (250, 350),
    "medium": (400, 550),
    "long": (600, 750),
}
DEFAULT_LENGTH = "medium"
MAX_WORDS = 900  # hard cap whatever the AI sends
CLOSING_LINE = "And that is where tonight's story ends. Sweet dreams."
_URL = re.compile(r"(https?://|www\.)", re.IGNORECASE)


def word_count(paragraphs: list[str] | tuple[str, ...]) -> int:
    """Words in a story."""
    return sum(len(p.split()) for p in paragraphs)


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; tidy whitespace; drop empties."""
    parts = re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip())
    return [" ".join(p.split()) for p in parts if p.strip()]


def trim(paragraphs: list[str], max_words: int) -> tuple[list[str], bool]:
    """Keep whole paragraphs up to ``max_words``; add a closing line if cut."""
    kept: list[str] = []
    total = 0
    for para in paragraphs:
        words = len(para.split())
        if kept and total + words > max_words:
            return [*kept, CLOSING_LINE], True
        kept.append(para)
        total += words
    return kept, False


def is_clean(text: str) -> bool:
    """Reject links and stray markup in AI output."""
    return not _URL.search(text) and "<" not in text and "```" not in text


@dataclass(frozen=True, slots=True)
class Story:
    """One printable story or chapter."""

    title: str
    paragraphs: tuple[str, ...]
    choices: tuple[str, ...] = ()  # "A" and "B" options for a serial chapter
    chapter: int | None = None  # serial chapters only
    source: str = "offline"  # or "ai"
    credit: str | None = None
    summary: str = ""  # story so far (serials)

    @property
    def words(self) -> int:
        """Word count."""
        return word_count(self.paragraphs)

    def answer(self) -> dict[str, object]:
        """Return the data stored with the print (lets it be re-printed)."""
        return {
            "title": self.title,
            "paragraphs": list(self.paragraphs),
            "choices": list(self.choices),
            "chapter": self.chapter,
        }


def offline_stories(length: str) -> list[dict]:
    """Bundled stories of a length (any length if none match)."""
    stories = load_json("stories.json")
    matching = [s for s in stories if s["length"] == length]
    return matching or stories


def pick_offline(length: str, seed: int, recent: list[str] | None = None) -> Story:
    """Choose a bundled story, avoiding recently printed titles."""
    rng = random.Random(seed)
    options = offline_stories(length)
    fresh = [s for s in options if s["title"] not in set(recent or [])] or options
    chosen = rng.choice(fresh)
    return Story(
        chosen["title"],
        tuple(chosen["paragraphs"]),
        source="offline",
        credit=chosen.get("credit"),
    )
