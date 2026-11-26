"""Voice: print from a spoken request and always return something to say.

Shared by the ``tiny_press.voice_print`` action (which the Assist voice
phrases blueprint calls) and the tools Tiny Press gives AI agents
(``llm.py``). Problems such as kid-mode limits, an offline printer or a
missing spelling list come back as speech instead of an error, so a voice
request never fails silently.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from . import jobs
from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, PrintType
from .coordinator import TinyPressCoordinator
from .limits import KID_TYPES
from .services import (
    _DIFFICULTY_WORDS,
    _coordinator,
    async_morning_slip,
    async_print_type,
    async_story,
)

SERVICE_VOICE_PRINT = "voice_print"
NOTE = "note"
NEXT_CHAPTER = "next_chapter"
MAX_NOTE = 500
MAX_TOPIC = 120

# What a voice request can ask for. "note" prints dictated text and, like
# print_text, is an adult print: it never counts toward kid-mode limits.
VOICE_TYPES: tuple[str, ...] = (
    PrintType.MAZE,
    PrintType.WORD_SEARCH,
    PrintType.MATH,
    PrintType.KID_PACK,
    PrintType.KID_SUDOKU,
    PrintType.SPELLING,
    PrintType.JOKE,
    PrintType.FACT,
    PrintType.STORY,
    NEXT_CHAPTER,
    PrintType.SUDOKU,
    PrintType.CROSSWORD,
    PrintType.CRYPTOGRAM,
    PrintType.PUZZLE_PACK,
    PrintType.MORNING_SLIP,
    PrintType.WEATHER,
    NOTE,
)

_NAMES: dict[str, str] = {
    PrintType.MAZE: "a maze",
    PrintType.WORD_SEARCH: "a word search",
    PrintType.MATH: "a math sheet",
    PrintType.KID_PACK: "a kid pack",
    PrintType.KID_SUDOKU: "a kid sudoku",
    PrintType.SPELLING: "spelling practice",
    PrintType.SUDOKU: "a sudoku",
    PrintType.CROSSWORD: "a crossword",
    PrintType.CRYPTOGRAM: "a cryptogram",
    PrintType.PUZZLE_PACK: "a puzzle pack",
    PrintType.MORNING_SLIP: "your morning slip",
    PrintType.WEATHER: "the weather",
}

VOICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required("type"): vol.In(VOICE_TYPES),
        vol.Optional("profile"): vol.Any(None, cv.string),
        vol.Optional("difficulty"): vol.Any(None, cv.string),
        vol.Optional("topic"): vol.Any(None, cv.string),
        vol.Optional("text"): vol.Any(None, cv.string),
        vol.Optional("sentence"): vol.Any(None, cv.string),
    }
)


def _clean(value: Any, limit: int = 200) -> str | None:
    """Trim a spoken value; empty means not given."""
    text = " ".join(str(value or "").split())[:limit]
    return text or None


def difficulty_in(sentence: str | None) -> str | None:
    """Find a difficulty word spoken in the sentence ("print a hard maze")."""
    if not sentence:
        return None
    words = re.sub(r"[^a-z ]", " ", sentence.lower()).split()
    for options in _DIFFICULTY_WORDS.values():
        for word in words:
            if word in options:
                return word
    return None


def _spoken(err: HomeAssistantError) -> str:
    """Turn an error into something to read aloud."""
    message = str(err).strip()
    if not message or message == err.translation_key:
        return "Tiny Press couldn't print that right now."
    # Settings paths and action names don't read well aloud.
    for path, spoken in (
        ("Configure → Settings", "Tiny Press's settings"),
        ("Configure → Edit a profile", "Tiny Press's profile settings"),
        ("Configure → ", "Tiny Press's "),
    ):
        message = message.replace(path, spoken)
    return message


def _success_speech(kind: str, response: dict[str, Any], who: str) -> str:
    """Say what printed."""
    if kind == PrintType.JOKE:
        setup = response.get("setup") or ""
        punchline = response.get("punchline") or ""
        return f"{setup} ... {punchline}".strip(" .") if punchline else setup
    if kind == PrintType.FACT:
        return f"Here's a fun fact. {response.get('setup') or ''}".strip()
    if kind in (PrintType.STORY, NEXT_CHAPTER):
        title = response.get("title") or "a bedtime story"
        chapter = response.get("chapter")
        what = f"chapter {chapter} of {title}" if chapter else title
        return f"Printing {what}. Sweet dreams!"
    if kind == NOTE:
        return "Printing your note."
    name = _NAMES.get(kind, "that")
    if kind in KID_TYPES and who:
        return f"Printing {name} for {who}."
    return f"Printing {name}."


async def async_voice_print(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    kind: str,
    *,
    profile: str | None = None,
    difficulty: str | None = None,
    topic: str | None = None,
    text: str | None = None,
    sentence: str | None = None,
) -> dict[str, Any]:
    """Print a voice request. Never raises for the user's own problems.

    Returns ``printed`` and ``speech``, plus the print's own response data
    (``print_id``, a joke's ``setup`` and ``punchline``, a story's ``title``)
    when something printed.
    """
    profile = _clean(profile, 60)
    topic = _clean(topic, MAX_TOPIC)
    difficulty = _clean(difficulty, 30) or difficulty_in(sentence)
    try:
        if kind == NOTE:
            note = _clean(text, MAX_NOTE)
            if not note:
                return {"printed": False, "speech": "What should the note say?"}
            response = await coordinator.async_print(
                jobs.text_job(note, None, "normal")
            )
        elif kind == PrintType.STORY:
            response = await async_story(
                hass, coordinator, profile=profile, topic=topic
            )
        elif kind == NEXT_CHAPTER:
            response = await async_story(
                hass, coordinator, profile=profile, continuing=True
            )
        elif kind == PrintType.MORNING_SLIP:
            response = await async_morning_slip(hass, coordinator)
        else:
            response = await async_print_type(
                hass,
                coordinator,
                PrintType(kind),
                profile=profile,
                difficulty=difficulty,
            )
    except HomeAssistantError as err:
        return {"printed": False, "speech": _spoken(err)}
    who = ""
    if kind in KID_TYPES or kind in (PrintType.STORY, NEXT_CHAPTER):
        who = coordinator.kid_profile(profile).name
    data = {
        key: value
        for key, value in response.items()
        if key != "image" and isinstance(value, str | int | float | bool | None)
    }
    return {
        **data,
        "printed": True,
        "speech": _success_speech(kind, response, who),
    }


@callback
def async_setup_voice_service(hass: HomeAssistant) -> None:
    """Register ``tiny_press.voice_print``."""

    async def handle(call: ServiceCall) -> dict[str, Any]:
        try:
            coordinator = _coordinator(hass, call)
        except HomeAssistantError as err:
            return {"printed": False, "speech": _spoken(err)}
        return await async_voice_print(
            hass,
            coordinator,
            call.data["type"],
            profile=call.data.get("profile"),
            difficulty=call.data.get("difficulty"),
            topic=call.data.get("topic"),
            text=call.data.get("text"),
            sentence=call.data.get("sentence"),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_VOICE_PRINT,
        handle,
        schema=VOICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
