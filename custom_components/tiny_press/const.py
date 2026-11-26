"""Constants for Tiny Press."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

DOMAIN: Final = "tiny_press"
MANUFACTURER: Final = "Epson"
DEFAULT_MODEL: Final = "TM-m30III"

CONF_PAPER_WIDTH: Final = "paper_width"
CONF_MAX_LENGTH_MM: Final = "max_length_mm"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_PRINT_TEST_PAGE: Final = "print_test_page"
CONF_AI_TASK: Final = "ai_task_entity"
CONF_WEATHER: Final = "weather_entity"
CONF_CALENDARS: Final = "calendar_entities"
CONF_TODOS: Final = "todo_entities"
CONF_MORNING_BOTTOM: Final = "morning_bottom"
CONF_FEEDS: Final = "feeds"
# Where the morning slip's bottom comes from: "online" uses live sources where
# one exists (today: Wikiquote for the quote), with bundled content as the
# fallback; "local" uses bundled content only; "feed" takes the quote from a
# chosen feed (falling back to bundled).
CONF_BOTTOM_SOURCE: Final = "bottom_source"
BOTTOM_SOURCES: Final = ("online", "local", "feed")
CONF_LIVE_QUOTE: Final = "live_quote"  # v0.9.0 toggle, read when bottom_source is unset


def bottom_source(options: Any) -> str:
    """Return the morning slip bottom's source, honoring v0.9.0's Live quote toggle."""
    source = options.get(CONF_BOTTOM_SOURCE)
    if source in BOTTOM_SOURCES:
        return source
    return "online" if options.get(CONF_LIVE_QUOTE, True) else "local"


CONF_MORNING_FEED: Final = "morning_feed"
# Holidays and themes (Configure -> Holidays and themes).
CONF_THEME: Final = "theme"  # auto | off | a fixed theme (themes.json key)
CONF_SECULAR_DAYS: Final = "secular_days"  # seasons, science, public, school
CONF_HOLIDAY_GROUPS: Final = "holiday_groups"  # opt-in faith and cultural groups
CONF_EXCLUDED_DAYS: Final = "excluded_days"  # single days switched off in a group
CONF_HOLIDAY_CALENDARS: Final = "holiday_calendars"  # public holidays
CONF_SCHOOL_DAY: Final = "school_day"  # "YYYY-MM-DD"
CONF_CUSTOM_DAYS: Final = "custom_days"  # [{id, name, date "MM-DD", banner, art}]
CONF_QUOTE_FEED: Final = "quote_feed"  # feed ID when bottom_source is "feed"
# Quiet hours for feed auto-print (one setting for all feeds).
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_QUIET_MODE: Final = "quiet_mode"
CONF_AI_JOKES: Final = "ai_jokes"  # off: bundled, human-written jokes and facts

DEFAULT_PORT: Final = 9100
DEFAULT_MAX_LENGTH_MM: Final = 600
DEFAULT_POLL_INTERVAL: Final = 60  # seconds
MIN_POLL_INTERVAL: Final = 15
MAX_POLL_INTERVAL: Final = 3600

# The TM-m30III prints at 203 dpi (8 dots/mm). Epson's spec sheet gives
# 576 dots per line on 80 mm paper (72 mm printable) and 420 dots per line
# on 58 mm paper (52.5 mm printable).
DOTS_PER_MM: Final = 8
PAPER_80MM: Final = "80"
PAPER_58MM: Final = "58"
PAPER_DOTS: Final[dict[str, int]] = {PAPER_80MM: 576, PAPER_58MM: 420}

# Paper fed past the last printed line before the cut, plus the top margin.
FEED_MM: Final = 14

OFFLINE_REPAIR_AFTER_HOURS: Final = 24
ISSUE_OFFLINE: Final = "printer_offline"

EVENT_PRINTED: Final = "tiny_press_printed"
EVENT_RATE_LIMITED: Final = "tiny_press_rate_limited"

STORAGE_VERSION: Final = 1
HISTORY_SIZE: Final = 20
RECENT_JOKES: Final = 40  # bundled jokes/facts not repeated within this many

SETTING_MAZE_DIFFICULTY: Final = "maze_difficulty"
SETTING_KID_PROFILE: Final = "kid_profile"
SETTING_ADULT_PROFILE: Final = "adult_profile"
SETTING_SUDOKU_DIFFICULTY: Final = "sudoku_difficulty"
SETTING_STORY_LENGTH: Final = "story_length"
SETTING_MORNING_KID_DAY: Final = "morning_kid_day"


class PrintType(StrEnum):
    """Print types the general ``tiny_press.print`` action accepts."""

    MAZE = "maze"
    WORD_SEARCH = "word_search"
    MATH = "math"
    JOKE = "joke"
    FACT = "fact"
    KID_PACK = "kid_pack"
    WEATHER = "weather"
    SUDOKU = "sudoku"
    CROSSWORD = "crossword"
    CRYPTOGRAM = "cryptogram"
    PUZZLE_PACK = "puzzle_pack"
    STORY = "story"
    MORNING_SLIP = "morning_slip"
    HISTORY = "history"
    FEED = "feed"
    KID_SUDOKU = "kid_sudoku"
    SPELLING = "spelling"
    SPELLING_SEARCH = "spelling_search"
    TEST_PAGE = "test_page"


class Difficulty(StrEnum):
    """Normalized difficulty."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class PaperState(StrEnum):
    """States of the paper sensor."""

    OK = "ok"
    NEAR_END = "near_end"
    OUT = "out"
    COVER_OPEN = "cover_open"
    OFFLINE = "offline"


ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_TYPE: Final = "type"
ATTR_PROFILE: Final = "profile"
ATTR_DIFFICULTY: Final = "difficulty"
ATTR_SEED: Final = "seed"
ATTR_TEXT: Final = "text"
ATTR_TITLE: Final = "title"
ATTR_SIZE: Final = "size"
ATTR_PATH: Final = "path"

TEXT_SIZES: Final = ("small", "normal", "large")
