"""Config and options flows for Tiny Press."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import voluptuous as vol

from .const import (
    CONF_MAX_LENGTH_MM,
    CONF_PAPER_WIDTH,
    CONF_POLL_INTERVAL,
    CONF_PRINT_TEST_PAGE,
    DEFAULT_MAX_LENGTH_MM,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    PAPER_58MM,
    PAPER_80MM,
    PAPER_DOTS,
)
from .coordinator import TinyPressConfigEntry
from .printer import escpos
from .printer.transport import PrinterConnectError, PrinterError, PrinterTransport
from .services import test_page_print

_LOGGER = logging.getLogger(__name__)

PAPER_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[PAPER_80MM, PAPER_58MM],
        translation_key=CONF_PAPER_WIDTH,
        mode=SelectSelectorMode.LIST,
    )
)


async def _probe(host: str, port: int) -> str | None:
    """Return an error key, or None when the printer answers ESC/POS status."""
    try:
        await PrinterTransport(host, port).read_status()
    except PrinterConnectError:
        return "cannot_connect"
    except PrinterError:
        return "no_status"
    return None


class TinyPressConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a printer by address or from DHCP discovery."""

    VERSION = 1

    def __init__(self) -> None:
        """Start empty."""
        self._host: str | None = None
        self._port: int = DEFAULT_PORT

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host and port, then test-connect and read status."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            if (error := await _probe(host, port)) is None:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                self._host, self._port = host, port
                return await self.async_step_paper()
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Offer a discovered Epson device if it speaks ESC/POS."""
        host = discovery_info.ip
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._async_abort_entries_match({CONF_HOST: host})
        # Epson's MAC ranges also cover inkjets and projectors: only offer
        # devices that answer receipt-printer status on port 9100.
        if await _probe(host, DEFAULT_PORT) is not None:
            return self.async_abort(reason="not_receipt_printer")
        self._host, self._port = host, DEFAULT_PORT
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered printer."""
        if user_input is not None:
            return await self.async_step_paper()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"host": self._host or ""},
        )

    async def async_step_paper(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the paper width and optionally print a test page."""
        assert self._host is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            paper = user_input[CONF_PAPER_WIDTH]
            if user_input.get(CONF_PRINT_TEST_PAGE) and not (
                await self._print_test_page(paper)
            ):
                errors["base"] = "test_page_failed"
            if not errors:
                return self.async_create_entry(
                    title=f"Tiny Press ({self._host})",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_PAPER_WIDTH: paper,
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_PAPER_WIDTH, default=PAPER_80MM): PAPER_SELECTOR,
                vol.Optional(CONF_PRINT_TEST_PAGE, default=True): bool,
            }
        )
        return self.async_show_form(step_id="paper", data_schema=schema, errors=errors)

    async def _print_test_page(self, paper: str) -> bool:
        """Print the test page straight from the flow (before the entry exists)."""
        assert self._host is not None
        job = test_page_print(
            paper,
            {
                "Printer": f"{self._host}:{self._port}",
                "Paper": f"{paper} mm, {PAPER_DOTS[paper]} dots",
            },
        )

        def render() -> bytes:
            image, _ = job.build(PAPER_DOTS[paper]).render()
            return escpos.INIT + escpos.raster(image) + job.extra + escpos.cut()

        data = await self.hass.async_add_executor_job(render)
        try:
            await PrinterTransport(self._host, self._port).send(data)
        except PrinterError as err:
            _LOGGER.warning("Test page failed: %s", err)
            return False
        return True

    @staticmethod
    @callback
    def async_get_options_flow(entry: TinyPressConfigEntry) -> TinyPressOptionsFlow:
        """Return the options flow."""
        return TinyPressOptionsFlow()


class TinyPressOptionsFlow(OptionsFlowWithReload):
    """Longest print and status poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_MAX_LENGTH_MM: int(user_input[CONF_MAX_LENGTH_MM]),
                    CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL]),
                }
            )
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAX_LENGTH_MM,
                    default=options.get(CONF_MAX_LENGTH_MM, DEFAULT_MAX_LENGTH_MM),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=100,
                        max=3000,
                        step=10,
                        unit_of_measurement="mm",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=5,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
