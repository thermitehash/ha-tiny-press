"""Persistent state: paper used, last print, puzzle history, settings."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, HISTORY_SIZE, STORAGE_VERSION

SAVE_DELAY = 10


class TinyPressStore:
    """Small JSON store, one per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the store."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.data: dict[str, Any] = self._empty()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "paper_used_mm": 0.0,
            "last_print": None,
            "history": [],
            "offline_since": None,
            "settings": {},
        }

    async def async_load(self) -> None:
        """Load saved data, keeping defaults for missing keys."""
        saved = await self._store.async_load() or {}
        self.data = {**self._empty(), **saved}

    def _save(self) -> None:
        self._store.async_delay_save(lambda: self.data, SAVE_DELAY)

    async def async_flush(self) -> None:
        """Write now (used on unload)."""
        await self._store.async_save(self.data)

    async def async_remove(self) -> None:
        """Delete the file (entry removed)."""
        await self._store.async_remove()

    @property
    def paper_used_mm(self) -> float:
        """Total millimetres of paper printed."""
        return float(self.data["paper_used_mm"])

    @property
    def last_print(self) -> dict[str, Any] | None:
        """The most recent print, if any."""
        return self.data["last_print"]

    @property
    def history(self) -> list[dict[str, Any]]:
        """Recent puzzles with answer data, newest first."""
        return self.data["history"]

    def record_print(self, last: dict[str, Any], answer: dict[str, Any] | None) -> None:
        """Add paper used, set the last print and keep the answer key."""
        self.data["paper_used_mm"] = round(self.paper_used_mm + last["length_mm"], 1)
        self.data["last_print"] = last
        if answer is not None:
            entry = {
                "print_id": last["print_id"],
                "type": last["type"],
                "printed_at": last["printed_at"],
                "answer": answer,
            }
            rest = [h for h in self.history if h["print_id"] != last["print_id"]]
            self.data["history"] = [entry, *rest][:HISTORY_SIZE]
        self._save()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Read a select's value."""
        return self.data["settings"].get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Remember a select's value."""
        self.data["settings"][key] = value
        self._save()

    @property
    def offline_since(self) -> str | None:
        """ISO timestamp the printer went offline, or None."""
        return self.data["offline_since"]

    def set_offline_since(self, value: str | None) -> None:
        """Update the offline marker."""
        if self.data["offline_since"] != value:
            self.data["offline_since"] = value
            self._save()
