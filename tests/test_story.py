"""Bedtime stories: AI, offline fallback, serial adventures, limits."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.ai import story_instructions
from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS
from custom_components.tiny_press.generators import story
from custom_components.tiny_press.generators.data import load_json
from custom_components.tiny_press.profiles import Profile
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter

KID = {"id": "rosie", "kind": "kid", "name": "Rosie", "grade": "2", "interests": "owls"}
PARA = "The little owl looked at the stars and smiled. " * 6  # 54 words


def _story_text(words: int) -> str:
    paras = max(1, words // 54)
    return "\n\n".join(PARA.strip() for _ in range(paras))


# ---- pure helpers ----------------------------------------------------------


def test_bundled_stories_fit_their_lengths() -> None:
    stories = load_json("stories.json")
    for length, (low, high) in story.LENGTHS.items():
        matching = [s for s in stories if s["length"] == length]
        assert len(matching) >= 2
        for s in matching:
            assert low <= story.word_count(s["paragraphs"]) <= high, s["title"]
            assert s["credit"]


def test_split_trim_clean() -> None:
    assert story.split_paragraphs(" a  b \n\n\n c\n") == ["a b", "c"]
    paras = ["one two three"] * 5
    kept, cut = story.trim(paras, 7)
    assert cut and kept[-1] == story.CLOSING_LINE and len(kept) == 3
    assert story.trim(paras, 100) == (paras, False)
    assert not story.is_clean("see https://example.com")
    assert not story.is_clean("<b>x</b>")
    assert story.is_clean("A gentle tale.")


def test_pick_offline_avoids_recent() -> None:
    first = story.pick_offline("short", 1)
    other = story.pick_offline("short", 1, recent=[first.title])
    assert other.title != first.title
    assert story.pick_offline("nonsense", 1).paragraphs


def test_instructions_never_use_the_name() -> None:
    kid = Profile(id="rosie", kind="kid", name="Rosie", grade="2", interests="owls")
    text = story_instructions(kid, topic="moon", length="long")
    assert "Rosie" not in text
    assert "600 and 750" in text and "owls" in text and "made-up name" in text
    serial = story_instructions(
        kid,
        topic=None,
        length="short",
        series={
            "title": "T",
            "summary": "S",
            "chapter": 2,
            "choices": {"A": "go", "B": "stay"},
        },
        choice="B",
    )
    assert "chapter 3" in serial and "chose: stay" in serial
    gentle = story_instructions(
        kid,
        topic=None,
        length="short",
        series={"chapter": 1, "choices": {"A": "x", "B": "y"}},
    )
    assert "gentler" in gentle
    final = story_instructions(
        kid, topic=None, length="short", series={"chapter": 1}, final=True
    )
    assert "final chapter" in final


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_story_page_width(width: int) -> None:
    footer = layout.Footer("Story", "ST12", date(2026, 11, 26), "medium")
    s = story.Story("A Title", (PARA,) * 3, ("Fly to the moon", "Stay home"), 2)
    for item in (s, story.pick_offline("long", 2)):
        assert layout.story_page(width, item, footer).render()[0].width == width


# ---- through Home Assistant -------------------------------------------------


def _ai(hass: HomeAssistant, replies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(dict(call.data))
        return {"data": replies[min(len(calls), len(replies)) - 1]}

    hass.services.async_register(
        "ai_task", "generate_data", handler, supports_response=SupportsResponse.ONLY
    )
    return calls


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(
        entry, options={"profiles": [KID], **options}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, service: str, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


def _notice(hass: HomeAssistant) -> str | None:
    state = hass.states.get("persistent_notification.tiny_press_story_fallback")
    if state:
        return state.attributes.get("message")
    from homeassistant.components import persistent_notification

    notes = persistent_notification._async_get_or_create_notifications(hass)
    note = notes.get("tiny_press_story_fallback")
    return note["message"] if note else None


async def test_ai_story(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    calls = _ai(hass, [{"title": "Owl Night", "story": _story_text(450)}])
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    res = await _call(hass, "print_story", topic="the moon", length="medium")
    assert res["title"] == "Owl Night" and res["source"] == "ai"
    assert res["chapter"] is None and res["choices"] is None
    assert "Rosie" not in str(calls)
    assert "the moon" in calls[0]["instructions"]


async def test_short_story_is_retried_and_long_trimmed(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    calls = _ai(
        hass,
        [
            {"title": "Tiny", "story": _story_text(54)},
            {"title": "Huge", "story": _story_text(1500)},
        ],
    )
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    res = await _call(hass, "print_story", length="short")
    assert len(calls) == 2
    assert "only 54 words" in calls[1]["instructions"]
    assert res["title"] == "Huge" and res["words"] <= 350 + 50 + 20


async def test_offline_fallback_and_notice(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    res = await _call(hass, "print_story", length="long")
    assert res["source"] == "offline"
    assert "No AI task entity" in (_notice(hass) or "")
    again = await _call(hass, "print_story", length="long")
    assert again["title"] != res["title"]  # no repeat while others remain


async def test_bad_ai_output_falls_back(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    _ai(hass, [{"title": "Link", "story": "Visit https://example.com today."}])
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    res = await _call(hass, "print_story")
    assert res["source"] == "offline"
    assert "didn't return a usable story" in (_notice(hass) or "")


async def test_serial_adventure(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    chapter = {
        "title": "The Owl Map",
        "story": _story_text(300),
        "choice_a": "Follow the river",
        "choice_b": "Climb the hill",
        "summary": "An owl found a map.",
    }
    calls = _ai(hass, [chapter])
    await _setup(hass, config_entry, ai_task_entity="ai_task.claude")
    store = config_entry.runtime_data.store

    with pytest.raises(ServiceValidationError, match="no story in progress"):
        await _call(hass, "continue_story")

    one = await _call(hass, "print_story", mode="serial", topic="maps", length="short")
    assert one["chapter"] == 1
    assert one["choices"] == {"A": "Follow the river", "B": "Climb the hill"}
    assert store.series("rosie")["chapter"] == 1

    two = await _call(hass, "continue_story", choice="b")
    assert two["chapter"] == 2
    assert "chose: Climb the hill" in calls[-1]["instructions"]
    assert store.series("rosie")["history"] == ["B"]

    # Next chapter button: no choice, the AI picks the gentler one.
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.tiny_press_next_chapter"},
        blocking=True,
    )
    assert "gentler" in calls[-1]["instructions"]
    assert store.series("rosie")["chapter"] == 3

    final = await _call(hass, "continue_story", final=True)
    assert final["chapter"] == 4 and final["choices"] is None
    assert store.series("rosie") is None


async def test_serial_without_ai_keeps_the_series(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    store = config_entry.runtime_data.store
    store.set_series(
        "rosie", {"title": "T", "chapter": 2, "choices": {"A": "a", "B": "b"}}
    )
    res = await _call(hass, "continue_story", choice="A")
    assert res["source"] == "offline"
    assert "chapters need the AI" in (_notice(hass) or "")
    assert store.series("rosie")["chapter"] == 2


async def test_story_counts_toward_limits_and_length_select(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry, limits_enabled=True, limit_cooldown_s=3600)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.tiny_press_story_length", "option": "short"},
        blocking=True,
    )
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.tiny_press_bedtime_story"},
        blocking=True,
    )
    assert config_entry.runtime_data.store.last_print["difficulty"] == "short"
    with pytest.raises(ServiceValidationError, match="Just a moment"):
        await _call(hass, "print_story")
    res = await _call(hass, "print_story", ignore_limits=True)
    assert res["type"] == "story"
    # The general print action can print a story too; previews can't.
    via_print = await _call(hass, "print", type="story", ignore_limits=True)
    assert via_print["type"] == "story"
    with pytest.raises(ServiceValidationError, match="can't be previewed"):
        await _call(hass, "preview", type="story")
