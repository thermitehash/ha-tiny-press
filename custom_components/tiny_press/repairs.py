"""Repairs: tell the household when the printer has been offline for a day."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_OFFLINE


def offline_issue_id(entry_id: str) -> str:
    """Issue ID for one printer."""
    return f"{ISSUE_OFFLINE}_{entry_id}"


@callback
def async_raise_offline_issue(
    hass: HomeAssistant, entry_id: str, name: str, since: datetime
) -> None:
    """Create (or refresh) the not-fixable offline issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        offline_issue_id(entry_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_OFFLINE,
        translation_placeholders={
            "name": name,
            "since": since.strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


@callback
def async_clear_offline_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the issue once the printer answers again."""
    ir.async_delete_issue(hass, DOMAIN, offline_issue_id(entry_id))
