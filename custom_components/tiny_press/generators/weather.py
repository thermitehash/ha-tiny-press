"""Weather report: current conditions plus up to 10 days of forecast.

Pure: built from a ``weather`` entity's state/attributes and the response of
``weather.get_forecasts``. The same report is reused by the morning slip.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

MAX_DAYS = 10

CONDITIONS = {
    "clear-night": "Clear",
    "cloudy": "Cloudy",
    "exceptional": "Unusual weather",
    "fog": "Foggy",
    "hail": "Hail",
    "lightning": "Thunderstorms",
    "lightning-rainy": "Thunderstorms",
    "partlycloudy": "Partly cloudy",
    "pouring": "Heavy rain",
    "rainy": "Rainy",
    "snowy": "Snowy",
    "snowy-rainy": "Sleet",
    "sunny": "Sunny",
    "windy": "Windy",
    "windy-variant": "Windy",
}


def condition_label(condition: str | None) -> str:
    """Friendly text for a Home Assistant weather condition."""
    if not condition:
        return "Unknown"
    return CONDITIONS.get(condition, condition.replace("-", " ").capitalize())


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except TypeError, ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Day:
    """One forecast day."""

    day: date
    condition: str | None
    high: float | None
    low: float | None
    precip_chance: float | None


@dataclass(frozen=True, slots=True)
class WeatherReport:
    """Everything the weather print shows."""

    place: str
    condition: str | None
    temperature: float | None
    feels_like: float | None
    humidity: float | None
    wind_speed: float | None
    temp_unit: str
    wind_unit: str
    days: tuple[Day, ...]


def build_report(
    place: str,
    attributes: dict[str, Any],
    condition: str | None,
    forecast: list[dict[str, Any]],
    to_local: Any = None,
) -> WeatherReport:
    """Turn entity attributes and forecast rows into a report.

    ``to_local`` converts a forecast datetime to local time (defaults to the
    datetime's own date). Twice-daily rows are merged into one row per day.
    """
    days: dict[date, dict[str, Any]] = {}
    for row in forecast:
        raw = row.get("datetime")
        if not raw:
            continue
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        day = (to_local(when) if to_local else when).date()
        entry = days.setdefault(
            day, {"condition": None, "high": None, "low": None, "precip": None}
        )
        is_night = row.get("is_daytime") is False
        if entry["condition"] is None or not is_night:
            entry["condition"] = row.get("condition") or entry["condition"]
        for key, value, pick in (
            ("high", _num(row.get("temperature")), max),
            ("low", _num(row.get("templow")), min),
            ("precip", _num(row.get("precipitation_probability")), max),
        ):
            if value is not None:
                entry[key] = value if entry[key] is None else pick(entry[key], value)
        if is_night and entry["low"] is None:
            entry["low"] = _num(row.get("temperature"))
    rows = tuple(
        Day(day, d["condition"], d["high"], d["low"], d["precip"])
        for day, d in sorted(days.items())
    )[:MAX_DAYS]
    return WeatherReport(
        place=place,
        condition=condition,
        temperature=_num(attributes.get("temperature")),
        feels_like=_num(attributes.get("apparent_temperature")),
        humidity=_num(attributes.get("humidity")),
        wind_speed=_num(attributes.get("wind_speed")),
        temp_unit=str(attributes.get("temperature_unit") or "°"),
        wind_unit=str(attributes.get("wind_speed_unit") or ""),
        days=rows,
    )
