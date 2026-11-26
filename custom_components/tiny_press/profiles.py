"""Household profiles (kids and adults), stored in the entry's options."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Literal

from .const import Difficulty

GRADES = ("K", "1", "2", "3", "4", "5")
DEFAULT_GRADE = "3"
CONF_PROFILES = "profiles"
KID = "kid"
ADULT = "adult"


def grade_number(grade: str | int) -> int:
    """K is 0; 1-5 are themselves. Anything else is clamped to 0-5."""
    text = str(grade).strip().upper()
    if text in ("K", "0"):
        return 0
    try:
        return max(0, min(5, int(text)))
    except ValueError:
        return grade_number(DEFAULT_GRADE)


def grade_label(n: int) -> str:
    """0 -> "K", 3 -> "3"."""
    return GRADES[max(0, min(5, n))]


def slugify(name: str) -> str:
    """Make a stable ID from a name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "profile"


@dataclass(frozen=True, slots=True)
class Profile:
    """One person the printer makes things for."""

    id: str
    kind: Literal["kid", "adult"]
    name: str
    grade: str = DEFAULT_GRADE  # kids: reading grade
    interests: str = ""  # kids
    stretch: bool = False  # kids: +1 grade on puzzles (reading and math)
    spelling_todo: str = ""  # kids: a todo entity holding the list (one word per item)
    difficulty: str = Difficulty.MEDIUM.value  # adults
    math_grade: str = ""  # kids: empty means the same as the reading grade
    maze_difficulty: str = ""  # kids: empty follows the Maze difficulty select
    ha_user: str = ""  # the Home Assistant user this profile belongs to, if any
    daily_limit: int = 0  # kids: prints per day; 0 uses the Kid-mode limits setting

    @property
    def display_name(self) -> str | None:
        """The name to print in headers (None for the built-in default kid)."""
        return (
            None
            if self.id in ("kid", "adult") and self.name in ("Kid", "Adult")
            else self.name
        )

    @property
    def puzzle_grade(self) -> str:
        """Reading grade used for word puzzles (one higher with "stretch")."""
        return grade_label(grade_number(self.grade) + (1 if self.stretch else 0))

    @property
    def math_level(self) -> str:
        """Math grade used for math and number puzzles (one higher with "stretch")."""
        base = grade_number(self.math_grade or self.grade)
        return grade_label(base + (1 if self.stretch else 0))

    @property
    def reading_grade(self) -> str:
        """Grade used for reading (stories, jokes)."""
        return grade_label(grade_number(self.grade))

    def as_dict(self) -> dict[str, Any]:
        """Serialize for the options."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        """Load from the options, tolerating missing keys."""
        return cls(
            id=str(data.get("id") or slugify(str(data.get("name", "")))),
            kind=ADULT if data.get("kind") == ADULT else KID,
            name=str(data.get("name") or "Kid"),
            grade=grade_label(grade_number(data.get("grade", DEFAULT_GRADE))),
            interests=str(data.get("interests") or ""),
            stretch=bool(data.get("stretch", False)),
            spelling_todo=str(data.get("spelling_todo") or ""),
            difficulty=str(data.get("difficulty") or Difficulty.MEDIUM.value),
            math_grade=(
                grade_label(grade_number(data["math_grade"]))
                if data.get("math_grade") not in (None, "")
                else ""
            ),
            ha_user=str(data.get("ha_user") or ""),
            daily_limit=_positive_int(data.get("daily_limit")),
            maze_difficulty=(
                str(data["maze_difficulty"])
                if data.get("maze_difficulty") in {d.value for d in Difficulty}
                else ""
            ),
        )


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except TypeError, ValueError:
        return 0


DEFAULT_KID = Profile(id="kid", kind=KID, name="Kid")
DEFAULT_ADULT = Profile(id="adult", kind=ADULT, name="Adult")


def load_profiles(options: dict[str, Any]) -> list[Profile]:
    """All configured profiles."""
    return [Profile.from_dict(p) for p in options.get(CONF_PROFILES, [])]


def profiles_of(options: dict[str, Any], kind: str) -> list[Profile]:
    """Return configured profiles of one kind, or the built-in default."""
    found = [p for p in load_profiles(options) if p.kind == kind]
    if found:
        return found
    return [DEFAULT_KID if kind == KID else DEFAULT_ADULT]


def find_profile(
    options: dict[str, Any], kind: str, wanted: str | None, active_id: str | None
) -> Profile:
    """Match a name or ID (case-insensitive), else the active one, else the first."""
    candidates = profiles_of(options, kind)
    for key in (wanted, active_id):
        if not key:
            continue
        low = key.strip().lower()
        for profile in candidates:
            if low in (profile.id.lower(), profile.name.lower()):
                return profile
    return candidates[0]


def find_any_profile(options: dict[str, Any], wanted: str) -> Profile | None:
    """Match a name or ID across kids and adults."""
    low = wanted.strip().lower()
    for profile in load_profiles(options):
        if low in (profile.id.lower(), profile.name.lower()):
            return profile
    return None
