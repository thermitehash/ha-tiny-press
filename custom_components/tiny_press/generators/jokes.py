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
    credit: str | None = None  # where a bundled item comes from, printed small

    def answer(self) -> dict[str, object]:
        """Return the data stored with the print (the punchline is the answer)."""
        return {"kind": self.kind, "setup": self.setup, "punchline": self.punchline}


def offline_count(kind: str) -> int:
    """How many bundled jokes or facts there are."""
    return len(load_json("jokes.json" if kind == JOKE else "facts.json"))


def pick(kind: str, seed: int, recent: list[int] | None = None) -> Joke:
    """Choose a bundled joke or fact, avoiding recently printed ones."""
    rng = random.Random(seed)
    items: list[dict[str, str]] = load_json(
        "jokes.json" if kind == JOKE else "facts.json"
    )
    avoid = set(recent or [])
    choices = [i for i in range(len(items)) if i not in avoid] or list(
        range(len(items))
    )
    index = rng.choice(choices)
    item = items[index]
    if kind == JOKE:
        return Joke(
            JOKE, item["setup"], item["punchline"], "offline", index, item.get("credit")
        )
    return Joke(FACT, item["fact"], None, "offline", index, item.get("source"))


def pick_themed(
    kind: str,
    seed: int,
    jokes: tuple[dict[str, str], ...] = (),
    fact_sources: tuple[str, ...] = (),
    recent: list[int] | None = None,
) -> Joke | None:
    """Pick a joke from a theme's own jokes, or a fact from its sources (or None)."""
    rng = random.Random(seed)
    if kind == JOKE:
        if not jokes:
            return None
        item = rng.choice(list(jokes))
        return Joke(
            JOKE, item["setup"], item["punchline"], "offline", None, "Tiny Press"
        )
    if not fact_sources:
        return None
    items: list[dict[str, str]] = load_json("facts.json")
    matches = [
        i
        for i, fact in enumerate(items)
        if any(src in fact.get("source", "") for src in fact_sources)
    ]
    if not matches:
        return None
    avoid = set(recent or [])
    index = rng.choice([i for i in matches if i not in avoid] or matches)
    return Joke(
        FACT, items[index]["fact"], None, "offline", index, items[index].get("source")
    )
