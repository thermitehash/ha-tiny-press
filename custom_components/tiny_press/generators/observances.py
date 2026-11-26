"""Holidays and themes: which days are recognized today, and their themes.

Pure. Recognized only on the day itself. Groups are opt-in, except the
secular ones (seasons, science days, public holidays, first day of school),
which are on by default. Faith and cultural days come in groups that are all
off by default and treated the same way; single days inside a picked group
can be switched off.

Dates: fixed days, "nth weekday" rules, Easter computed (Western and
Orthodox), solstices and equinoxes computed (Meeus), and a bundled table for
moving lunar and lunisolar dates (``script/build_observances.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
import hashlib
import math
from typing import Any

from .data import load_json

SECULAR_DEFAULT = ("seasons", "science", "public", "school")
SEASON_NAMES = ("spring", "summer", "autumn", "winter")

# Meeus, Astronomical Algorithms, chapter 27: mean equinox and solstice
# (years 2000-3000) and the periodic terms.
_MEAN = {
    "march": (2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057),
    "june": (2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030),
    "september": (2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078),
    "december": (2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032),
}
_TERMS = (
    (485, 324.96, 1934.136), (203, 337.23, 32964.467), (199, 342.08, 20.186),
    (182, 27.85, 445267.112), (156, 73.14, 45036.886), (136, 171.52, 22518.443),
    (77, 222.54, 65928.934), (74, 296.72, 3034.906), (70, 243.58, 9037.513),
    (58, 119.81, 33718.147), (52, 297.17, 150.678), (50, 21.02, 2281.226),
    (45, 247.54, 29929.562), (44, 325.15, 31555.956), (29, 60.93, 4443.417),
    (18, 155.12, 67555.328), (17, 288.79, 4562.452), (16, 198.04, 62894.029),
    (14, 199.76, 31436.921), (12, 95.39, 14577.848), (12, 287.11, 31931.756),
    (12, 320.81, 34777.259), (9, 227.73, 1222.114), (8, 15.45, 16859.074),
)  # fmt: skip
_J2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)  # JD 2451545.0


def season_moment(year: int, which: str) -> datetime:
    """Return the equinox or solstice (``march``, ``june``...) in UTC.

    Accurate to about a minute; the ~1 minute between TT and UTC is ignored.
    """
    y = (year - 2000) / 1000
    a, b, c, d, e = _MEAN[which]
    jde0 = a + b * y + c * y**2 + d * y**3 + e * y**4
    t = (jde0 - 2451545.0) / 36525
    w = math.radians(35999.373 * t - 2.47)
    dl = 1 + 0.0334 * math.cos(w) + 0.0007 * math.cos(2 * w)
    s = sum(a_ * math.cos(math.radians(b_ + c_ * t)) for a_, b_, c_ in _TERMS)
    jde = jde0 + 0.00001 * s / dl
    return _J2000 + timedelta(days=jde - 2451545.0)


def season_starts(year: int, to_local: Any) -> dict[date, str]:
    """Local dates of the year's equinoxes and solstices -> "march" etc."""
    return {
        to_local(season_moment(year, which)).date(): which
        for which in ("march", "june", "september", "december")
    }


def season_of(day: date, to_local: Any, latitude: float) -> str:
    """Return the astronomical season on ``day`` (flipped south of the equator)."""
    starts = sorted(
        (to_local(season_moment(year, which)).date(), which)
        for year in (day.year - 1, day.year)
        for which in ("march", "june", "september", "december")
    )
    current = "december"
    for start, which in starts:
        if start <= day:
            current = which
    north = {
        "march": "spring",
        "june": "summer",
        "september": "autumn",
        "december": "winter",
    }
    south = {
        "march": "autumn",
        "june": "winter",
        "september": "spring",
        "december": "summer",
    }
    return (north if latitude >= 0 else south)[current]


def western_easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    return date(year, month, (h + ell - 7 * m + 114) % 31 + 1)


def orthodox_easter(year: int) -> date:
    """Orthodox Easter Sunday (Julian computus), as a Gregorian date (1900-2099)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    julian = date(year, month, (d + e + 114) % 31 + 1)
    return julian + timedelta(days=13)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth (1-based, or -1 for last) weekday (Monday=0) of a month."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


@cache
def _data() -> dict[str, Any]:
    return load_json("observances.json")


def groups() -> list[dict[str, Any]]:
    """All groups, secular ones first."""
    return _data()["groups"]


def all_observances() -> list[dict[str, Any]]:
    """Every bundled observance (not seasons, school or public holidays)."""
    return _data()["observances"]


def art_names() -> list[str]:
    """Names of the bundled ASCII art pieces."""
    return sorted(_data()["art"])


def art(name: str | None) -> tuple[str, ...]:
    """Return an ASCII art piece's lines (empty if unknown)."""
    return tuple(_data()["art"].get(name or "", ()))


def falls_on(item: dict[str, Any], day: date) -> bool:
    """Whether a bundled observance falls on ``day``."""
    when = item["when"]
    if "fixed" in when:
        fixed = when["fixed"]
        return day.strftime("%m-%d") in ([fixed] if isinstance(fixed, str) else fixed)
    if "nth" in when:
        month, weekday, n = when["nth"]
        return day.month == month and day == nth_weekday(day.year, month, weekday, n)
    if "easter" in when:
        rule = western_easter if when["easter"] == "western" else orthodox_easter
        return day == rule(day.year)
    if when.get("table"):
        return day.isoformat() in _data()["dates"].get(item["id"], ())
    return False


