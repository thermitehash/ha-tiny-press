"""Kid-mode rate limiter, preview and answer keys."""

from __future__ import annotations

import asyncio
import base64
from datetime import timedelta
import io
import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.tiny_press.card import CARD_URL
from custom_components.tiny_press.const import DOMAIN

from .fake_printer import FakePrinter

ROOT = Path(__file__).resolve().parent.parent
LIMITS = {
    "limits_enabled": True,
    "limit_cooldown_s": 60,
    "limit_per_hour": 3,
    "limit_per_day": 4,
    "limit_paper_mm_day": 5000,
    "limit_admins_skip": False,
}
LEFT = "sensor.tiny_press_kid_prints_left_today"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _print(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, "print", data, blocking=True, return_response=True
    )


async def test_limits_off_by_default(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    state = hass.states.get(LEFT)
    assert state.state == "unknown"
    assert state.attributes["enabled"] is False
    for _ in range(3):
        await _print(hass, type="joke")


async def test_cooldown_hour_and_day(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-11-26 15:00:00+00:00")
    await _setup(hass, config_entry, **LIMITS)
    events = async_capture_events(hass, "tiny_press_rate_limited")
    assert hass.states.get(LEFT).state == "4"

    await _print(hass, type="joke")
    state = hass.states.get(LEFT)
    assert state.state == "3"
    assert state.attributes["blocked_reason"] == "cooldown"
    assert state.attributes["next_print_at"].startswith("2026-11-26T15:01:00")

    # Cooldown blocks the action and the buttons alike.
    with pytest.raises(ServiceValidationError, match="Just a moment"):
        await _print(hass, type="maze")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.tiny_press_joke"}, blocking=True
        )
    await hass.async_block_till_done()
    assert events[0].data["reason"] == "cooldown"
    assert events[0].data["type"] == "maze"

    # Parents (and non-kid prints) aren't limited.
    await _print(hass, type="maze", ignore_limits=True)
    await hass.services.async_call(DOMAIN, "print_text", {"text": "hi"}, blocking=True)

    freezer.tick(timedelta(seconds=61))
    await _print(hass, type="math")
    freezer.tick(timedelta(seconds=61))
    await _print(hass, type="word_search")
    freezer.tick(timedelta(seconds=61))
    # Three in the last hour: the hourly limit kicks in.
    with pytest.raises(ServiceValidationError, match="lots of printing"):
        await _print(hass, type="fact")

    freezer.tick(timedelta(hours=1))
    await _print(hass, type="fact")
    freezer.tick(timedelta(minutes=5))
    with pytest.raises(ServiceValidationError, match="enough printing for today"):
        await _print(hass, type="joke")
    assert hass.states.get(LEFT).state == "0"

    # A new day resets the counts.
    freezer.move_to("2026-11-27 15:00:00+00:00")
    await config_entry.runtime_data.async_refresh()
    assert hass.states.get(LEFT).state == "4"
    await _print(hass, type="joke")


async def test_paper_budget(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(
        hass,
        config_entry,
        **{
            **LIMITS,
            "limit_cooldown_s": 0,
            "limit_per_hour": 0,
            "limit_paper_mm_day": 100,
        },
    )
    await _print(hass, type="kid_pack")  # far more than 100 mm
    with pytest.raises(ServiceValidationError, match="paper is all used up"):
        await _print(hass, type="joke")


async def test_admins_skip_option(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    hass_admin_user,
) -> None:
    await _setup(hass, config_entry, **{**LIMITS, "limit_admins_skip": True})
    from homeassistant.core import Context

    ctx = Context(user_id=hass_admin_user.id)
    for _ in range(2):
        await hass.services.async_call(
            DOMAIN, "print", {"type": "joke"}, blocking=True, context=ctx
        )
    # Admin prints don't count; without an admin user the limits apply.
    assert hass.states.get(LEFT).state == "4"
    await _print(hass, type="joke")
    with pytest.raises(ServiceValidationError):
        await _print(hass, type="joke")


async def test_preview_then_print_same_seed(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    preview = await hass.services.async_call(
        DOMAIN,
        "preview",
        {"type": "maze", "difficulty": "hard"},
        blocking=True,
        return_response=True,
    )
    assert preview["image"].startswith("data:image/png;base64,")
    png = base64.b64decode(preview["image"].split(",", 1)[1])
    with Image.open(io.BytesIO(png)) as img:
        assert img.width == 576
    assert printer.jobs == []  # nothing printed
    printed = await _print(hass, type="maze", difficulty="hard", seed=preview["seed"])
    assert printed["print_id"] == preview["print_id"]
    assert printed["length_mm"] == preview["length_mm"]


async def _jobs(printer: FakePrinter, count: int) -> None:
    for _ in range(100):
        if len(printer.jobs) >= count:
            return
        await asyncio.sleep(0.01)


@pytest.mark.parametrize("kind", ["maze", "word_search", "math", "joke", "fact"])
async def test_print_answers(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter, kind: str
) -> None:
    await _setup(hass, config_entry)
    printed = await _print(hass, type=kind, seed=7)
    answers = await hass.services.async_call(
        DOMAIN,
        "print_answers",
        {"print_id": f"#{printed['print_id'].lower()}"},
        blocking=True,
        return_response=True,
    )
    assert answers["print_id"] == printed["print_id"]
    assert answers["answers_for"] == kind
    # Newest puzzle when no ID is given (and via the Answers button).
    newest = await hass.services.async_call(
        DOMAIN, "print_answers", {}, blocking=True, return_response=True
    )
    assert newest["print_id"] == printed["print_id"]
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.tiny_press_answers"}, blocking=True
    )
    await _jobs(printer, 4)
    assert len(printer.jobs) == 4


async def test_answers_missing(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="no answer key"):
        await hass.services.async_call(DOMAIN, "print_answers", {}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.tiny_press_answers"}, blocking=True
        )
    await _print(hass, type="maze")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "print_answers", {"print_id": "ZZZZ"}, blocking=True
        )


async def test_limits_options_flow(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "kid_limits"}
    )
    assert result["step_id"] == "kid_limits"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], LIMITS
    )
    await hass.async_block_till_done()
    assert {k: config_entry.options[k] for k in LIMITS} == LIMITS
    assert config_entry.runtime_data.limiter.enabled


