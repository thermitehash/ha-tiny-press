"""Download feeds and Wikiquote's quote of the day, on demand only.

Nothing here polls: a feed is fetched when someone prints it (or the morning
slip needs it). Downloads use Home Assistant's shared HTTP session with a
timeout and a size cap.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .generators.feeds import (
    DEFAULT_ITEMS,
    MAX_ITEMS,
    WIKIQUOTE_API_URL,
    WIKIQUOTE_URL,
    Feed,
    FeedError,
    parse_feed,
    wikiquote_api_html,
    wikiquote_quote,
)
from .store import TinyPressStore

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_BYTES = 2 * 1024 * 1024
# Wikimedia asks automated clients to identify themselves.
USER_AGENT = "TinyPress/0.9 (Home Assistant integration; +https://github.com/thermitehash/ha-tiny-press)"
SETTING_LIVE_QUOTE_CACHE = "live_quote_cache"


class FetchError(Exception):
    """The download failed or wasn't a feed."""


DEFAULT_CHECK_MINUTES = 15
DEFAULT_QUIET_START = "21:00"
DEFAULT_QUIET_END = "07:00"
QUIET_MODES = ("skip", "morning")


@dataclass(frozen=True, slots=True)
class FeedConfig:
    """One feed from Configure → Feeds."""

    id: str
    name: str
    url: str
    items: int = DEFAULT_ITEMS
    # Auto-print a slip for each new item (off by default).
    auto_print: bool = False
    check_minutes: int = DEFAULT_CHECK_MINUTES
    quiet_start: str | None = DEFAULT_QUIET_START  # "HH:MM"; None: no quiet hours
    quiet_end: str | None = DEFAULT_QUIET_END
    quiet_mode: str = "skip"  # skip: drop quiet-hours items; morning: print after
    auto_qr: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> FeedConfig:
        """Build from stored options."""
        items = int(data.get("items") or DEFAULT_ITEMS)
        minutes = int(data.get("check_minutes") or DEFAULT_CHECK_MINUTES)
        mode = data.get("quiet_mode") or "skip"
        return cls(
            str(data["id"]),
            str(data["name"]),
            str(data["url"]),
            max(1, min(MAX_ITEMS, items)),
            bool(data.get("auto_print", False)),
            max(5, min(1440, minutes)),
            data.get("quiet_start", DEFAULT_QUIET_START) or None,
            data.get("quiet_end", DEFAULT_QUIET_END) or None,
            mode if mode in QUIET_MODES else "skip",
            bool(data.get("auto_qr", False)),
        )

    def as_dict(self) -> dict:
        """Return the stored form."""
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "items": self.items,
            "auto_print": self.auto_print,
            "check_minutes": self.check_minutes,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
            "quiet_mode": self.quiet_mode,
            "auto_qr": self.auto_qr,
        }


def feeds_from_options(options: dict) -> list[FeedConfig]:
    """List the configured feeds, in order."""
    out = []
    for raw in options.get("feeds") or []:
        try:
            out.append(FeedConfig.from_dict(raw))
        except KeyError, TypeError, ValueError:
            continue
    return out


def find_feed(feeds: list[FeedConfig], wanted: str | None) -> FeedConfig | None:
    """Match an ID or name (loosely, as spoken), else the first feed."""
    if not feeds:
        return None
    if wanted:
        low = " ".join(wanted.lower().split())
        for feed in feeds:
            if low in (feed.id.lower(), feed.name.lower()):
                return feed
        for feed in feeds:  # "bbc" finds "BBC News"
            if low in feed.name.lower() or feed.name.lower() in low:
                return feed
        return None
    return feeds[0]


async def async_download(hass: HomeAssistant, url: str) -> bytes:
    """GET a URL with a timeout and size cap."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise FetchError(f"HTTP {resp.status}")
            data = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                data += chunk
                if len(data) > MAX_BYTES:
                    raise FetchError("the feed is too large")
            return bytes(data)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise FetchError(str(err) or type(err).__name__) from err


async def async_fetch_feed(hass: HomeAssistant, url: str, limit: int) -> Feed:
    """Download and parse a feed (parsing runs in the executor)."""
    data = await async_download(hass, url)
    try:
        return await hass.async_add_executor_job(parse_feed, data, limit)
    except FeedError as err:
        raise FetchError(str(err)) from err


async def async_live_quote(
    hass: HomeAssistant, store: TinyPressStore
) -> tuple[str, str] | None:
    """Today's Wikiquote quote and author, cached for the day; None on failure."""
    today = dt_util.now().date().isoformat()
    cached = store.get_setting(SETTING_LIVE_QUOTE_CACHE)
    if isinstance(cached, dict) and cached.get("day") == today:
        return cached["text"], cached["author"]
    found = None
    for url in (WIKIQUOTE_API_URL, WIKIQUOTE_URL):
        try:
            data = await async_download(hass, url)
        except FetchError as err:
            _LOGGER.info("Couldn't get Wikiquote's quote of the day: %s", err)
            continue
        if url == WIKIQUOTE_API_URL:
            data = wikiquote_api_html(data) or b""
        found = await hass.async_add_executor_job(wikiquote_quote, data)
        if found is not None:
            break
    if found is None:
        _LOGGER.info("No usable Wikiquote quote of the day; using a bundled one")
        return None
    store.set_setting(
        SETTING_LIVE_QUOTE_CACHE, {"day": today, "text": found[0], "author": found[1]}
    )
    return found
