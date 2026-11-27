"""Per-person card rules and per-kid limits."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser

from custom_components.tiny_press.const import DOMAIN

from .fake_printer import FakePrinter

LIMITS = {"limits_enabled": True, "limit_cooldown_s": 3600, "limit_admins_skip": False}
LEFT = "sensor.tiny_press_kid_prints_left_today"


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, rosie_user: str, sam_user: str
) -> None:
    hass.config_entries.async_update_entry(
        entry,
        options={
            **LIMITS,
            "profiles": [
                {
                    "id": "rosie",
                    "kind": "kid",
                    "name": "Rosie",
                    "grade": "2",
                    "ha_user": rosie_user,
                },
                {"id": "max", "kind": "kid", "name": "Max", "grade": "4"},
                {"id": "sam", "kind": "adult", "name": "Sam", "ha_user": sam_user},
            ],
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _print(
    hass: HomeAssistant, user: str | None = None, **data: Any
) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN,
        "print",
        data,
        blocking=True,
        return_response=True,
        context=Context(user_id=user),
    )


async def test_people_and_per_kid_limits(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
    hass_admin_user: MockUser,
) -> None:
    freezer.move_to("2026-11-26 15:00:00+00:00")
    rosie = MockUser(name="Rosie").add_to_hass(hass)
    sam = MockUser(name="Sam").add_to_hass(hass)
    await _setup(hass, config_entry, rosie.id, sam.id)

    # Rosie's account always prints as Rosie, even when asking for Max or
    # trying to skip limits.
    res = await _print(hass, rosie.id, type="joke", profile="max", ignore_limits=True)
    assert res["profile"] == "Rosie"
    with pytest.raises(ServiceValidationError, match="Just a moment"):
        await _print(hass, rosie.id, type="joke")

    # Limits are per kid: Max isn't blocked by Rosie's cooldown.
    assert (await _print(hass, None, type="joke", profile="max"))["profile"] == "Max"
    with pytest.raises(ServiceValidationError, match="Just a moment"):
        await _print(hass, None, type="joke", profile="max")

    # Admins and linked adults print as anyone and never count.
    for user in (hass_admin_user.id, sam.id):
        res = await _print(hass, user, type="maze", profile="rosie")
        assert res["profile"] == "Rosie"
    assert (await _print(hass, sam.id, type="crossword"))["profile"] == "Sam"

    state = hass.states.get(LEFT)
    kids = state.attributes["kids"]
    assert kids["rosie"]["blocked_reason"] == "cooldown"
    assert kids["rosie"]["prints_left"] == 9 and kids["max"]["prints_left"] == 9
    assert kids["rosie"]["blocked_since"].startswith("2026-11-26T15:00:00")
    profiles = hass.states.get("select.tiny_press_kid_profile").attributes["profiles"]
    assert {p["id"]: p["ha_user"] for p in profiles} == {
        "rosie": rosie.id,
        "max": None,
        "sam": sam.id,
    }

    # Morning slip from a kid's account: once a day for that kid only.
    await hass.services.async_call(
        DOMAIN,
        "print_morning_slip",
        {},
        blocking=True,
        context=Context(user_id=rosie.id),
    )
    with pytest.raises(ServiceValidationError, match="already been printed"):
        await hass.services.async_call(
            DOMAIN,
            "print_morning_slip",
            {},
            blocking=True,
            context=Context(user_id=rosie.id),
        )
    await hass.services.async_call(
        DOMAIN, "print_morning_slip", {"kid_mode": True}, blocking=True
    )  # the shared kid-mode slip is separate


async def test_link_a_user_in_options(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    rosie = MockUser(name="Rosie").add_to_hass(hass)
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_kid"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": "Rosie", "grade": "2", "stretch": False, "ha_user": rosie.id},
    )
    await hass.async_block_till_done()
    assert loaded_entry.options["profiles"][0]["ha_user"] == rosie.id


async def test_morning_slip_greys_out_for_everyone(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-11-26 07:00:00+00:00")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    button = "button.tiny_press_morning_slip"
    assert hass.states.get(button).attributes["printed_today"] is False
    await hass.services.async_call(DOMAIN, "print_morning_slip", {}, blocking=True)
    await hass.async_block_till_done()
    attrs = hass.states.get(button).attributes
    assert attrs["printed_today"] is True
    assert attrs["last_printed"].startswith("2026-11-26T07:00")
    freezer.move_to("2026-11-27 07:00:00+00:00")  # a new day
    config_entry.runtime_data.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(button).attributes["printed_today"] is False


async def test_daily_limit_per_kid(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-11-26 15:00:00+00:00")
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "limits_enabled": True,
            "limit_cooldown_s": 0,
            "limit_per_hour": 0,
            "limit_per_day": 5,
            "profiles": [
                {"id": "rosie", "kind": "kid", "name": "Rosie", "daily_limit": 2},
                {"id": "max", "kind": "kid", "name": "Max"},
            ],
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    kids = hass.states.get(LEFT).attributes["kids"]
    assert kids["rosie"]["per_day"] == 2 and kids["rosie"]["prints_left"] == 2
    assert kids["max"]["per_day"] == 5 and kids["max"]["prints_left"] == 5

    for _ in range(2):
        await _print(hass, type="joke", profile="rosie")
    with pytest.raises(ServiceValidationError, match="enough printing for today"):
        await _print(hass, type="joke", profile="rosie")
    # Max follows the household setting.
    for _ in range(5):
        await _print(hass, type="joke", profile="max")
    with pytest.raises(ServiceValidationError, match="enough printing for today"):
        await _print(hass, type="joke", profile="max")


async def test_set_daily_limit_in_options(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    flow = hass.config_entries.options
    result = await flow.async_init(loaded_entry.entry_id)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "add_kid"})
    result = await flow.async_configure(
        result["flow_id"],
        {"name": "Rosie", "grade": "2", "stretch": False, "daily_limit": 3},
    )
    await hass.async_block_till_done()
    assert loaded_entry.options["profiles"][0]["daily_limit"] == 3
    # Cleared: back to the household setting.
    result = await flow.async_init(loaded_entry.entry_id)
    result = await flow.async_configure(
        result["flow_id"], {"next_step_id": "edit_profile"}
    )
    result = await flow.async_configure(result["flow_id"], {"profile": "rosie"})
    assert result["step_id"] == "edit_kid"
    result = await flow.async_configure(
        result["flow_id"], {"name": "Rosie", "grade": "2", "stretch": False}
    )
    await hass.async_block_till_done()
    assert loaded_entry.options["profiles"][0]["daily_limit"] == 0


async def test_print_counts_survive_restarts(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from custom_components.tiny_press.store import TinyPressStore

    freezer.move_to("2026-11-26 15:00:00+00:00")
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "limits_enabled": True,
            "limit_cooldown_s": 0,
            "limit_per_hour": 0,
            "limit_per_day": 5,
            "profiles": [{"id": "rosie", "kind": "kid", "name": "Rosie"}],
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    for _ in range(2):
        await _print(hass, type="joke", profile="rosie")

    # Written within seconds, so even an unclean stop keeps the count.
    freezer.tick(3)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    key = f"tiny_press.{config_entry.entry_id}"
    saved = hass_storage[key]["data"]["limits"]["kids"]["rosie"]["prints"]
    assert len(saved) == 2

    # A reload (as after an options change or an upgrade) keeps it.
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(LEFT).attributes["kids"]["rosie"]["prints_left"] == 3

    # A future storage format change keeps the data too.
    hass_storage[key]["version"] = 0
    store = TinyPressStore(hass, config_entry.entry_id)
    await store.async_load()
    assert len(store.data["limits"]["kids"]["rosie"]["prints"]) == 2


async def test_old_shared_counts_are_kept_today(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    from homeassistant.util import dt as dt_util

    from custom_components.tiny_press.limits import RateLimiter

    store = loaded_entry.runtime_data.store
    today = dt_util.now().date().isoformat()
    stamp = dt_util.utcnow().isoformat()
    store.data["limits"] = {"day": today, "prints": [stamp], "paper_mm": 12.0}
    limiter = RateLimiter(store, {"limits_enabled": True})
    limiter.status("")
    assert store.data["limits"]["kids"][""] == {"prints": [stamp], "paper_mm": 12.0}
