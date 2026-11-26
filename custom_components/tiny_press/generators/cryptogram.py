"""Cryptogram: a public-domain quote with every letter swapped for another.

Pure and deterministic for a given seed. No letter ever stands for itself.
Easy gives two letters away, medium one, hard none.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import random
import string

from .data import load_json

HINTS = {"easy": 2, "medium": 1, "hard": 0}


@dataclass(frozen=True, slots=True)
class Cryptogram:
    """The coded quote, its key and the free hint letters."""

    plain: str
    author: str
    cipher: str
    key: dict[str, str]  # plain letter -> cipher letter
    hints: tuple[str, ...]  # plain letters given away
    index: int

    def hint_pairs(self) -> list[tuple[str, str]]:
        """(cipher letter, plain letter) for each hint."""
        return [(self.key[p], p) for p in self.hints]

    def answer(self) -> dict[str, object]:
        """Answer-key data."""
        return {
            "plain": self.plain,
            "author": self.author,
            "cipher": self.cipher,
            "hints": list(self.hints),
            "key": self.key,
        }


def quotes() -> list[dict[str, str]]:
    """Return the bundled public-domain quotes."""
    return load_json("quotes.json")


def derangement(rng: random.Random) -> dict[str, str]:
    """Make a random letter substitution where no letter maps to itself."""
    letters = list(string.ascii_uppercase)
    while True:
        shuffled = letters[:]
        rng.shuffle(shuffled)
        if all(a != b for a, b in zip(letters, shuffled, strict=True)):
            return dict(zip(letters, shuffled, strict=True))


def encode(text: str, key: dict[str, str]) -> str:
    """Upper-case the text and swap every letter; keep spaces and punctuation."""
    return "".join(key.get(ch, ch) for ch in text.upper())


def generate(difficulty: str, seed: int, recent: list[int] | None = None) -> Cryptogram:
    """Pick a quote (avoiding recent ones) and code it."""
    rng = random.Random(seed)
    items = quotes()
    avoid = set(recent or [])
    choices = [i for i in range(len(items)) if i not in avoid] or list(
        range(len(items))
    )
    index = rng.choice(choices)
    quote = items[index]
    key = derangement(rng)
    plain = quote["text"]
    counts = Counter(ch for ch in plain.upper() if ch.isalpha())
    # Hints: the most common letters, which help the most.
    hints = tuple(ch for ch, _ in counts.most_common(HINTS.get(difficulty, 1)))
    return Cryptogram(plain, quote["author"], encode(plain, key), key, hints, index)
