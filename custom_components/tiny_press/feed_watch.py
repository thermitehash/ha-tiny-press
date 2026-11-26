"""Auto-print a slip when a feed adds an item (per feed, off by default).

Every minute, each feed with auto-print on whose check interval has passed is
fetched. The first check only remembers what's already there, so turning
auto-print on never prints a backlog. After that, each new item gets its own
slip, at most ``MAX_PER_CHECK`` per check, oldest first. Items older than
``MAX_AGE`` are never auto-printed. During a feed's quiet hours new items are
either skipped or kept (up to ``MAX_PER_CHECK``) and printed once quiet hours
end. Auto slips are not kid prints, so kid-mode limits never apply.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import jobs
from .coordinator import TinyPressCoordinator
from .fetch import FeedConfig, FetchError, async_fetch_feed, feeds_from_options
from .generators.feeds import MAX_ITEMS, Feed, FeedItem

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(minutes=1)
MAX_PER_CHECK = 3
MAX_AGE = timedelta(hours=12)
MAX_SEEN = 200
SETTING_FEED_WATCH = "feed_watch"


def item_key(item: FeedItem) -> str:
    """Identify an item by its link, else its title and date."""
    if item.link:
        return item.link
    stamp = item.published.isoformat() if item.published else ""
    return f"{item.title}|{stamp}"


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def in_quiet_hours(feed: FeedConfig, now: datetime) -> bool:
    """Say whether ``now`` (local) is inside the feed's quiet hours."""
    start, end = _parse_time(feed.quiet_start), _parse_time(feed.quiet_end)
    if start is None or end is None or start == end:
        return False
    current = now.time()
    if start < end:
        return start <= current < end
    return current >= start or current < end  # spans midnight


def _to_store(item: FeedItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "link": item.link,
        "published": item.published.isoformat() if item.published else None,
        "summary": item.summary,
    }


def _from_store(data: dict[str, Any]) -> FeedItem:
    published = data.get("published")
    return FeedItem(
        data.get("title") or "",
        data.get("link"),
        datetime.fromisoformat(published) if published else None,
        data.get("summary") or "",
    )


class FeedWatcher:
    """Checks auto-print feeds for one printer."""

    def __init__(self, hass: HomeAssistant, coordinator: TinyPressCoordinator) -> None:
        """Set up (call ``async_start`` to begin)."""
        self.hass = hass
        self.coordinator = coordinator
        self._unsub: CALLBACK_TYPE | None = None
        self._running = False

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Check every minute; returns the stop function."""
        self._unsub = async_track_time_interval(self.hass, self._tick, TICK)
        return self.async_stop

    @callback
    def async_stop(self) -> None:
        """Stop checking."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    def _state(self) -> dict[str, Any]:
        return dict(self.coordinator.store.get_setting(SETTING_FEED_WATCH) or {})

    def _save(self, state: dict[str, Any]) -> None:
        self.coordinator.store.set_setting(SETTING_FEED_WATCH, state)

    async def _tick(self, now: datetime | None = None) -> None:
        if self._running:  # a slow fetch is still going
            return
        self._running = True
        try:
            await self.async_check(dt_util.utcnow())
        finally:
            self._running = False

    async def async_check(self, now: datetime) -> int:
        """Check feeds that are due; returns how many slips printed."""
        feeds = [
            f
            for f in feeds_from_options(self.coordinator.config_entry.options)
            if f.auto_print
        ]
        state = self._state()
        # Forget feeds that are gone or switched off, so turning one back on
        # starts fresh (no backlog).
        active = {f.id for f in feeds}
        if any(key not in active for key in state):
            state = {key: value for key, value in state.items() if key in active}
            self._save(state)
        printed = 0
        for feed in feeds:
            entry = state.get(feed.id)
            last = entry.get("last") if entry else None
            if last and now - datetime.fromisoformat(last) < timedelta(
                minutes=feed.check_minutes
            ):
                continue
            printed += await self._check_feed(feed, entry, now, state)
        return printed

    async def _check_feed(
        self,
        feed: FeedConfig,
        entry: dict[str, Any] | None,
        now: datetime,
        state: dict[str, Any],
    ) -> int:
        try:
            parsed: Feed = await async_fetch_feed(self.hass, feed.url, MAX_ITEMS)
        except FetchError as err:
            _LOGGER.info("Auto-print: couldn't read %s: %s", feed.name, err)
            if entry is not None:
                state[feed.id] = {**entry, "last": now.isoformat()}
                self._save(state)
            return 0

        keys = [item_key(item) for item in parsed.items]
        if entry is None:  # first check: remember what's there, print nothing
            state[feed.id] = {"seen": keys, "last": now.isoformat(), "pending": []}
            self._save(state)
            return 0

        seen = set(entry.get("seen") or [])
        fresh = [
            item
            for item in parsed.items
            if item_key(item) not in seen
            and (item.published is None or now - item.published <= MAX_AGE)
        ]
        fresh.reverse()  # oldest first
        pending = [_from_store(p) for p in entry.get("pending") or []]
        quiet = in_quiet_hours(feed, dt_util.as_local(now))

        to_print: list[FeedItem] = []
        if quiet:
            if feed.quiet_mode == "morning":
                pending = (pending + fresh)[-MAX_PER_CHECK:]
        else:
            to_print = (pending + fresh)[-MAX_PER_CHECK:]
            pending = []

        printed = 0
        failed: list[FeedItem] = []
        for item in to_print:
            if failed:
                failed.append(item)
                continue
            job = jobs.feed_job(
                feed.name,
                Feed(parsed.title, parsed.link, (item,)),
                1,
                qr=feed.auto_qr,
                label="New item",
            )
            try:
                await self.coordinator.async_print(job)
            except HomeAssistantError as err:
                _LOGGER.info("Auto-print: %s didn't print: %s", feed.name, err)
                failed.append(item)
            else:
                printed += 1

        # Unprinted items (printer off) wait for the next check, capped.
        pending = (pending + failed)[-MAX_PER_CHECK:]
        state[feed.id] = {
            "seen": (keys + [k for k in entry.get("seen") or [] if k not in keys])[
                :MAX_SEEN
            ],
            "last": now.isoformat(),
            "pending": [_to_store(item) for item in pending],
        }
        self._save(state)
        return printed
