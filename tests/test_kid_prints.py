"""Kid prints through the action and buttons."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.const import DOMAIN

from .fake_printer import FakePrinter

ROSIE = {
    "id": "rosie",
    "kind": "kid",
    "name": "Rosie",
    "grade": "2",
    "interests": "dinosaurs",
    "stretch": False,
}
MAX = {"id": "max", "kind": "kid", "name": "Max", "grade": "4"}


@pytest.fixture
async def kid_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> MockConfigEntry:
    hass.config_entries.async_update_entry(
        config_entry, options={"profiles": [ROSIE, MAX]}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _print(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print", data, blocking=True, return_response=True
    )


async def _jobs(printer: FakePrinter, count: int) -> list[bytes]:
    for _ in range(100):
        if len(printer.jobs) >= count:
            break
        await asyncio.sleep(0.01)
    return printer.jobs


async def test_word_search_and_math_use_profile(
    hass: HomeAssistant, kid_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    store = kid_entry.runtime_data.store
    ws = await _print(hass, type="word_search", seed=3)
    assert ws["profile"] == "Rosie"  # first kid is the default
    assert store.history[0]["answer"]["grade"] == "2"
    assert store.history[0]["answer"]["size"] == 10

    math = await _print(hass, type="math", profile="max", seed=3)
    assert math["profile"] == "Max"
    assert store.history[0]["answer"]["grade"] == "4"
    assert hass.states.get("sensor.tiny_press_last_print").attributes["difficulty"] == (
        "Grade 4"
    )
    assert len(await _jobs(printer, 2)) == 2


async def test_kid_profile_select_drives_buttons(
    hass: HomeAssistant, kid_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    select = "select.tiny_press_kid_profile"
    state = hass.states.get(select)
    assert state.state == "Rosie"
    assert state.attributes["options"] == ["Rosie", "Max"]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "Max"}, blocking=True
    )
    assert hass.states.get(select).state == "Max"
    for button in ("word_search", "math", "joke", "kid_pack"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": f"button.tiny_press_{button}"},
            blocking=True,
        )
    await _jobs(printer, 4)
    last = hass.states.get("sensor.tiny_press_last_print")
    assert last.state == "kid_pack"
    assert last.attributes["profile"] == "Max"


async def test_kid_pack_is_one_job_with_three_keys(
    hass: HomeAssistant, kid_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    response = await _print(hass, type="kid_pack", seed=11, difficulty="easy")
    assert response["type"] == "kid_pack"
    assert len(response["print_ids"]) == 3
    assert response["print_id"] == response["print_ids"][0]
    jobs = await _jobs(printer, 1)
    assert len(jobs) == 1 and jobs[0].count(b"\x1dVB") == 1  # one cut
    history = kid_entry.runtime_data.store.history
    assert {h["type"] for h in history[:3]} == {"maze", "word_search", "math"}
    assert {h["print_id"] for h in history[:3]} == set(response["print_ids"])
    maze = next(h for h in history if h["type"] == "maze")
    assert maze["answer"]["difficulty"] == "easy"
    # Same seed, same pack.
    again = await _print(hass, type="kid_pack", seed=11, difficulty="easy")
    assert again["print_ids"] == response["print_ids"]


async def test_joke_offline_rotates(
    hass: HomeAssistant, kid_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    first = await _print(hass, type="joke")
    assert first["source"] == "offline"
    assert first["setup"].endswith("?") and first["punchline"]
    store = kid_entry.runtime_data.store
    assert len(store.recent("joke")) == 1
    fact = await _print(hass, type="fact")
    assert fact["type"] == "fact" and fact["punchline"] is None
    assert len(store.recent("fact")) == 1
    # A seeded joke is repeatable.
    a = await _print(hass, type="joke", seed=5)
    store.data["recent"]["joke"] = []
    b = await _print(hass, type="joke", seed=5)
    assert a["setup"] == b["setup"]


async def test_joke_uses_ai_task(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    calls: list[dict[str, Any]] = []

    async def handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(dict(call.data))
        return {"data": {"setup": "What do clouds do for fun?", "punchline": "Float!"}}

    hass.services.async_register(
        "ai_task", "generate_data", handler, supports_response=SupportsResponse.ONLY
    )
    hass.config_entries.async_update_entry(
        config_entry,
        options={"profiles": [ROSIE], "ai_task_entity": "ai_task.claude"},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    response = await _print(hass, type="joke")
    assert response["source"] == "ai"
    assert response["punchline"] == "Float!"
    assert "grade 2" in calls[0]["instructions"]
    assert "dinosaurs" in calls[0]["instructions"]
    assert config_entry.runtime_data.store.recent("joke") == []
