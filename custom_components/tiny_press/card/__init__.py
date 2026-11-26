"""Serve the Tiny Press dashboard card and register it with the dashboards.

In storage mode (the default), the card is added to the dashboard
resources, the same way other card-shipping integrations do it, so it shows
up in the card picker. A version query keeps browsers from using a stale
copy after an update. YAML-mode dashboards get the card through the
frontend's extra-module hook instead (and the README explains how to add it
as a resource).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "tiny-press-card.js"
CARD_URL = "/tiny_press/tiny-press-card.js"


def _resources(hass: HomeAssistant) -> Any | None:
    """Return the storage-mode resource collection, if dashboards use storage."""
    try:
        from homeassistant.components.lovelace.const import (  # noqa: PLC0415
            LOVELACE_DATA,
        )
    except ImportError:  # pragma: no cover - lovelace always ships with HA
        return None
    data = hass.data.get(LOVELACE_DATA)
    if data is None or getattr(data, "resource_mode", None) != "storage":
        return None
    return data.resources


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card's JavaScript and make dashboards load it."""
    if hass.http is None:
        _LOGGER.debug("HTTP not loaded; dashboard card not registered")
        return
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    version = (await async_get_integration(hass, DOMAIN)).version
    url = f"{CARD_URL}?v={version}"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )

    resources = _resources(hass)
    if resources is not None:
        await resources.async_get_info()  # loads the collection from storage
        mine = [
            item
            for item in resources.async_items()
            if str(item.get("url", "")).split("?")[0] == CARD_URL
        ]
        if not mine:
            await resources.async_create_item({"res_type": "module", "url": url})
            _LOGGER.info("Added the Tiny Press card to the dashboard resources")
        else:
            first, *extra = mine
            if first.get("url") != url:
                await resources.async_update_item(
                    first["id"], {"res_type": "module", "url": url}
                )
            for item in extra:  # tidy up duplicates
                await resources.async_delete_item(item["id"])
        return

    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url  # noqa: PLC0415

        add_extra_js_url(hass, url)


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Remove the dashboard resource (when the last printer is removed)."""
    resources = _resources(hass)
    if resources is None:
        return
    await resources.async_get_info()
    for item in list(resources.async_items()):
        if str(item.get("url", "")).split("?")[0] == CARD_URL:
            await resources.async_delete_item(item["id"])