@dataclass(frozen=True, slots=True)
class Theme:
    """Words, clues, art and jokes for a theme."""

    id: str
    name: str
    words: tuple[str, ...]
    clues: dict[str, str] = field(default_factory=dict)
    art: tuple[str, ...] = ()
    jokes: tuple[dict[str, str], ...] = ()
    fact_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Observance:
    """A recognized day."""

    id: str
    group: str
    name: str
    banner: str
    art: tuple[str, ...] = ()
    theme: Theme | None = None
    solemn: bool = False  # no jokes on this day


# Themed jokes only ever come from science days: never jokes about any
# religious or cultural observance (including fun days such as Halloween).
JOKE_GROUPS = frozenset({"science"})


def _theme_from(item: dict[str, Any], theme_id: str, name: str) -> Theme:
    jokes = item.get("jokes") if item.get("group") in JOKE_GROUPS else None
    return Theme(
        theme_id,
        name,
        tuple(item.get("words") or ()),
        dict(item.get("clues") or {}),
        art(item.get("art")),
        tuple(jokes or ()),
        tuple(item.get("fact_sources") or ()),
    )


def theme(theme_id: str) -> Theme | None:
    """Look up a theme: an observance, a season, "school", or a fixed theme."""
    data = _data()
    for item in data["observances"]:
        if item["id"] == theme_id:
            return _theme_from(item, theme_id, item["name"])
    if theme_id in data["seasons"]:
        return _theme_from(data["seasons"][theme_id], theme_id, theme_id.title())
    if theme_id == "school":
        return _theme_from(data["special"]["school"], "school", "School")
    words = load_json("themes.json").get(theme_id)
    if words:
        return Theme(theme_id, theme_id.title(), tuple(w.upper() for w in words))
    return None


def fixed_themes() -> list[str]:
    """Themes that can be chosen to print all the time."""
    return sorted(load_json("themes.json"))


def _season_banner(which: str, latitude: float) -> tuple[str, str, str]:
    season = {
        "march": ("spring", "autumn"),
        "june": ("summer", "winter"),
        "september": ("autumn", "spring"),
        "december": ("winter", "summer"),
    }[which][0 if latitude >= 0 else 1]
    label = {"march": "March equinox", "june": "June solstice"}.get(
        which, f"{which.title()} {'equinox' if which == 'september' else 'solstice'}"
    )
    extra = {
        "spring": "Day and night are about the same length.",
        "autumn": "Day and night are about the same length.",
        "summer": "It's the longest day of the year.",
        "winter": "It's the shortest day of the year.",
    }[season]
    return season, label, f"Today is the {label}, the first day of {season}. {extra}"


def todays(
    day: date,
    *,
    to_local: Any,
    latitude: float,
    secular: set[str] | frozenset[str] = frozenset(SECULAR_DEFAULT),
    picked_groups: set[str] | frozenset[str] = frozenset(),
    excluded: set[str] | frozenset[str] = frozenset(),
    school_day: str | None = None,
    custom: list[dict[str, Any]] | None = None,
    public: list[str] | None = None,
) -> list[Observance]:
    """Days recognized on ``day``, most specific first.

    Order: custom family days, faith and cultural days, fun days, first day
    of school, public holidays, science days, then the season. Days of the
    same rank take turns by date.
    """
    data = _data()
    out: list[Observance] = []
    for item in custom or []:
        if item.get("date") == day.strftime("%m-%d"):
            name = str(item.get("name") or "A special day")
            out.append(
                Observance(
                    f"custom:{item.get('id', name)}",
                    "custom",
                    name,
                    str(item.get("banner") or f"Today is {name}!"),
                    art(item.get("art") or data["special"]["custom"]["art"]),
                )
            )
    secular_groups = {g["id"] for g in data["groups"] if g.get("secular")}
    for item in data["observances"]:
        group = item["group"]
        member_of = [group, *item.get("also_groups", ())]
        on = any(
            g in secular if g in secular_groups else g in picked_groups
            for g in member_of
        )
        if on and item["id"] not in excluded and falls_on(item, day):
            out.append(
                Observance(
                    item["id"],
                    group,
                    item["name"],
                    item["banner"],
                    art(item.get("art")),
                    _theme_from(item, item["id"], item["name"]),
                    bool(item.get("solemn")),
                )
            )
    if "school" in secular and school_day == day.isoformat():
        school = data["special"]["school"]
        out.append(
            Observance(
                "school",
                "school",
                school["name"],
                school["banner"],
                art(school["art"]),
                theme("school"),
            )
        )
    if "public" in secular:
        for name in public or []:
            out.append(
                Observance(
                    f"public:{name}",
                    "public",
                    name,
                    f"Today is {name}.",
                    art(data["special"]["public"]["art"]),
                )
            )
    if "seasons" in secular:
        which = season_starts(day.year, to_local).get(day)
        if which:
            season, label, banner = _season_banner(which, latitude)
            out.append(
                Observance(
                    f"season:{which}",
                    "seasons",
                    label,
                    banner,
                    art(data["seasons"][season]["art"]),
                    theme(season),
                )
            )
    # Faith and cultural days rank together, above fun days; days of the same
    # rank take turns by date, so no tradition always wins a shared day.
    order = {
        "custom": 0,
        "fun": 2,
        "school": 3,
        "public": 4,
        "science": 5,
        "seasons": 6,
    }

    def turn(obs: Observance) -> str:
        return hashlib.sha256(f"{day.isoformat()}|{obs.id}".encode()).hexdigest()

    out.sort(key=lambda o: (order.get(o.group, 1), turn(o)))
    return out
