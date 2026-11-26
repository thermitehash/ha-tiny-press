"""Spelling practice from a kid's own word list (e.g. this week's school list).

Pure and deterministic for a given seed:

* **Unscramble:** each word's letters shuffled (never left in order).
* **Missing letters:** each word with about a third of its letters blanked
  (never the first letter), so she fills in the gaps.

The word search for the same list is ``word_search.generate(words=...)``.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import re

MAX_WORDS = 15  # per sheet
MAX_PARSED = 50  # a longer list is sampled per sheet


def parse_words(text: str | list[str] | None) -> list[str]:
    """Split a typed list (commas, semicolons or new lines) into clean words."""
    if not text:
        return []
    items = text if isinstance(text, list) else re.split(r"[,;\n]+", text)
    seen: dict[str, None] = {}
    for item in items:
        word = re.sub(r"[^A-Za-z]", "", str(item)).lower()
        if len(word) >= 2:
            seen.setdefault(word, None)
    return list(seen)[:MAX_PARSED]


def scramble(word: str, rng: random.Random) -> str:
    """Shuffle letters so the result differs from the word when possible."""
    letters = list(word)
    if len(set(letters)) < 2:
        return word
    for _ in range(20):
        rng.shuffle(letters)
        if "".join(letters) != word:
            break
    return "".join(letters)


def blank_positions(word: str, rng: random.Random) -> list[int]:
    """Which letters to hide: about a third, at least one, never the first."""
    if len(word) < 2:
        return []
    count = max(1, min(len(word) - 1, round(len(word) * 0.35)))
    return sorted(rng.sample(range(1, len(word)), min(count, len(word) - 1)))


@dataclass(frozen=True, slots=True)
class SpellingSheet:
    """Both activities for one word list."""

    words: tuple[str, ...]
    scrambled: tuple[str, ...]
    blanks: tuple[tuple[int, ...], ...]

    def masked(self, index: int) -> str:
        """``c _ t`` for word ``index``."""
        word, hide = self.words[index], set(self.blanks[index])
        return " ".join("_" if i in hide else ch for i, ch in enumerate(word))

    def answer(self) -> dict[str, object]:
        """Answer-key data."""
        return {
            "words": list(self.words),
            "scrambled": list(self.scrambled),
            "blanks": [list(b) for b in self.blanks],
        }


def pick_words(words: list[str], seed: int) -> list[str]:
    """Up to ``MAX_WORDS`` words; a longer list is sampled differently per seed."""
    if len(words) <= MAX_WORDS:
        return list(words)
    return random.Random(f"pick-{seed}").sample(words, MAX_WORDS)


def generate(words: list[str], seed: int) -> SpellingSheet:
    """Build the unscramble and missing-letter activities."""
    if not words:
        raise ValueError("no spelling words")
    rng = random.Random(seed)
    order = pick_words(words, seed)
    rng.shuffle(order)
    return SpellingSheet(
        tuple(order),
        tuple(scramble(w, rng) for w in order),
        tuple(tuple(blank_positions(w, rng)) for w in order),
    )
