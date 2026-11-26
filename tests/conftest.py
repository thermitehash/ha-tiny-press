"""Fixtures for Tiny Press tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tiny_press.const import CONF_PAPER_WIDTH, DOMAIN, PAPER_80MM

from .fake_printer import FakePrinter


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture(autouse=True)
def fast_retry() -> None:
    """No real sleep before the single reconnect retry."""
    with patch("custom_components.tiny_press.printer.queue.RETRY_DELAY", 0):
        yield


@pytest.fixture
async def printer(socket_enabled: None) -> AsyncGenerator[FakePrinter]:
    """A running fake printer."""
    fake = FakePrinter()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
def config_entry(hass: HomeAssistant, printer: FakePrinter) -> MockConfigEntry:
    """A config entry pointing at the fake printer."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Tiny Press (127.0.0.1)",
        unique_id=f"127.0.0.1:{printer.port}",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: printer.port,
            CONF_PAPER_WIDTH: PAPER_80MM,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
