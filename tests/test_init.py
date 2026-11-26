"""Setup, entities, actions, events, polling and repairs."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.tiny_press.const import DOMAIN, EVENT_PRINTED, Difficulty
from custom_components.tiny_press.printer.escpos import INIT
from custom_components.tiny_press.services import normalize_difficulty

from .fake_printer import FakePrinter

ONLINE = "binary_sensor.tiny_press_online"
PAPER = "sensor.tiny_press_paper"
USED = "sensor.tiny_press_paper_used"
LAST = "sensor.tiny_press_last_print"


async def _wait_jobs(printer: FakePrinter, count: int) -> None:
    for _ in range(100):
        if len(printer.jobs) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} jobs, got {len(printer.jobs)}")


async def test_setup_and_entities(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    assert loaded_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ONLINE).state == "on"
    assert hass.states.get(PAPER).state == "ok"
    assert float(hass.states.get(USED).state) == 0
    assert hass.states.get(LAST).state == "unknown"
    assert hass.states.get("button.tiny_press_maze")
    assert hass.states.get("button.tiny_press_test_page")
    assert hass.states.get("select.tiny_press_maze_difficulty").state == "easy"


async def test_print_maze_action(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    events = async_capture_events(hass, EVENT_PRINTED)
    response = await hass.services.async_call(
        DOMAIN,
        "print",
        {"type": "maze", "difficulty": "Tricky!", "seed": 42, "profile": "Kid"},
        blocking=True,
        return_response=True,
    )
    assert response["type"] == "maze"
    assert len(response["print_id"]) == 4
    assert response["length_mm"] > 100
    assert response["truncated"] is False
    await _wait_jobs(printer, 1)
    job = printer.jobs[0]
    assert job.startswith(INIT + b"\x1dv0\x00")
    assert job.endswith(b"\x1dVB\x03")
    await hass.async_block_till_done()
    assert events[-1].data == {
        "type": "maze",
        "print_id": response["print_id"],
        "profile": "Kid",
        "success": True,
    }
    last = hass.states.get(LAST)
    assert last.state == "maze"
    assert last.attributes["difficulty"] == "hard"
    assert float(hass.states.get(USED).state) == response["length_mm"]
    history = loaded_entry.runtime_data.store.history
    assert history[0]["print_id"] == response["print_id"]
    assert history[0]["answer"]["seed"] == 42

    # Same seed, same puzzle and ID.
    again = await hass.services.async_call(
        DOMAIN,
        "print",
        {"type": "maze", "difficulty": "hard", "seed": 42},
        blocking=True,
        return_response=True,
    )
    assert again["print_id"] == response["print_id"]
    assert len(loaded_entry.runtime_data.store.history) == 1


async def test_buttons_and_select(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.tiny_press_maze_difficulty", "option": "medium"},
        blocking=True,
    )
    assert hass.states.get("select.tiny_press_maze_difficulty").state == "medium"
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.tiny_press_maze"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.tiny_press_test_page"}, blocking=True
    )
    await _wait_jobs(printer, 2)
    assert (
        loaded_entry.runtime_data.store.history[0]["answer"]["difficulty"] == "medium"
    )
    # The test page ends with a native QR code before the cut.
    test_page = next(j for j in printer.jobs if b"\x1d(k" in j)
    assert b"github.com/thermitehash/ha-tiny-press" in test_page
    assert hass.states.get(LAST).state == "test_page"


async def test_print_text(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "print_text",
        {"text": "Hello\nworld", "title": "Hi", "size": "large"},
        blocking=True,
        return_response=True,
    )
    assert response["type"] == "text"
    await _wait_jobs(printer, 1)


async def test_max_length_trims(
    hass: HomeAssistant, printer: FakePrinter, config_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        config_entry, options={"max_length_mm": 100, "poll_interval": 60}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    response = await hass.services.async_call(
        DOMAIN,
        "print_text",
        {"text": "line\n" * 500},
        blocking=True,
        return_response=True,
    )
    assert response["truncated"] is True
    assert response["length_mm"] <= 100


async def test_print_image(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    printer: FakePrinter,
    tmp_path: Path,
) -> None:
    www = Path(hass.config.path("www"))
    www.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 200), (120, 120, 120)).save(www / "pic.png")
    hass.config.allowlist_external_dirs = {str(www)}
    response = await hass.services.async_call(
        DOMAIN,
        "print_image",
        {"path": str(www / "pic.png")},
        blocking=True,
        return_response=True,
    )
    assert response["type"] == "image"
    await _wait_jobs(printer, 1)

    outside = tmp_path / "secret.png"
    Image.new("RGB", (10, 10)).save(outside)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "print_image", {"path": str(outside)}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "print_image", {"path": str(www / "missing.png")}, blocking=True
        )
    (www / "bad.png").write_text("not an image")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "print_image", {"path": str(www / "bad.png")}, blocking=True
        )


async def test_print_failure_fires_event(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    events = async_capture_events(hass, EVENT_PRINTED)
    await printer.stop()
    with pytest.raises(HomeAssistantError, match="didn't take the job"):
        await hass.services.async_call(DOMAIN, "print", {"type": "maze"}, blocking=True)
    await hass.async_block_till_done()
    assert events[-1].data["success"] is False


async def test_no_entry_errors(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "print", {"type": "maze", "config_entry_id": "nope"}, blocking=True
        )
    await hass.config_entries.async_unload(loaded_entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "print", {"type": "maze"}, blocking=True)


async def test_two_printers_need_choice(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    other = MockConfigEntry(
        domain=DOMAIN, unique_id="x", data={**loaded_entry.data, "host": "127.0.0.1"}
    )
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "print", {"type": "maze"}, blocking=True)
    await hass.services.async_call(
        DOMAIN,
        "print",
        {"type": "maze", "config_entry_id": other.entry_id},
        blocking=True,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, Difficulty.MEDIUM),
        ("easy", Difficulty.EASY),
        ("Medium", Difficulty.MEDIUM),
        ("hard", Difficulty.HARD),
        ("harder", Difficulty.HARD),
        ("tricky", Difficulty.HARD),
        ("a little harder", Difficulty.HARD),
        ("super hard", Difficulty.HARD),
        ("simple", Difficulty.EASY),
        ("banana", Difficulty.MEDIUM),
    ],
)
def test_normalize_difficulty(text: str | None, expected: Difficulty) -> None:
    assert normalize_difficulty(text, Difficulty.MEDIUM) is expected


@pytest.mark.parametrize(
    ("status", "paper", "online"),
    [
        ({4: 0x1E}, "near_end", "on"),
        ({4: 0x72, 1: 0x1E}, "out", "off"),
        ({2: 0x16, 1: 0x1E}, "cover_open", "off"),
        ({1: 0x1E}, "offline", "off"),
    ],
)
async def test_status_states(
    hass: HomeAssistant,
    printer: FakePrinter,
    config_entry: MockConfigEntry,
    status: dict[int, int],
    paper: str,
    online: str,
) -> None:
    printer.status.update(status)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(PAPER).state == paper
    assert hass.states.get(ONLINE).state == online


async def test_offline_repair_after_a_day(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    issues = ir.async_get(hass)
    await printer.stop()
    coordinator = loaded_entry.runtime_data
    await coordinator.async_refresh()
    assert hass.states.get(PAPER).state == "offline"
    assert hass.states.get(ONLINE).state == "off"
    assert not issues.async_get_issue(
        DOMAIN, f"printer_offline_{loaded_entry.entry_id}"
    )

    freezer.tick(timedelta(hours=25))
    await coordinator.async_refresh()
    assert issues.async_get_issue(DOMAIN, f"printer_offline_{loaded_entry.entry_id}")

    await printer.start()  # back on a new port: point the transport at it
    coordinator.queue.transport.port = printer.port
    await coordinator.async_refresh()
    assert hass.states.get(PAPER).state == "ok"
    assert not issues.async_get_issue(
        DOMAIN, f"printer_offline_{loaded_entry.entry_id}"
    )


async def test_poll_interval_and_busy_skip(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    coordinator = loaded_entry.runtime_data
    assert coordinator.update_interval == timedelta(seconds=60)
    before = printer.connections
    with patch.object(coordinator.queue._lock, "locked", return_value=True):
        await coordinator.async_refresh()
    assert printer.connections == before  # no status query mid-job
    assert hass.states.get(ONLINE).state == "on"
    await coordinator.async_refresh()
    assert printer.connections == before + 1


async def test_diagnostics_redacts_host(
    hass: HomeAssistant, hass_client, loaded_entry: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        loaded_entry,
        options={
            "profiles": [
                {"id": "r", "kind": "kid", "name": "Rosie", "interests": "cats"}
            ]
        },
    )
    await hass.async_block_till_done()
    diag = await get_diagnostics_for_config_entry(hass, hass_client, loaded_entry)
    assert diag["entry"]["data"]["host"] == "**REDACTED**"
    profile = diag["entry"]["options"]["profiles"][0]
    assert profile["name"] == "**REDACTED**" and profile["interests"] == "**REDACTED**"
    assert "Rosie" not in str(diag)
    assert diag["state"]["paper"] == "ok"
    assert diag["width_dots"] == 576


async def test_unload_and_remove(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.state is ConfigEntryState.NOT_LOADED
    assert await hass.config_entries.async_remove(loaded_entry.entry_id)
