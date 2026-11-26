"""Bundled jokes/facts and the ai_task path."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.tiny_press.ai import async_ai_joke
from custom_components.tiny_press.generators import jokes
from custom_components.tiny_press.generators.data import load_json
from custom_components.tiny_press.profiles import DEFAULT_KID


def test_bundled_lists_are_big_enough() -> None:
    assert jokes.offline_count(jokes.JOKE) >= 100
    assert jokes.offline_count(jokes.FACT) >= 100
    joke_list = load_json("jokes.json")
    assert all(len(j) == 2 and j[0].endswith("?") and j[1] for j in joke_list)
    assert len({j[0] for j in joke_list}) == len(joke_list)
    facts = load_json("facts.json")
    assert len(set(facts)) == len(facts)
    assert all(len(f) < 160 for f in facts)


def test_pick_avoids_recent() -> None:
    a = jokes.pick(jokes.JOKE, 1)
    assert a == jokes.pick(jokes.JOKE, 1)
    assert a.punchline and a.source == "offline"
    b = jokes.pick(jokes.JOKE, 1, recent=[a.index])
    assert b.index != a.index
    every = list(range(jokes.offline_count(jokes.JOKE)))
    assert jokes.pick(jokes.JOKE, 1, recent=every).index is not None
    fact = jokes.pick(jokes.FACT, 2)
    assert fact.punchline is None


def _register(hass: HomeAssistant, handler) -> None:
    hass.services.async_register(
        "ai_task", "generate_data", handler, supports_response=SupportsResponse.ONLY
    )


async def test_ai_joke(hass: HomeAssistant) -> None:
    seen: list[dict[str, Any]] = []

    async def handler(call: ServiceCall) -> dict[str, Any]:
        seen.append(dict(call.data))
        return {"data": {"setup": "Why  is the sky blue?", "punchline": "It's shy!"}}

    _register(hass, handler)
    joke = await async_ai_joke(hass, "ai_task.test", jokes.JOKE, DEFAULT_KID)
    assert joke == jokes.Joke("joke", "Why is the sky blue?", "It's shy!", "ai")
    assert seen[0]["entity_id"] == "ai_task.test"
    assert "copyrighted" in seen[0]["instructions"]
    assert set(seen[0]["structure"]) == {"setup", "punchline"}


async def test_ai_fact(hass: HomeAssistant) -> None:
    async def handler(call: ServiceCall) -> dict[str, Any]:
        return {"data": {"fact": "Owls can see in the dark."}}

    _register(hass, handler)
    fact = await async_ai_joke(hass, "ai_task.test", jokes.FACT, DEFAULT_KID)
    assert fact is not None and fact.setup == "Owls can see in the dark."


@pytest.mark.parametrize(
    "reply",
    [
        {"data": {"setup": "", "punchline": "x"}},
        {"data": {"setup": "x" * 400, "punchline": "y"}},
        {"data": "just text"},
        {},
        {"data": {"setup": 3, "punchline": None}},
    ],
)
async def test_ai_bad_output_falls_back(hass: HomeAssistant, reply: dict) -> None:
    async def handler(call: ServiceCall) -> dict[str, Any]:
        return reply

    _register(hass, handler)
    assert await async_ai_joke(hass, "ai_task.test", jokes.JOKE, DEFAULT_KID) is None


async def test_ai_bad_fact_falls_back(hass: HomeAssistant) -> None:
    async def handler(call: ServiceCall) -> dict[str, Any]:
        return {"data": {"fact": ""}}

    _register(hass, handler)
    assert await async_ai_joke(hass, "ai_task.test", jokes.FACT, DEFAULT_KID) is None


async def test_ai_missing_or_failing(hass: HomeAssistant) -> None:
    assert await async_ai_joke(hass, None, jokes.JOKE, DEFAULT_KID) is None
    assert await async_ai_joke(hass, "ai_task.test", jokes.JOKE, DEFAULT_KID) is None

    async def handler(call: ServiceCall) -> dict[str, Any]:
        raise HomeAssistantError("quota")

    _register(hass, handler)
    assert await async_ai_joke(hass, "ai_task.test", jokes.JOKE, DEFAULT_KID) is None
