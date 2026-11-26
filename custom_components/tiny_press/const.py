"""Constants for Tiny Press."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "tiny_press"
MANUFACTURER: Final = "Epson"
DEFAULT_MODEL: Final = "TM-m30III"

CONF_PAPER_WIDTH: Final = "paper_width"
CONF_MAX_LENGTH_MM: Final = "max_length_mm"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_PRINT_TEST_PAGE: Final = "print_test_page"
CONF_AI_TASK: Final = "ai_task_entity"

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

STORAGE_VERSION: Final = 1
HISTORY_SIZE: Final = 20
RECENT_JOKES: Final = 40  # bundled jokes/facts not repeated within this many

SETTING_MAZE_DIFFICULTY: Final = "maze_difficulty"
SETTING_KID_PROFILE: Final = "kid_profile"


class PrintType(StrEnum):
    """Print types the general ``tiny_press.print`` action accepts."""

    MAZE = "maze"
    WORD_SEARCH = "word_search"
    MATH = "math"
    JOKE = "joke"
    FACT = "fact"
    KID_PACK = "kid_pack"
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
