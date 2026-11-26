"""Serve the Tiny Press dashboard card and load it on every dashboard."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "tiny-press-card.js"
CARD_URL = "/tiny_press/tiny-press-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card's JavaScript and add it to the frontend.

    ``add_extra_js_url`` loads the module on every page, so the card works in
    any dashboard without adding a Lovelace resource by hand.
    """
    if hass.http is None or "frontend" not in hass.config.components:
        _LOGGER.debug("Frontend not loaded; dashboard card not registered")
        return
    # Imported here: these components are optional (after_dependencies).
    from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")
