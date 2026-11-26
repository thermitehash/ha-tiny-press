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
