"""Tools Tiny Press gives AI agents (Claude, OpenAI, …) in an Assist pipeline.

With these, "print my daughter a dinosaur story" works through an AI agent
without turning on "Prefer handling commands locally". Kid prints still obey
kid-mode limits, and every print keeps its length cap.
"""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolAnnotations,
    ToolInput,
)
import probatio

from .const import DOMAIN
from .coordinator import TinyPressConfigEntry
from .fetch import feeds_from_options
from .voice import MAX_NOTE, MAX_TOPIC, NOTE, VOICE_TYPES, async_voice_print

PRINT_TYPES = [kind for kind in VOICE_TYPES if kind != NOTE]
_ANNOTATIONS = ToolAnnotations(destructive=False, open_world=False)


def _entries(hass: HomeAssistant) -> list[TinyPressConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def _printer_field(entries: list[TinyPressConfigEntry]) -> dict[Any, Any]:
    """Ask which printer only when there's more than one."""
    if len(entries) < 2:
        return {}
    return {
        probatio.Optional(
            "printer", description="Which printer, if the user names one."
        ): probatio.In([entry.title for entry in entries])
    }


def _feed_field(entries: list[TinyPressConfigEntry]) -> dict[Any, Any]:
    """Offer the configured feed names, for type feed."""
    names = sorted({f.name for e in entries for f in feeds_from_options(e.options)})
    if not names:
        return {}
    return {
        probatio.Optional(
            "feed", description="Which feed, for type feed. Empty uses the first."
        ): probatio.In(names)
    }


class _TinyPressTool(Tool):
    """Shared plumbing: pick the printer, print, return what to say."""

    integration = DOMAIN
    annotations = _ANNOTATIONS

    def __init__(self, entries: list[TinyPressConfigEntry]) -> None:
        """Keep the loaded printers."""
        self._entries = entries

    def _entry(self, args: dict[str, Any]) -> TinyPressConfigEntry:
        wanted = args.get("printer")
        for entry in self._entries:
            if entry.title == wanted:
                return entry
        return self._entries[0]

    async def _print(
        self, hass: HomeAssistant, args: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        entry = self._entry(args)
        return await async_voice_print(
            hass,
            entry.runtime_data,
            kind,
            profile=args.get("profile"),
            difficulty=args.get("difficulty"),
            topic=args.get("topic"),
            text=args.get("text"),
            feed=args.get("feed"),
        )


class PrintTool(_TinyPressTool):
    """Print a puzzle, joke, story, morning slip or the weather."""

    name = f"{DOMAIN}__print"
    title = "Print on Tiny Press"
    description = (
        "Print something on the household Tiny Press receipt printer: kid "
        "puzzles (maze, word_search, math, kid_pack, kid_sudoku, spelling, "
        "spelling_search), a "
        "joke or fun fact, a bedtime story (optionally about a topic) or the "
        "next chapter of the story in progress, adult puzzles (sudoku, "
        "crossword, cryptogram, puzzle_pack), the morning slip, the "
        "weather, or the newest headlines from one of the household's feeds "
        "(type feed, with the feed's name). Kid prints follow the household's kid-mode limits. Say the "
        "returned 'speech' to the user; when 'printed' is false it explains "
        "why nothing printed."
    )

    def __init__(self, entries: list[TinyPressConfigEntry]) -> None:
        """Build the parameters (a printer choice only with several printers)."""
        super().__init__(entries)
        self.parameters = probatio.Schema(
            {
                probatio.Required("type", description="What to print."): probatio.In(
                    PRINT_TYPES
                ),
                probatio.Optional(
                    "profile",
                    description=(
                        "The kid's (or adult's) profile name, if the user says "
                        "who it's for."
                    ),
                ): str,
                probatio.Optional(
                    "difficulty", description="Only if the user asks for one."
                ): probatio.In(["easy", "medium", "hard"]),
                probatio.Optional(
                    "topic", description="Story topic, for type story only."
                ): probatio.All(str, probatio.Length(max=MAX_TOPIC)),
                **_feed_field(entries),
                **_printer_field(entries),
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> dict[str, Any]:
        args = tool_input.tool_args
        return await self._print(hass, args, args["type"])


class PrintNoteTool(_TinyPressTool):
    """Print a short note the user dictates."""

    name = f"{DOMAIN}__print_note"
    title = "Print a note on Tiny Press"
    description = (
        "Print a short note (a reminder, list or message) on the Tiny Press "
        "receipt printer, exactly as the user dictates it. Say the returned "
        "'speech' to the user."
    )

    def __init__(self, entries: list[TinyPressConfigEntry]) -> None:
        """Build the parameters (a printer choice only with several printers)."""
        super().__init__(entries)
        self.parameters = probatio.Schema(
            {
                probatio.Required("text", description="The note's text."): probatio.All(
                    str, probatio.Length(min=1, max=MAX_NOTE)
                ),
                **_printer_field(entries),
            }
        )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> dict[str, Any]:
        return await self._print(hass, tool_input.tool_args, NOTE)


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return Tiny Press's tools for the Assist API, when a printer is loaded."""
    if api_id != LLM_API_ASSIST or not (entries := _entries(hass)):
        return None
    return LLMTools(tools=[PrintTool(entries), PrintNoteTool(entries)])
