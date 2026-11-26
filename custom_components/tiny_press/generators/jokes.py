"""Jokes and fun facts: the bundled offline lists.

``ai.py`` asks an ``ai_task`` entity first; this module is the fallback and
is pure and deterministic for a given seed.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from .data import load_json

JOKE = "joke"
FACT = "fact"


@dataclass(frozen=True, slots=True)
class Joke:
    """A joke (setup + punchline) or a fact (setup only)."""

    kind: str
    setup: str
    punchline: str | None = None
    source: str = "offline"  # or "ai"
    index: int | None = None  # position in the bundled list

    def answer(self) -> dict[str, object]:
        """Return the data stored with the print (the punchline is the answer)."""
        return {"kind": self.kind, "setup": self.setup, "punchline": self.punchline}


def offline_count(kind: str) -> int:
    """How many bundled jokes or facts there are."""
    return len(load_json("jokes.json" if kind == JOKE else "facts.json"))


def pick(kind: str, seed: int, recent: list[int] | None = None) -> Joke:
    """Choose a bundled joke or fact, avoiding recently printed ones."""
    rng = random.Random(seed)
    if kind == JOKE:
        items: list[list[str]] = load_json("jokes.json")
    else:
        items = [[f] for f in load_json("facts.json")]
    avoid = set(recent or [])
    choices = [i for i in range(len(items)) if i not in avoid] or list(
        range(len(items))
    )
    index = rng.choice(choices)
    item = items[index]
    return Joke(kind, item[0], item[1] if len(item) > 1 else None, "offline", index)
