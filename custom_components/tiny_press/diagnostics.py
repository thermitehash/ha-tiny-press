"""Diagnostics (the printer's address is redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import TinyPressConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TinyPressConfigEntry
) -> dict[str, Any]:
    """Return entry settings, the last status and print counters."""
    coordinator = entry.runtime_data
    data = coordinator.data
    store = coordinator.store
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "width_dots": coordinator.width,
        "state": {
            "online": data.online if data else None,
            "paper": data.paper.value if data else None,
            "status": asdict(data.status) if data and data.status else None,
        },
        "queue_busy": coordinator.queue.busy,
        "paper_used_mm": store.paper_used_mm,
        "last_print": store.last_print,
        "history": [
            {"print_id": h["print_id"], "type": h["type"]} for h in store.history
        ],
        "offline_since": store.offline_since,
        "settings": store.data["settings"],
    }
