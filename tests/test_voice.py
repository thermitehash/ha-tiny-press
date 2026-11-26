"""Voice: the voice_print action, the Assist phrases blueprint and AI-agent tools."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm as llm_helper
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tiny_press.const import DOMAIN
from custom_components.tiny_press.voice import difficulty_in

from .fake_printer import FakePrinter

BLUEPRINT = (
    Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "tiny_press"
    / "voice_phrases.yaml"
)
ROSIE = {"id": "rosie", "kind": "kid", "name": "Rosie", "grade": "2"}
COOLDOWN = {
    "limits_enabled": True,
    "limit_cooldown_s": 3600,
    "limit_admins_skip": False,
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(
        entry, options={"profiles": [ROSIE], **options}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _voice(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "voice_print", data, blocking=True, return_response=True
    )


def test_difficulty_in() -> None:
    assert difficulty_in("print a hard maze") == "hard"
    assert difficulty_in("Print an EASY sudoku!") == "easy"
    assert difficulty_in("print a maze for Rosie") is None
    assert difficulty_in(None) is None


async def test_voice_print_speech(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    res = await _voice(hass, type="maze", profile="rosie", sentence="print a hard maze")
    assert res["printed"] is True
    assert res["speech"] == "Printing a maze for Rosie."
    assert res["type"] == "maze" and res["print_id"]
    store = config_entry.runtime_data.store
    assert store.data["last_print"]["difficulty"] == "hard"

    joke = await _voice(hass, type="joke")
    assert joke["setup"] in joke["speech"] and joke["punchline"] in joke["speech"]
    fact = await _voice(hass, type="fact")
    assert fact["speech"].startswith("Here's a fun fact.")
    assert (await _voice(hass, type="sudoku", profile=""))["speech"] == (
        "Printing a sudoku."
    )
    story = await _voice(hass, type="story", topic="dragons")
    assert (
        story["speech"].endswith("Sweet dreams!") and story["title"] in story["speech"]
    )


async def test_voice_print_problems_are_spoken(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry, **COOLDOWN)
    assert (await _voice(hass, type="maze"))["printed"] is True
    blocked = await _voice(hass, type="maze")
    assert blocked == {
        "printed": False,
        "speech": blocked["speech"],
    } and blocked["speech"].startswith("Just a moment!")
    # Notes and adult puzzles are not kid prints: never limited.
    note = await _voice(hass, type="note", text="  Feed   the cat  ")
    assert note["printed"] is True and note["speech"] == "Printing your note."
    assert (await _voice(hass, type="crossword"))["printed"] is True
    assert (await _voice(hass, type="note", text=" "))["speech"] == (
        "What should the note say?"
    )
    chapter = await _voice(hass, type="next_chapter")
    assert chapter["printed"] is False  # blocked by the cooldown first
    weather = await _voice(hass, type="weather")
    assert weather["printed"] is False
    assert "weather entity" in weather["speech"]
    assert weather["speech"] == (
        "Choose a weather entity under Tiny Press's settings to print the weather"
    )


async def test_voice_print_without_a_printer(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    res = await _voice(hass, type="joke")
    assert res["printed"] is False and res["speech"]


async def test_blueprint_phrases(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.get(
        "https://news.example.com/rss",
        content=b"<rss><channel><title>N</title><item><title>Hi</title></item>"
        b"</channel></rss>",
    )
    await _setup(
        hass,
        config_entry,
        feeds=[
            {
                "id": "news",
                "name": "Example News",
                "url": "https://news.example.com/rss",
            }
        ],
    )
    folder = Path(hass.config.path("blueprints/automation/tiny_press"))
    await hass.async_add_executor_job(lambda: folder.mkdir(parents=True, exist_ok=True))
    await hass.async_add_executor_job(shutil.copy, BLUEPRINT, folder)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "id": "tiny_press_voice",
                "use_blueprint": {
                    "path": "tiny_press/voice_phrases.yaml",
                    "input": {
                        "printer": config_entry.entry_id,
                        "turned_on": [
                            "maze",
                            "joke",
                            "story_topic",
                            "note",
                            "sudoku",
                            "feed",
                        ],
                    },
                },
            }
        },
    )
    await hass.async_block_till_done()

    async def say(text: str) -> str:
        result = await conversation.async_converse(
            hass, text, None, Context(), language="en"
        )
        return result.response.speech["plain"]["speech"]

    assert await say("print a hard maze for Rosie") == "Printing a maze for Rosie."
    store = config_entry.runtime_data.store
    assert store.data["last_print"]["difficulty"] == "hard"
    assert await say("Print a maze.") == "Printing a maze for Rosie."
    assert "..." in await say("tell me a joke")
    assert (await say("print a story about a brave dragon")).endswith("Sweet dreams!")
    assert await say("print a note that says feed the cat") == "Printing your note."
    assert store.data["last_print"]["type"] == "text"
    assert await say("print an easy sudoku") == "Printing a sudoku."
    assert store.data["last_print"]["difficulty"] == "easy"
    assert await say("print the news") == "Printing 1 headline from Example News."
    assert await say("print the headlines from example news") == (
        "Printing 1 headline from Example News."
    )
    last = store.data["last_print"]["print_id"]
    # Word search phrases are turned off in this blueprint instance.
    assert await say("print a word search") != "Printing a word search for Rosie."
    assert store.data["last_print"]["print_id"] == last


async def test_llm_tools(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry, **COOLDOWN)
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "llm", {})
    context = llm_helper.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant=conversation.DOMAIN,
        device_id=None,
    )
    api = await llm_helper.async_get_api(hass, llm_helper.LLM_API_ASSIST, context)
    tools = {tool.name: tool for tool in api.tools}
    assert {"tiny_press__print", "tiny_press__print_note"} <= set(tools)
    print_tool = tools["tiny_press__print"]
    assert print_tool.parameters({"type": "maze", "difficulty": "hard"})
    with pytest.raises(Exception):  # noqa: B017 - schema rejects unknown types
        print_tool.parameters({"type": "test_page"})

    res = (
        await api.async_call_tool(
            llm_helper.ToolInput(
                "tiny_press__print", {"type": "maze", "profile": "Rosie"}
            )
        )
    ).data
    assert res["printed"] is True and res["speech"] == "Printing a maze for Rosie."
    blocked = (
        await api.async_call_tool(
            llm_helper.ToolInput("tiny_press__print", {"type": "joke"})
        )
    ).data
    assert blocked["printed"] is False and "next print" in blocked["speech"]
    note = (
        await api.async_call_tool(
            llm_helper.ToolInput("tiny_press__print_note", {"text": "Buy milk"})
        )
    ).data
    assert note["printed"] is True


async def test_llm_tools_need_a_loaded_printer(hass: HomeAssistant) -> None:
    from custom_components.tiny_press import llm as tp_llm

    context = llm_helper.LLMContext("test", None, "en", "conversation", None)
    assert tp_llm.async_get_tools(hass, context, llm_helper.LLM_API_ASSIST) is None
    assert tp_llm.async_get_tools(hass, context, "other") is None
