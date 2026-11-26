"""Holidays and themes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tiny_press import jobs, services
from custom_components.tiny_press.const import DOMAIN, PAPER_DOTS, Difficulty
from custom_components.tiny_press.generators import (
    crossword,
    morning,
    observances as ob,
    word_search,
)
from custom_components.tiny_press.profiles import Profile
from custom_components.tiny_press.render import layout

from .fake_printer import FakePrinter


def utc(moment: datetime) -> datetime:
    return moment


def test_season_moments_and_easter() -> None:
    # Published 2026 times (UTC): Mar 20 14:46, Jun 21 08:24, Sep 23 00:05,
    # Dec 21 20:50. Within a few minutes is plenty for picking the date.
    expected = {
        "march": datetime(2026, 3, 20, 14, 46, tzinfo=UTC),
        "june": datetime(2026, 6, 21, 8, 24, tzinfo=UTC),
        "september": datetime(2026, 9, 23, 0, 5, tzinfo=UTC),
        "december": datetime(2026, 12, 21, 20, 50, tzinfo=UTC),
    }
    for which, when in expected.items():
        assert abs((ob.season_moment(2026, which) - when).total_seconds()) < 300
    assert ob.western_easter(2026) == date(2026, 4, 5)
    assert ob.western_easter(2027) == date(2027, 3, 28)
    assert ob.orthodox_easter(2026) == date(2026, 4, 12)
    assert ob.orthodox_easter(2027) == date(2027, 5, 2)
    assert ob.nth_weekday(2026, 10, 0, 2) == date(2026, 10, 12)  # 2nd Monday
    assert ob.nth_weekday(2026, 4, 4, -1) == date(2026, 4, 24)  # last Friday
    assert ob.season_of(date(2026, 11, 26), utc, 40) == "autumn"
    assert ob.season_of(date(2026, 11, 26), utc, -33) == "spring"
    assert ob.season_of(date(2026, 1, 5), utc, 40) == "winter"


def test_data_is_complete() -> None:
    groups = {g["id"] for g in ob.groups()}
    for item in ob.all_observances():
        assert item["group"] in groups
        assert ob.art(item["art"]), item["id"]
        assert len(item["words"]) >= 6 and item.get("clues"), item["id"]
        assert len(item["banner"]) <= 200, item["id"]
        if item["when"].get("table"):
            years = {d[:4] for d in ob._data()["dates"][item["id"]]}
            assert {str(y) for y in range(2026, 2036)} <= years, item["id"]
    for name in ob.art_names():
        lines = ob.art(name)
        assert len(lines) <= 8 and max(len(line) for line in lines) <= 28, name
        assert all(line.isascii() for line in lines), name
    assert ob.theme("spring").art and ob.theme("pi_day").jokes
    assert ob.theme("space").words  # fixed theme from themes.json
    assert ob.theme("nope") is None


def test_todays_groups_and_order() -> None:
    def ids(day: date, **kwargs: Any) -> list[str]:
        return [o.id for o in ob.todays(day, to_local=utc, latitude=40, **kwargs)]

    diwali = date(2026, 11, 8)
    assert ids(diwali) == []  # faith and cultural groups are off by default
    assert ids(diwali, picked_groups={"hindu"}) == ["diwali"]
    assert ids(diwali, picked_groups={"hindu"}, excluded={"diwali"}) == []
    assert ids(date(2026, 3, 14)) == ["pi_day"]  # science days on by default
    assert ids(date(2026, 3, 14), secular=set()) == []
    assert ids(date(2026, 3, 20)) == ["season:march"]
    assert ids(date(2026, 4, 5), picked_groups={"christian"}) == ["easter"]
    # Custom first, then cultural, school, public, science, season.
    found = ids(
        date(2026, 3, 20),
        picked_groups={"muslim"},
        school_day="2026-03-20",
        custom=[{"id": "gran", "name": "Gran's birthday", "date": "03-20"}],
        public=["Spring Bank Day"],
    )
    assert found == [
        "custom:gran",
        "eid_al_fitr",
        "school",
        "public:Spring Bank Day",
        "season:march",
    ]
    south = ob.todays(date(2026, 12, 21), to_local=utc, latitude=-33)[0]
    assert "first day of summer" in south.banner
    dead = [date(2026, 11, 1), date(2026, 11, 2)]
    assert all(
        ids(d, picked_groups={"heritage"}) == ["dia_de_los_muertos"] for d in dead
    )


def test_review_fixes() -> None:
    """Fixes from the cultural-sensitivity review."""

    def ids(day: date, groups: set[str]) -> list[str]:
        return [
            o.id
            for o in ob.todays(day, to_local=utc, latitude=40, picked_groups=groups)
        ]

    # Hanukkah counts for the year it starts in (not a Jan 1 tail end).
    assert ids(date(2028, 12, 13), {"jewish"}) == ["hanukkah"]
    assert ids(date(2028, 1, 1), {"jewish"}) == []
    # Faith and cultural days outrank fun days on a shared date.
    shared = ids(date(2029, 2, 14), {"fun", "muslim", "buddhist"})
    assert shared[-1] == "valentines" and len(shared) == 3
    # Days of the same rank take turns: neither always wins over the years.
    firsts = {
        ids(day, {"east_asian"})[0]
        for day in (
            date(y, *map(int, d.split("-")[1:]))
            for y, d in [(int(d[:4]), d) for d in ob._data()["dates"]["chuseok"]]
        )
    }
    assert firsts == {"mid_autumn", "chuseok"}
    # Diwali belongs to the Sikh group too (Bandi Chhor Divas).
    assert ids(date(2026, 11, 8), {"sikh"}) == ["diwali"]
    # Yom Kippur is solemn: no jokes.
    yom = ob.todays(
        date(2026, 9, 21), to_local=utc, latitude=40, picked_groups={"jewish"}
    )
    assert yom[0].solemn and not yom[0].theme.jokes
    assert "Union troops" in next(
        o["banner"] for o in ob.all_observances() if o["id"] == "juneteenth"
    )


def test_themed_generators() -> None:
    theme = ob.theme("lunar_new_year")
    assert theme is not None
    puzzle = word_search.generate("2", 7, theme_words=theme.words)
    assert set(puzzle.words) & set(theme.words)
    extra = [{"word": w, "clue": c} for w, c in theme.clues.items()]
    words = {e.word for e in crossword.generate("medium", 7, extra).entries}
    assert words & set(theme.clues)


@pytest.mark.parametrize("width", sorted(PAPER_DOTS.values()))
def test_layouts(width: int) -> None:
    day = date(2026, 11, 8)
    found = ob.todays(day, to_local=utc, latitude=40, picked_groups={"hindu"})
    slip = morning.MorningSlip(day, None, (), 0, banner=found[0], also=("Pi Day",))
    footer = layout.Footer("Morning slip", "ABCD", day, show_id=False)
    assert layout.morning_page(width, slip, footer).render()[0].width == width
    job = jobs.maze_job(Difficulty.EASY, 1, None, ob.theme("autumn"))
    assert job.build(width).render()[0].width == width
    pack = jobs.kid_pack_job(
        Profile("r", "kid", "Rosie", grade="2"), Difficulty.EASY, 1, ob.theme("summer")
    )
    assert pack.build(width).render()[0].width == width


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, **options: Any) -> None:
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_current_theme(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-03-14 15:00:00+00:00")  # Pi Day
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    theme, recognized = services.current_theme(hass, coordinator)
    assert theme.id == "pi_day" and recognized
    hass.config_entries.async_update_entry(
        config_entry, options={"secular_days": ["seasons"]}
    )
    theme, recognized = services.current_theme(hass, coordinator)
    assert theme.id == "winter" and not recognized  # Mar 14: still winter (north)
    hass.config_entries.async_update_entry(config_entry, options={"theme": "space"})
    assert services.current_theme(hass, coordinator)[0].id == "space"
    hass.config_entries.async_update_entry(config_entry, options={"theme": "off"})
    assert services.current_theme(hass, coordinator) == (None, False)


async def test_morning_banner_and_public_holiday(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-11-08 12:00:00+00:00")
    hass.states.async_set("calendar.holidays", "off")

    async def get_events(call: ServiceCall) -> dict[str, Any]:
        return {
            "calendar.holidays": {
                "events": [
                    {"summary": "Remembrance Sunday", "start": "2026-11-08"},
                    {"summary": "Meeting", "start": "2026-11-08T09:00:00+00:00"},
                ]
            }
        }

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await _setup(
        hass,
        config_entry,
        holiday_groups=["hindu"],
        holiday_calendars=["calendar.holidays"],
        morning_bottom="joke",
    )
    captured: list[morning.MorningSlip] = []
    real = jobs.morning_job

    def spy(slip: morning.MorningSlip) -> Any:
        captured.append(slip)
        return real(slip)

    with patch.object(jobs, "morning_job", spy):
        await hass.services.async_call(
            DOMAIN, "print_morning_slip", {}, blocking=True, return_response=True
        )
    slip = captured[0]
    assert slip.banner.id == "diwali" and slip.banner.art
    assert slip.also == ("Remembrance Sunday",)  # the timed event isn't a holiday
    assert slip.joke.credit == "Tiny Press" or slip.joke.setup  # a joke printed


async def test_quote_from_a_feed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    url = "https://quotes.example.com/rss"
    aioclient_mock.get(
        url,
        content=b"<rss><channel><title>Q</title><item><title>Maya Angelou</title>"
        b"<description>Nothing will work unless you do.</description></item>"
        b"</channel></rss>",
    )
    await _setup(
        hass,
        config_entry,
        morning_bottom="quote",
        bottom_source="feed",
        quote_feed="q",
        feeds=[{"id": "q", "name": "Daily Quotes", "url": url}],
    )
    quote = await services._morning_quote(hass, config_entry.runtime_data)
    assert quote == morning.Quote(
        "Nothing will work unless you do.", "Maya Angelou", None, "Daily Quotes"
    )


async def test_holiday_options(
    hass: HomeAssistant, config_entry: MockConfigEntry, printer: FakePrinter
) -> None:
    await _setup(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert "holidays" in result["menu_options"] and "add_day" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "holidays"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "theme": "auto",
            "secular_days": ["seasons", "science"],
            "school_day": "2026-09-02",
            "holiday_groups": ["jewish", "hindu"],
        },
    )
    assert result["step_id"] == "holiday_days"
    keep = [o["id"] for o in ob.all_observances() if o["group"] in ("jewish", "hindu")]
    keep.remove("yom_kippur")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"days": keep}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    opts = config_entry.options
    assert opts["holiday_groups"] == ["jewish", "hindu"]
    assert opts["excluded_days"] == ["yom_kippur"]
    assert opts["secular_days"] == ["seasons", "science"]
    assert opts["school_day"] == "2026-09-02"

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_day"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"name": "Gran's birthday", "date": "2026-05-04", "art": "cake"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options["custom_days"] == [
        {
            "id": "gran_s_birthday",
            "name": "Gran's birthday",
            "date": "05-04",
            "banner": "Today is Gran's birthday!",
            "art": "cake",
        }
    ]
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert "remove_day" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_day"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"days": ["gran_s_birthday"]}
    )
    await hass.async_block_till_done()
    assert config_entry.options["custom_days"] == []


async def test_no_jokes_on_a_solemn_day(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    printer: FakePrinter,
    freezer: FrozenDateTimeFactory,
) -> None:
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-09-21 12:00:00+00:00")  # Yom Kippur
    await _setup(hass, config_entry, holiday_groups=["jewish"], morning_bottom="joke")
    captured: list[morning.MorningSlip] = []
    real = jobs.morning_job

    def spy(slip: morning.MorningSlip) -> Any:
        captured.append(slip)
        return real(slip)

    with patch.object(jobs, "morning_job", spy):
        await hass.services.async_call(
            DOMAIN, "print_morning_slip", {}, blocking=True, return_response=True
        )
    assert captured[0].banner.id == "yom_kippur"
    assert captured[0].joke.kind == "fact"  # the joke bottom becomes a fact
