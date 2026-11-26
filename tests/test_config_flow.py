"""Config and options flows."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.const import DOMAIN

from .fake_printer import FakePrinter


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_with_test_page(
    hass: HomeAssistant, printer: FakePrinter
) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: " 127.0.0.1 ", CONF_PORT: printer.port}
    )
    assert result["step_id"] == "paper"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"paper_width": "58", "print_test_page": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "host": "127.0.0.1",
        "port": printer.port,
        "paper_width": "58",
    }
    for _ in range(100):
        if printer.jobs:
            break
        await asyncio.sleep(0.01)
    # 58 mm raster: 420 dots = 53 bytes per row.
    assert printer.jobs[0][2:8] == b"\x1dv0\x00\x35\x00"


async def test_user_flow_errors(hass: HomeAssistant, printer: FakePrinter) -> None:
    result = await _start(hass)
    printer.answer_status = False
    with patch("custom_components.tiny_press.printer.transport.STATUS_TIMEOUT", 0.2):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: printer.port}
        )
    assert result["errors"] == {"base": "no_status"}

    port = printer.port
    await printer.stop()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_test_page_failure_shows_error(
    hass: HomeAssistant, printer: FakePrinter
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: printer.port}
    )
    await printer.stop()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"paper_width": "80", "print_test_page": True}
    )
    assert result["errors"] == {"base": "test_page_failed"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"paper_width": "80", "print_test_page": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: printer.port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def _dhcp(ip: str = "127.0.0.1") -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="epson-tm", macaddress="0026ab123456")


async def test_dhcp_discovery(hass: HomeAssistant, printer: FakePrinter) -> None:
    with patch("custom_components.tiny_press.config_flow.DEFAULT_PORT", printer.port):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp()
        )
        assert result["step_id"] == "discovery_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "paper"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"paper_width": "80", "print_test_page": False}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "00:26:ab:12:34:56"


async def test_dhcp_ignores_non_receipt_printer(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    fake = FakePrinter()
    await fake.start()
    port = fake.port
    await fake.stop()
    with patch("custom_components.tiny_press.config_flow.DEFAULT_PORT", port):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp()
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_receipt_printer"


async def test_dhcp_updates_moved_printer(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="00:26:ab:12:34:56",
        data={CONF_HOST: "10.0.0.5", CONF_PORT: 9100, "paper_width": "80"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp("10.0.0.9")
    )
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "10.0.0.9"


async def test_options_settings(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["settings", "kid_limits", "add_kid", "add_adult"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "max_length_mm": 450,
            "poll_interval": 120,
            "ai_task_entity": "ai_task.claude",
            "ai_jokes": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert loaded_entry.options == {
        "max_length_mm": 450,
        "poll_interval": 120,
        "ai_task_entity": "ai_task.claude",
        "ai_jokes": True,
        "weather_entity": None,
    }
    coordinator = loaded_entry.runtime_data
    assert coordinator.max_length_mm == 450
    assert coordinator.update_interval.total_seconds() == 120
    assert coordinator.ai_task_entity == "ai_task.claude"
    assert coordinator.use_ai_jokes


async def _menu(hass: HomeAssistant, entry: MockConfigEntry, step: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_profiles_add_edit_remove(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await _menu(hass, loaded_entry, "add_kid")
    assert result["step_id"] == "add_kid"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "name": " Rosie ",
            "grade": "2",
            "interests": "dinosaurs, space",
            "stretch": False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert loaded_entry.options["profiles"] == [
        {
            "id": "rosie",
            "kind": "kid",
            "name": "Rosie",
            "grade": "2",
            "interests": "dinosaurs, space",
            "stretch": False,
            "spelling_words": "",
            "spelling_todo": "",
            "difficulty": "medium",
        }
    ]
    assert hass.states.get("select.tiny_press_kid_profile").state == "Rosie"

    # Duplicate names are refused.
    result = await _menu(hass, loaded_entry, "add_kid")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "rosie", "grade": "3", "stretch": False}
    )
    assert result["errors"] == {"name": "name_exists"}

    result = await _menu(hass, loaded_entry, "add_adult")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Sam", "difficulty": "hard"}
    )
    await hass.async_block_till_done()
    assert [p["name"] for p in loaded_entry.options["profiles"]] == ["Rosie", "Sam"]

    result = await _menu(hass, loaded_entry, "edit_profile")
    assert result["step_id"] == "edit_profile"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"profile": "rosie"}
    )
    assert result["step_id"] == "edit_kid"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": "Rosie", "grade": "3", "interests": "horses", "stretch": True},
    )
    await hass.async_block_till_done()
    rosie = loaded_entry.options["profiles"][0]
    assert (rosie["grade"], rosie["interests"], rosie["stretch"]) == (
        "3",
        "horses",
        True,
    )

    result = await _menu(hass, loaded_entry, "edit_profile")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"profile": "sam"}
    )
    assert result["step_id"] == "edit_adult"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Rosie", "difficulty": "easy"}
    )
    assert result["errors"] == {"name": "name_exists"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Sam", "difficulty": "easy"}
    )
    await hass.async_block_till_done()
    assert loaded_entry.options["profiles"][1]["difficulty"] == "easy"

    result = await _menu(hass, loaded_entry, "remove_profile")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"profiles": ["sam"]}
    )
    await hass.async_block_till_done()
    assert [p["id"] for p in loaded_entry.options["profiles"]] == ["rosie"]


async def test_add_profile_needs_name(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await _menu(hass, loaded_entry, "add_adult")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "  ", "difficulty": "easy"}
    )
    assert result["errors"] == {"name": "name_required"}
