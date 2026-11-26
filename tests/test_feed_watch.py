"""Auto-print a slip when a feed adds an item."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tiny_press.feed_watch import (
    SETTING_FEED_WATCH,
    FeedWatcher,
    QuietHours,
    in_quiet_hours,
    item_key,
)
from custom_components.tiny_press.fetch import FeedConfig
from custom_components.tiny_press.generators.feeds import FeedItem

from .fake_printer import FakePrinter

URL = "https://news.example.com/rss"
NOON = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def rss(*items: tuple[str, datetime]) -> bytes:
    body = "".join(
        f"<item><title>{title}</title><link>https://news.example.com/{title}</link>"
        f"<pubDate>{format_datetime(when)}</pubDate></item>"
        for title, when in items
    )
    return f"<rss><channel><title>News</title>{body}</channel></rss>".encode()


def feed(**changes: Any) -> dict[str, Any]:
    return {**FeedConfig("news", "News", URL).as_dict(), "auto_print": True, **changes}


NO_QUIET = {"quiet_start": None, "quiet_end": None}


class Harness:
    """A watcher, the mocked feed and a record of what printed."""

    def __init__(
        self, hass: HomeAssistant, entry: MockConfigEntry, mock: AiohttpClientMocker
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.mock = mock
        self.coordinator = entry.runtime_data
        self.watcher = FeedWatcher(hass, self.coordinator)
        self.printed: list[str] = []
        self.fail = False
        real = self.coordinator.async_print

        async def spy(job: Any) -> dict[str, Any]:
            if self.fail:
                raise HomeAssistantError("printer offline")
            self.printed.append(job.response["headlines"][0])
            assert job.label == "New item"
            return await real(job)

        patcher = patch.object(self.coordinator, "async_print", spy)
        patcher.start()
        entry.async_on_unload(patcher.stop)

    def serve(self, *items: tuple[str, datetime]) -> None:
        self.mock.clear_requests()
        self.mock.get(URL, content=rss(*items))

    async def check(self, now: datetime) -> int:
        return await self.watcher.async_check(now)

    @property
    def state(self) -> dict[str, Any]:
        return self.coordinator.store.get_setting(SETTING_FEED_WATCH) or {}


async def _harness(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock: AiohttpClientMocker,
    quiet: dict[str, Any] | None = None,
    **feed_changes: Any,
) -> Harness:
    await hass.config.async_set_time_zone("UTC")
    hass.config_entries.async_update_entry(
        entry,
        options={
            "feeds": [feed(**feed_changes)],
            **(NO_QUIET if quiet is None else quiet),
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return Harness(hass, entry, mock)


def test_quiet_hours_and_keys() -> None:
    night = QuietHours.from_options({})  # default 9 PM to 7 AM, skip
    assert night == QuietHours("21:00", "07:00", "skip")
    day = QuietHours.from_options(
        {"quiet_start": "09:00:00", "quiet_end": "17:00:00", "quiet_mode": "x"}
    )
    assert day.mode == "skip"
    never = QuietHours.from_options(NO_QUIET)
    at = lambda h, m=0: datetime(2026, 11, 26, h, m, tzinfo=UTC)  # noqa: E731
    assert in_quiet_hours(night, at(23)) and in_quiet_hours(night, at(6, 59))
    assert not in_quiet_hours(night, at(7)) and not in_quiet_hours(night, at(12))
    assert in_quiet_hours(day, at(9)) and not in_quiet_hours(day, at(17))
    assert not in_quiet_hours(never, at(23))
    assert item_key(FeedItem("t", "https://x/1")) == "https://x/1"
    assert item_key(FeedItem("t", None, NOON)) == f"t|{NOON.isoformat()}"
    loaded = FeedConfig.from_dict({"id": "a", "name": "A", "url": URL})
    assert loaded.auto_print is False and loaded.check_minutes == 15
    assert (
        FeedConfig.from_dict({**loaded.as_dict(), "check_minutes": 1}).check_minutes
        == 5
    )


async def test_new_items_print_once(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    h = await _harness(hass, config_entry, aioclient_mock)
    h.serve(("a", NOON - timedelta(hours=1)), ("b", NOON - timedelta(hours=2)))
    assert await h.check(NOON) == 0  # first check: no backlog
    assert len(h.state["news"]["seen"]) == 2

    h.serve(("c", NOON), ("a", NOON - timedelta(hours=1)))
    assert await h.check(NOON + timedelta(minutes=5)) == 0  # not due yet
    assert aioclient_mock.call_count == 0
    assert await h.check(NOON + timedelta(minutes=15)) == 1
    assert h.printed == ["c"]
    assert await h.check(NOON + timedelta(minutes=30)) == 0  # already seen

    # A burst prints at most three, oldest first; stale items never print.
    h.serve(
        *((f"n{i}", NOON + timedelta(minutes=40 - i)) for i in range(5)),
        ("stale", NOON - timedelta(hours=13)),
    )
    assert await h.check(NOON + timedelta(minutes=45)) == 3
    assert h.printed[1:] == ["n2", "n1", "n0"]
    assert await h.check(NOON + timedelta(hours=1)) == 0


async def test_quiet_hours_skip(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    h = await _harness(
        hass, config_entry, aioclient_mock, quiet={"quiet_mode": "skip"}
    )  # the default quiet hours, 9 PM to 7 AM
    night = datetime(2026, 11, 26, 22, 0, tzinfo=UTC)
    h.serve(("a", night - timedelta(hours=1)))
    await h.check(night)
    h.serve(("b", night + timedelta(minutes=10)))
    assert await h.check(night + timedelta(minutes=20)) == 0
    morning = datetime(2026, 11, 27, 7, 30, tzinfo=UTC)
    h.serve(("b", night + timedelta(minutes=10)))
    assert await h.check(morning) == 0  # skipped, not printed later
    assert h.printed == []


async def test_quiet_hours_morning(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    h = await _harness(
        hass,
        config_entry,
        aioclient_mock,
        quiet={
            "quiet_start": "21:00:00",
            "quiet_end": "07:00:00",
            "quiet_mode": "morning",
        },
    )
    night = datetime(2026, 11, 26, 22, 0, tzinfo=UTC)
    h.serve(("a", night - timedelta(hours=1)))
    await h.check(night)
    items = [(f"q{i}", night + timedelta(minutes=10 * (5 - i))) for i in range(5)]
    h.serve(*items)
    assert await h.check(night + timedelta(hours=1)) == 0
    assert len(h.state["news"]["pending"]) == 3  # kept for the morning, capped
    h.serve(*items)
    assert await h.check(datetime(2026, 11, 27, 7, 0, tzinfo=UTC)) == 3
    assert h.printed == ["q2", "q1", "q0"]
    assert h.state["news"]["pending"] == []


async def test_failed_prints_wait(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    h = await _harness(hass, config_entry, aioclient_mock)
    h.serve(("a", NOON))
    await h.check(NOON)
    h.serve(("b", NOON + timedelta(minutes=10)), ("a", NOON))
    h.fail = True
    assert await h.check(NOON + timedelta(minutes=15)) == 0
    assert [p["title"] for p in h.state["news"]["pending"]] == ["b"]
    h.fail = False
    assert await h.check(NOON + timedelta(minutes=30)) == 1
    assert h.printed == ["b"]

    # A feed that can't be read waits for its next check.
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=500)
    assert await h.check(NOON + timedelta(minutes=45)) == 0
    assert h.state["news"]["last"] == (NOON + timedelta(minutes=45)).isoformat()


async def test_off_by_default_and_fresh_restart(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    h = await _harness(hass, config_entry, aioclient_mock, auto_print=False)
    h.serve(("a", NOON))
    assert await h.check(NOON) == 0
    assert aioclient_mock.call_count == 0 and h.state == {}

    hass.config_entries.async_update_entry(
        config_entry, options={"feeds": [feed()], **NO_QUIET}
    )
    await hass.async_block_till_done()
    await h.check(NOON)
    assert "news" in h.state
    hass.config_entries.async_update_entry(
        config_entry, options={"feeds": [feed(auto_print=False)], **NO_QUIET}
    )
    await hass.async_block_till_done()
    await h.check(NOON + timedelta(hours=1))
    assert h.state == {}  # switched off: forgotten, so no backlog later


async def test_runs_every_minute(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to(NOON)
    aioclient_mock.get(URL, content=rss(("a", NOON)))
    await hass.config.async_set_time_zone("UTC")
    hass.config_entries.async_update_entry(
        config_entry, options={"feeds": [feed()], **NO_QUIET}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    # The interval callback runs as a background task.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert aioclient_mock.call_count == 1
    state = config_entry.runtime_data.store.get_setting(SETTING_FEED_WATCH)
    assert state["news"]["seen"] == ["https://news.example.com/a"]


async def test_edit_feed_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
) -> None:
    hass.config_entries.async_update_entry(
        config_entry,
        options={"feeds": [FeedConfig("news", "News", URL).as_dict()]},
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert "edit_feed" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "edit_feed"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"feed": "news"}
    )
    assert result["step_id"] == "feed_settings"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "items": 4,
            "auto_print": True,
            "check_minutes": 30,
            "auto_qr": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    saved = config_entry.options["feeds"][0]
    assert saved["auto_print"] is True and saved["check_minutes"] == 30
    assert "quiet_start" not in saved  # quiet hours are global (Settings)
    assert saved["auto_qr"] is True and saved["items"] == 4
