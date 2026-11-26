"""Fill the moving-date table in data/observances.json.

Run by a developer (not at runtime) when the table needs more years:

    pip install holidays
    python script/build_observances.py

Dates come from the python-holidays library's calendars (MIT license).
Islamic dates follow its calculated (Umm al-Qura based) calendar and can
differ by a day where the moon is sighted locally; Vesak follows Indonesia's
date (it varies by country). Holidays that start at sundown are listed on
their first full day.
"""

from __future__ import annotations

import json
from pathlib import Path

import holidays
from holidays.calendars import _IslamicLunar

FIRST, LAST = 2026, 2036
DATA = Path(__file__).resolve().parent.parent / (
    "custom_components/tiny_press/data/observances.json"
)

# observance id -> (country, holiday name, exact match?)
COUNTRY = {
    "lunar_new_year": ("CN", "Chinese New Year (Spring Festival)"),
    "mid_autumn": ("CN", "Mid-Autumn Festival"),
    "chuseok": ("KR", "Chuseok"),
    "rosh_hashanah": ("IL", "Rosh Hashanah"),
    "yom_kippur": ("IL", "Yom Kippur"),
    "sukkot": ("IL", "Sukkot"),
    "hanukkah": ("IL", "Hanukkah"),
    "purim": ("IL", "Purim"),
    "passover": ("IL", "Pesach"),
    "makar_sankranti": ("IN", "Makar Sankranti"),
    "holi": ("IN", "Holi"),
    "dussehra": ("IN", "Dussehra"),
    "diwali": ("IN", "Diwali"),
    "onam": ("IN", "Onam"),
    "vaisakhi": ("IN", "Vaisakhi"),
    "guru_nanak": ("IN", "Guru Nanak"),
    "losar": ("BT", "Losar"),
    "vesak": ("ID", "Vesak Day"),
    "nowruz": ("IR", "Nowruz"),
}
ISLAMIC = {
    "ramadan_start": "ramadan_beginning_dates",
    "eid_al_fitr": "eid_al_fitr_dates",
    "eid_al_adha": "eid_al_adha_dates",
}


def _matches(label: str, name: str) -> bool:
    """The holiday itself: "Diwali (Deepavali)" or "Guru Nanak's Jayanti", but
    not "Holika Dahan", "Dussehra (Saptami)", eves or observed days."""
    if label == name:
        return True
    if any(word in label for word in ("observed", "Eve", "holiday")):
        return False
    rest = label[len(name) :]
    return label.startswith(name) and (
        rest.startswith("'s") or (rest.startswith(" (") and name not in EXACT)
    )


EXACT = {"Dussehra"}


def _country_dates(country: str, name: str) -> list[str]:
    cls = holidays.country_holidays(country)
    found = []
    for year in range(FIRST, LAST + 1):
        table = holidays.country_holidays(
            country,
            years=year,
            categories=cls.supported_categories,
            language="en_US",
        )
        days = sorted(
            day
            for day, label in table.items()
            if any(_matches(part.strip(), name) for part in label.split(";"))
        )
        if days:
            found.append(days[0].isoformat())  # the first day only
    return found


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    dates: dict[str, list[str]] = {}
    for key, (country, name) in COUNTRY.items():
        dates[key] = _country_dates(country, name)
    islamic = _IslamicLunar()
    for key, method in ISLAMIC.items():
        out = []
        for year in range(FIRST, LAST + 1):
            for day, _estimated in getattr(islamic, method)(year):
                if FIRST <= day.year <= LAST:
                    out.append(day.isoformat())
        dates[key] = sorted(set(out))
    wanted = {o["id"] for o in data["observances"] if o["when"].get("table")}
    missing = wanted - set(dates)
    if missing:
        raise SystemExit(f"no date source for: {sorted(missing)}")
    data["dates"] = {key: dates[key] for key in sorted(wanted)}
    DATA.write_text(
        json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for key in sorted(wanted):
        print(key, len(dates[key]), dates[key][:2])


if __name__ == "__main__":
    main()