async def test_card_is_served_yaml_fallback(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    hass_client,
) -> None:
    # No storage-mode dashboards: fall back to the frontend's extra-module hook.
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    add_js.assert_called_once()
    assert add_js.call_args[0][1] == f"{CARD_URL}?v=0.5.1"
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert 'customElements.define("tiny-press-card"' in await response.text()


class FakeResources:
    """Stands in for Lovelace's storage-mode resource collection."""

    def __init__(self, items: list[dict[str, str]]) -> None:
        self.items = {i["id"]: dict(i) for i in items}

    async def async_get_info(self) -> dict[str, int]:
        return {"resources": len(self.items)}

    def async_items(self) -> list[dict[str, str]]:
        return list(self.items.values())

    async def async_create_item(self, data: dict[str, str]) -> dict[str, str]:
        item = {
            "id": f"id{len(self.items)}",
            "type": data["res_type"],
            "url": data["url"],
        }
        self.items[item["id"]] = item
        return item

    async def async_update_item(self, item_id: str, data: dict[str, str]) -> dict:
        self.items[item_id]["url"] = data["url"]
        return self.items[item_id]

    async def async_delete_item(self, item_id: str) -> None:
        del self.items[item_id]


@pytest.mark.parametrize(
    "existing",
    [
        [],
        [{"id": "old", "type": "module", "url": f"{CARD_URL}?v=0.3.0"}],
        [
            {"id": "a", "type": "module", "url": f"{CARD_URL}?v=0.3.0"},
            {"id": "b", "type": "module", "url": CARD_URL},
            {"id": "other", "type": "module", "url": "/local/other.js"},
        ],
    ],
)
async def test_card_added_to_dashboard_resources(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter, existing
) -> None:
    from types import SimpleNamespace

    from homeassistant.components.lovelace.const import LOVELACE_DATA

    resources = FakeResources(existing)
    hass.data[LOVELACE_DATA] = SimpleNamespace(
        resource_mode="storage", resources=resources
    )
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    mine = [i for i in resources.async_items() if i["url"].startswith(CARD_URL)]
    assert [i["url"] for i in mine] == [f"{CARD_URL}?v=0.5.1"]
    assert len(resources.items) == len(mine) + sum(
        1 for i in existing if not i["url"].startswith(CARD_URL)
    )
    # Removing the last printer removes the resource.
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    assert not [i for i in resources.async_items() if i["url"].startswith(CARD_URL)]


def test_card_version_matches_manifest() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/tiny_press/manifest.json").read_text()
    )
    card = (ROOT / "custom_components/tiny_press/card/tiny-press-card.js").read_text()
    assert re.search(r'CARD_VERSION = "([^"]+)"', card)[1] == manifest["version"]
