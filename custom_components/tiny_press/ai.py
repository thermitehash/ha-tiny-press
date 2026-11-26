"""Ask an ``ai_task`` entity for kid-safe content, with strict output checks.

Any failure (no entity, the integration isn't loaded, a timeout, a refusal,
malformed output) returns None so callers fall back to bundled content.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .generators.jokes import FACT, JOKE, Joke
from .profiles import Profile

_LOGGER = logging.getLogger(__name__)

AI_TIMEOUT = 45.0
MAX_FIELD = 300

KID_RULES = (
    "Rules: it must be gentle, kind and age-appropriate for a child. "
    "No scary, violent, gross-out or mean content. No real people, no brands, "
    "no copyrighted characters, no references to alcohol, weapons or dating. "
    "Use simple words a child at this reading level can read on their own."
)


async def async_generate(
    hass: HomeAssistant,
    entity_id: str | None,
    task_name: str,
    instructions: str,
    structure: dict[str, Any],
) -> dict[str, Any] | None:
    """Call ``ai_task.generate_data`` and return the structured data, or None."""
    if not entity_id or not hass.services.has_service("ai_task", "generate_data"):
        return None
    try:
        async with asyncio.timeout(AI_TIMEOUT):
            response = await hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "entity_id": entity_id,
                    "task_name": task_name,
                    "instructions": instructions,
                    "structure": structure,
                },
                blocking=True,
                return_response=True,
            )
    except (HomeAssistantError, TimeoutError, ValueError) as err:
        _LOGGER.info("ai_task %s failed, using bundled content: %s", task_name, err)
        return None
    data = (response or {}).get("data")
    return data if isinstance(data, dict) else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value if 0 < len(value) <= MAX_FIELD else None


async def async_ai_joke(
    hass: HomeAssistant, entity_id: str | None, kind: str, profile: Profile
) -> Joke | None:
    """Ask the AI for a fresh joke or fact; None on any failure."""
    interests = f" They like: {profile.interests}." if profile.interests else ""
    grade = (
        "kindergarten"
        if profile.reading_grade == "K"
        else f"grade {profile.reading_grade}"
    )
    if kind == JOKE:
        instructions = (
            f"Write one short, original, silly joke or riddle for a child who reads at a "
            f"{grade} level.{interests} Give a one-sentence setup (a question) and a short "
            f"punchline. {KID_RULES}"
        )
        structure = {
            "setup": {
                "description": "The question",
                "required": True,
                "selector": {"text": {}},
            },
            "punchline": {
                "description": "The answer",
                "required": True,
                "selector": {"text": {}},
            },
        }
    else:
        instructions = (
            f"Share one surprising, true fun fact for a child who reads at a {grade} "
            f"level.{interests} One or two short sentences. Only well-established facts. "
            f"{KID_RULES}"
        )
        structure = {
            "fact": {
                "description": "The fact",
                "required": True,
                "selector": {"text": {}},
            },
        }
    data = await async_generate(
        hass, entity_id, f"Tiny Press {kind}", instructions, structure
    )
    if data is None:
        return None
    if kind == JOKE:
        setup, punchline = _text(data.get("setup")), _text(data.get("punchline"))
        if setup and punchline:
            return Joke(JOKE, setup, punchline, "ai")
        return None
    fact = _text(data.get("fact"))
    return Joke(FACT, fact, None, "ai") if fact else None
