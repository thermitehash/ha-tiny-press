"""Persistent state: paper used, last print, puzzle history, settings."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, HISTORY_SIZE, RECENT_JOKES, STORAGE_VERSION

# Writes are batched for a moment; Home Assistant also writes any pending
# save when it shuts down, so counts survive restarts and upgrades.
SAVE_DELAY = 2


class _KeepingStore(Store[dict[str, Any]]):
    """A Store that keeps the saved data when its format version changes.

    Without this, a future STORAGE_VERSION bump would fail to load (and an
    upgrade would lose print counts, paper used and puzzle history).
    """

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict[str, Any]:
        return old_data


class TinyPressStore:
    """Small JSON store, one per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the store."""
        self._store: Store[dict[str, Any]] = _KeepingStore(
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
            "recent": {},
            "limits": {},
            "series": {},
        }

    async def async_load(self) -> None:
        """Load saved data, keeping defaults for missing keys."""
        saved = await self._store.async_load() or {}
        self.data = {**self._empty(), **saved}

    def _save(self) -> None:
        self._store.async_delay_save(lambda: self.data, SAVE_DELAY)

    def save(self) -> None:
        """Schedule a write (debounced)."""
        self._save()

    def find_answer(self, print_id: str | None) -> dict[str, Any] | None:
        """Return an answer key by print ID, or the newest one."""
        if not print_id:
            return self.history[0] if self.history else None
        wanted = print_id.strip().lstrip("#").upper()
        return next((h for h in self.history if h["print_id"] == wanted), None)

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

    def record_print(
        self, last: dict[str, Any], answers: list[dict[str, Any]] | tuple[()] = ()
    ) -> None:
        """Add paper used, set the last print and keep the answer keys.

        Each answer is ``{"print_id", "type", "answer"}``; a kid pack has three.
        """
        self.data["paper_used_mm"] = round(self.paper_used_mm + last["length_mm"], 1)
        self.data["last_print"] = last
        history = self.history
        for item in answers:
            entry = {**item, "printed_at": last["printed_at"]}
            history = [
                entry,
                *(h for h in history if h["print_id"] != item["print_id"]),
            ]
        self.data["history"] = history[:HISTORY_SIZE]
        self._save()

    def recent(self, kind: str) -> list[int]:
        """Indexes of recently printed bundled jokes or facts."""
        return list(self.data["recent"].get(kind, []))

    def remember(self, kind: str, index: int) -> None:
        """Note a bundled joke or fact so it isn't repeated soon."""
        items = [i for i in self.recent(kind) if i != index]
        self.data["recent"][kind] = [index, *items][:RECENT_JOKES]
        self._save()

    def series(self, profile_id: str) -> dict[str, Any] | None:
        """Return the serial story in progress for a kid, if any."""
        return self.data["series"].get(profile_id)

    def set_series(self, profile_id: str, value: dict[str, Any] | None) -> None:
        """Save (or clear) a kid's serial story."""
        if value is None:
            self.data["series"].pop(profile_id, None)
        else:
            self.data["series"][profile_id] = value
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
