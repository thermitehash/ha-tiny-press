"""Actions (services) and the print jobs they build."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
import logging
from pathlib import Path
import re
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
import voluptuous as vol

from . import jobs
from .ai import async_ai_joke, async_ai_story
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DIFFICULTY,
    ATTR_PATH,
    ATTR_PROFILE,
    ATTR_SEED,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_TITLE,
    ATTR_TYPE,
    CONF_CALENDARS,
    CONF_MORNING_BOTTOM,
    CONF_PAPER_WIDTH,
    CONF_TODOS,
    CONF_WEATHER,
    DOMAIN,
    EVENT_RATE_LIMITED,
    PAPER_80MM,
    PAPER_DOTS,
    SETTING_MAZE_DIFFICULTY,
    SETTING_MORNING_KID_DAY,
    SETTING_STORY_LENGTH,
    SETTING_SUDOKU_DIFFICULTY,
    TEXT_SIZES,
    Difficulty,
    PrintType,
)
from .coordinator import PrintJob, TinyPressConfigEntry, TinyPressCoordinator
from .generators import history, morning, sudoku as sudoku_gen
from .generators.story import pick_offline
from .generators.weather import WeatherReport, build_report
from .limits import KID_TYPES

_LOGGER = logging.getLogger(__name__)

SERVICE_PRINT = "print"
SERVICE_PREVIEW = "preview"
SERVICE_PRINT_ANSWERS = "print_answers"
ATTR_IGNORE_LIMITS = "ignore_limits"
ATTR_PRINT_ID = "print_id"
ATTR_WORDS = "words"
STORY_LENGTHS = ("short", "medium", "long")
SERVICE_PRINT_TEXT = "print_text"
SERVICE_PRINT_IMAGE = "print_image"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

_DIFFICULTY_WORDS: dict[Difficulty, tuple[str, ...]] = {
    Difficulty.EASY: (
        "easy",
        "easier",
        "easiest",
        "simple",
        "beginner",
        "little",
        "small",
        "baby",
        "gentle",
    ),
    Difficulty.MEDIUM: ("medium", "normal", "regular", "average", "middle", "moderate"),
    Difficulty.HARD: (
        "hard",
        "harder",
        "hardest",
        "tricky",
        "trickier",
        "difficult",
        "challenging",
        "tough",
        "big",
        "expert",
        "super hard",
    ),
}

ENTRY_FIELD = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

PRINT_SCHEMA = vol.Schema(
    {
        **ENTRY_FIELD,
        vol.Required(ATTR_TYPE): vol.In([t.value for t in PrintType]),
        vol.Optional(ATTR_PROFILE): cv.string,
        vol.Optional(ATTR_DIFFICULTY): cv.string,
        vol.Optional(ATTR_SEED): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(ATTR_IGNORE_LIMITS, default=False): cv.boolean,
        vol.Optional(ATTR_WORDS): vol.Any(cv.string, [cv.string]),
    }
)
PREVIEW_SCHEMA = vol.Schema(
    {
        **ENTRY_FIELD,
        vol.Required(ATTR_TYPE): vol.In([t.value for t in PrintType]),
        vol.Optional(ATTR_PROFILE): cv.string,
        vol.Optional(ATTR_DIFFICULTY): cv.string,
        vol.Optional(ATTR_SEED): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(ATTR_WORDS): vol.Any(cv.string, [cv.string]),
    }
)
PRINT_STORY_SCHEMA = vol.Schema(
    {
        **ENTRY_FIELD,
        vol.Optional(ATTR_PROFILE): cv.string,
        vol.Optional("topic"): vol.All(cv.string, vol.Length(max=120)),
        vol.Optional("length"): vol.In(STORY_LENGTHS),
        vol.Optional("mode", default="standalone"): vol.In(("standalone", "serial")),
        vol.Optional(ATTR_IGNORE_LIMITS, default=False): cv.boolean,
    }
)
CONTINUE_STORY_SCHEMA = vol.Schema(
    {
        **ENTRY_FIELD,
        vol.Optional(ATTR_PROFILE): cv.string,
        vol.Optional("choice"): vol.All(vol.Upper, vol.In(("A", "B"))),
        vol.Optional("final", default=False): cv.boolean,
        vol.Optional("length"): vol.In(STORY_LENGTHS),
        vol.Optional(ATTR_IGNORE_LIMITS, default=False): cv.boolean,
    }
)
MORNING_SCHEMA = vol.Schema(
    {**ENTRY_FIELD, vol.Optional("kid_mode", default=False): cv.boolean}
)
HISTORY_SCHEMA = vol.All(
    vol.Schema(
        {
            **ENTRY_FIELD,
            vol.Required("entity_id"): vol.All(
                cv.entity_ids, vol.Length(min=1, max=history.MAX_SERIES)
            ),
            vol.Exclusive("hours", "period"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=24 * 31)
            ),
            vol.Exclusive("days", "period"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=31)
            ),
            vol.Exclusive("start", "period"): cv.datetime,
            vol.Optional("end"): cv.datetime,
            vol.Optional("style", default="graph"): vol.In(("graph", "table", "both")),
            vol.Optional("tall", default=False): cv.boolean,
            vol.Optional("grid", default=False): cv.boolean,
            vol.Optional("title"): vol.All(cv.string, vol.Length(max=60)),
        }
    ),
)
PRINT_ANSWERS_SCHEMA = vol.Schema(
    {**ENTRY_FIELD, vol.Optional(ATTR_PRINT_ID): cv.string}
)
PRINT_TEXT_SCHEMA = vol.Schema(
    {
        **ENTRY_FIELD,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(min=1, max=5000)),
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_SIZE, default="normal"): vol.In(TEXT_SIZES),
    }
)
PRINT_IMAGE_SCHEMA = vol.Schema({**ENTRY_FIELD, vol.Required(ATTR_PATH): cv.string})


def normalize_difficulty(value: str | None, default: Difficulty) -> Difficulty:
    """Map loose words ("harder", "tricky", "a bit easy") to a difficulty."""
    if not value:
        return default
    words = re.sub(r"[^a-z ]", " ", value.lower()).split()
    phrase = " ".join(words)
    for difficulty, options in _DIFFICULTY_WORDS.items():
        if phrase in options:
            return difficulty
    for difficulty in (Difficulty.HARD, Difficulty.EASY, Difficulty.MEDIUM):
        if any(word in _DIFFICULTY_WORDS[difficulty] for word in words):
            return difficulty
    return default


def test_page_info(coordinator: TinyPressCoordinator) -> tuple[str, dict[str, str]]:
    """Paper width and the details printed on the test page."""
    entry = coordinator.config_entry
    paper = entry.data.get(CONF_PAPER_WIDTH, PAPER_80MM)
    return paper, {
        "Printer": f"{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}",
        "Paper": f"{paper} mm, {PAPER_DOTS[paper]} dots",
        "Longest print": f"{coordinator.max_length_mm} mm",
    }


def maze_difficulty(coordinator: TinyPressCoordinator, value: str | None) -> Difficulty:
    """Loose difficulty text, else the Maze difficulty select."""
    default = Difficulty(
        coordinator.store.get_setting(SETTING_MAZE_DIFFICULTY, Difficulty.EASY)
    )
    return normalize_difficulty(value, default)


async def async_build_job(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    kind: PrintType,
    *,
    profile: str | None = None,
    difficulty: str | None = None,
    seed: int | None = None,
    words: list[str] | str | None = None,
) -> PrintJob | Callable[[], PrintJob]:
    """Return the job (or a builder to run in the executor) for one print type."""
    match kind:
        case PrintType.MAZE:
            level = maze_difficulty(coordinator, difficulty)
            return partial(jobs.maze_job, level, seed, profile)
        case PrintType.WORD_SEARCH:
            return partial(jobs.word_search_job, coordinator.kid_profile(profile), seed)
        case PrintType.MATH:
            return partial(jobs.math_job, coordinator.kid_profile(profile), seed)
        case PrintType.JOKE | PrintType.FACT:
            kid = coordinator.kid_profile(profile)
            joke = None
            # Bundled human-written lists unless AI jokes are switched on;
            # a seed asks for a repeatable (bundled) pick.
            if seed is None and coordinator.use_ai_jokes:
                joke = await async_ai_joke(
                    hass, coordinator.ai_task_entity, kind.value, kid
                )
            if joke is None:
                # A seeded pick ignores the rotation so it's repeatable.
                recent = [] if seed is not None else coordinator.store.recent(kind)
                joke = await hass.async_add_executor_job(
                    jobs.offline_joke, kind.value, seed, recent
                )
                if seed is None and joke.index is not None:
                    coordinator.store.remember(kind, joke.index)
            return jobs.joke_job(joke, kid)
        case PrintType.KID_PACK:
            kid = coordinator.kid_profile(profile)
            level = maze_difficulty(coordinator, difficulty)
            return partial(jobs.kid_pack_job, kid, level, seed)
        case PrintType.KID_SUDOKU:
            kid = coordinator.kid_profile(profile)
            level = (
                normalize_difficulty(difficulty, Difficulty.MEDIUM)
                if difficulty
                else None
            )
            return partial(jobs.kid_sudoku_job, kid, level, seed)
        case PrintType.SPELLING | PrintType.SPELLING_SEARCH:
            kid = coordinator.kid_profile(profile)
            todo_words = None
            if not words and kid.spelling_todo:
                todo_words = await async_todo_words(hass, kid.spelling_todo, kid.name)
            try:
                found = jobs.spelling_words_for(kid, words, todo_words)
            except ValueError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_spelling_words",
                    translation_placeholders={"profile": kid.name},
                ) from err
            build = (
                jobs.spelling_job
                if kind is PrintType.SPELLING
                else jobs.spelling_search_job
            )
            return partial(build, kid, found, seed)
        case (
            PrintType.SUDOKU
            | PrintType.CROSSWORD
            | PrintType.CRYPTOGRAM
            | PrintType.PUZZLE_PACK
        ):
            adult = coordinator.adult_profile(profile)
            base = Difficulty(adult.difficulty)
            level = normalize_difficulty(difficulty, base)
            sudoku_level = (
                level
                if difficulty
                else Difficulty(
                    coordinator.store.get_setting(SETTING_SUDOKU_DIFFICULTY, base)
                )
            )
            recent = [] if seed is not None else coordinator.store.recent("cryptogram")
            match kind:
                case PrintType.SUDOKU:
                    return partial(jobs.sudoku_job, sudoku_level, seed, adult.name)
                case PrintType.CROSSWORD:
                    return partial(jobs.crossword_job, level, seed, adult.name)
                case PrintType.CRYPTOGRAM:
                    return partial(jobs.cryptogram_job, level, seed, adult.name, recent)
                case _:
                    return partial(
                        jobs.puzzle_pack_job,
                        level,
                        sudoku_level,
                        seed,
                        adult.name,
                        recent,
                    )
        case PrintType.MORNING_SLIP:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="morning_preview"
            )
        case PrintType.STORY:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="story_preview"
            )
        case PrintType.WEATHER:
            return jobs.weather_job(await async_weather_report(hass, coordinator))
        case _:
            paper, info = test_page_info(coordinator)
            return jobs.test_page_job(paper, info)


def weather_entity(hass: HomeAssistant, coordinator: TinyPressCoordinator) -> str:
    """Return the weather entity from the options, or the only one there is."""
    chosen = coordinator.config_entry.options.get(CONF_WEATHER)
    if chosen and hass.states.get(chosen):
        return chosen
    found = hass.states.async_entity_ids("weather")
    if not chosen and len(found) == 1:
        return found[0]
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="weather_not_set"
    )


async def async_weather_report(
    hass: HomeAssistant, coordinator: TinyPressCoordinator
) -> WeatherReport:
    """Read the weather entity and ask it for a daily (or twice-daily) forecast."""
    entity_id = weather_entity(hass, coordinator)
    state = hass.states.get(entity_id)
    assert state is not None
    forecast: list[dict[str, Any]] = []
    for kind in ("daily", "twice_daily"):
        try:
            response = await hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": kind},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("No %s forecast from %s: %s", kind, entity_id, err)
            continue
        forecast = ((response or {}).get(entity_id) or {}).get("forecast") or []
        if forecast:
            break
    return build_report(
        str(state.attributes.get("friendly_name") or entity_id),
        dict(state.attributes),
        state.state if state.state not in ("unknown", "unavailable") else None,
        forecast,
        to_local=dt_util.as_local,
    )


async def async_todo_words(
    hass: HomeAssistant, entity_id: str, name: str
) -> list[str] | None:
    """Words still to learn from a to-do list (unchecked items).

    Checked-off items count as learned. Returns None if the list can't be
    read (the typed list is used instead); raises if every word is learned.
    """
    try:
        response = await hass.services.async_call(
            "todo",
            "get_items",
            {"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
    except HomeAssistantError as err:
        _LOGGER.info("Can't read spelling list %s: %s", entity_id, err)
        return None
    items = ((response or {}).get(entity_id) or {}).get("items") or []
    todo = [i.get("summary", "") for i in items if i.get("status") != "completed"]
    if items and not todo:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="all_words_learned",
            translation_placeholders={"profile": name},
        )
    return todo


def check_limits(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    kind: PrintType,
    profile: str | None,
) -> None:
    """Raise if kid-mode limits block this print (and fire an event)."""
    status = coordinator.limiter.status()
    if status.next_print_at is None:
        return
    hass.bus.async_fire(
        EVENT_RATE_LIMITED,
        {
            "type": kind.value,
            "profile": profile,
            "reason": status.reason,
            "next_print_at": status.next_print_at.isoformat(),
        },
    )
    when = dt_util.as_local(status.next_print_at)
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=f"rate_limited_{status.reason}",
        translation_placeholders={"time": when.strftime("%-I:%M %p")},
    )


STORY_NOTIFICATION = f"{DOMAIN}_story_fallback"


def _story_fallback_notice(hass: HomeAssistant, reason: str, serial: bool) -> None:
    """Explain (in a notification, never on paper) why a bundled story printed."""
    why = (
        "No AI task entity is set (Configure → Settings)"
        if reason == "not_set"
        else "The AI task entity didn't return a usable story"
    )
    extra = (
        " Choose-your-own-adventure chapters need the AI, so tonight's chapter "
        "will wait; the story in progress is kept."
        if serial
        else ""
    )
    persistent_notification.async_create(
        hass,
        f"{why}, so Tiny Press printed one of its bundled stories instead.{extra}",
        title="Tiny Press bedtime story",
        notification_id=STORY_NOTIFICATION,
    )


async def async_story(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    *,
    profile: str | None = None,
    topic: str | None = None,
    length: str | None = None,
    mode: str = "standalone",
    continuing: bool = False,
    choice: str | None = None,
    final: bool = False,
    ignore_limits: bool = False,
) -> dict[str, Any]:
    """Print a bedtime story, start a serial, or continue one."""
    kid = coordinator.kid_profile(profile)
    length = length or coordinator.store.get_setting(SETTING_STORY_LENGTH, "medium")
    limited = not ignore_limits and coordinator.limiter.enabled
    if limited:
        check_limits(hass, coordinator, PrintType.STORY, profile)
    series = coordinator.store.series(kid.id) if continuing else None
    if continuing and series is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_story_in_progress",
            translation_placeholders={"profile": kid.name},
        )
    serial = continuing or mode == "serial"
    story = None
    reason = "not_set"
    if coordinator.ai_task_entity:
        reason = "failed"
        story = await async_ai_story(
            hass,
            coordinator.ai_task_entity,
            kid,
            topic=topic or (series or {}).get("topic"),
            length=length,
            series=series,
            choice=choice,
            final=final,
            start_serial=serial and not continuing,
        )
    if story is None:
        story = await hass.async_add_executor_job(
            pick_offline, length, jobs.new_seed(), coordinator.store.recent("story")
        )
        coordinator.store.remember("story", story.title)
        _story_fallback_notice(hass, reason, serial)
    elif story.chapter:
        if final or not story.choices:
            coordinator.store.set_series(kid.id, None)
        else:
            history = [
                *(series or {}).get("history", []),
                *([choice] if choice else []),
            ]
            coordinator.store.set_series(
                kid.id,
                {
                    "title": (series or {}).get("title") or story.title,
                    "topic": topic or (series or {}).get("topic"),
                    "summary": story.summary,
                    "chapter": story.chapter,
                    "choices": dict(zip("AB", story.choices, strict=True)),
                    "history": history[-2:],
                },
            )
    response = await coordinator.async_print(jobs.story_job(story, kid, length))
    if limited:
        coordinator.limiter.record(response["length_mm"])
        coordinator.async_update_listeners()
    return response


async def async_morning_slip(
    hass: HomeAssistant, coordinator: TinyPressCoordinator, *, kid_mode: bool = False
) -> dict[str, Any]:
    """Print the morning slip. Never counts toward kid limits; once a day from kid mode."""
    today = dt_util.now().date()
    if (
        kid_mode
        and coordinator.store.get_setting(SETTING_MORNING_KID_DAY) == today.isoformat()
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="morning_once_a_day"
        )
    options = coordinator.config_entry.options
    try:
        weather = await async_weather_report(hass, coordinator)
    except ServiceValidationError:
        weather = None  # no weather entity: the slip just skips the weather

    calendars = [c for c in options.get(CONF_CALENDARS) or [] if hass.states.get(c)]
    raw_events: dict[str, list[dict[str, Any]]] = {}
    if calendars:
        start, end = morning.day_bounds(today, dt_util.get_default_time_zone())
        try:
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendars,
                    "start_date_time": start.isoformat(),
                    "end_date_time": end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
            raw_events = {
                entity: (data or {}).get("events") or []
                for entity, data in (response or {}).items()
            }
        except HomeAssistantError as err:
            _LOGGER.info("Couldn't read calendars for the morning slip: %s", err)
    events, more = morning.build_events(raw_events, today, dt_util.as_local)

    raw_todos: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for entity in options.get(CONF_TODOS) or []:
        state = hass.states.get(entity)
        if state is None:
            continue
        try:
            response = await hass.services.async_call(
                "todo",
                "get_items",
                {"entity_id": entity},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            _LOGGER.info("Couldn't read %s for the morning slip: %s", entity, err)
            continue
        items = ((response or {}).get(entity) or {}).get("items") or []
        raw_todos[entity] = (
            str(state.attributes.get("friendly_name") or entity),
            items,
        )

    bottom = options.get(CONF_MORNING_BOTTOM, "joke")
    joke = None
    puzzle = None
    quote = None
    word = None
    if bottom in ("joke", "fact"):
        kind = PrintType.JOKE if bottom == "joke" else PrintType.FACT
        kid = coordinator.kid_profile()
        if coordinator.use_ai_jokes:
            joke = await async_ai_joke(
                hass, coordinator.ai_task_entity, kind.value, kid
            )
        if joke is None:
            joke = await hass.async_add_executor_job(
                jobs.offline_joke, kind.value, None, coordinator.store.recent(kind)
            )
            if joke.index is not None:
                coordinator.store.remember(kind, joke.index)
    elif bottom in ("quote", "word"):
        pick = morning.pick_quote if bottom == "quote" else morning.pick_word
        picked = await hass.async_add_executor_job(
            pick, jobs.new_seed(), coordinator.store.recent(bottom)
        )
        if picked.index is not None:
            coordinator.store.remember(bottom, picked.index)
        if bottom == "quote":
            quote = picked
        else:
            word = picked
    elif bottom == "puzzle":
        level = coordinator.adult_profile().difficulty
        puzzle = await hass.async_add_executor_job(
            sudoku_gen.generate, 6, level, jobs.new_seed()
        )
    slip = morning.MorningSlip(
        day=today,
        weather=weather,
        events=events,
        more_events=more,
        todos=morning.build_todos(raw_todos),
        joke=joke,
        puzzle=puzzle,
        quote=quote,
        word=word,
        calendars_set=bool(calendars),
    )
    response = await coordinator.async_print(jobs.morning_job(slip))
    if kid_mode:
        coordinator.store.set_setting(SETTING_MORNING_KID_DAY, today.isoformat())
    return response


STATS_AFTER = timedelta(days=3)  # longer periods use hourly long-term statistics


def _fetch_states(
    hass: HomeAssistant, start: datetime, end: datetime, entity_ids: list[str]
) -> dict[str, list[Any]]:
    from homeassistant.components.recorder import (  # noqa: PLC0415
        history as rec_history,
    )

    return rec_history.get_significant_states(
        hass,
        start,
        end,
        entity_ids,
        include_start_time_state=True,
        significant_changes_only=False,
        no_attributes=True,
    )


def _fetch_stats(
    hass: HomeAssistant, start: datetime, end: datetime, entity_ids: list[str]
) -> dict[str, list[Any]]:
    from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
        statistics_during_period,
    )

    return statistics_during_period(
        hass, start, end, set(entity_ids), "hour", None, {"mean", "min", "max"}
    )


async def async_print_history(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    entity_ids: list[str],
    *,
    start: datetime,
    end: datetime,
    style: str = "graph",
    tall: bool = False,
    grid: bool = False,
    title: str | None = None,
) -> dict[str, Any]:
    """Print one to three entities' history (not a kid print: never limited)."""
    if "recorder" not in hass.config.components:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="history_unavailable"
        )
    from homeassistant.components.recorder import get_instance  # noqa: PLC0415

    recorder = get_instance(hass)
    raw = await recorder.async_add_executor_job(
        _fetch_states, hass, start, end, entity_ids
    )
    stats: dict[str, list[Any]] = {}
    if end - start > STATS_AFTER:
        stats = await recorder.async_add_executor_job(
            _fetch_stats, hass, start, end, entity_ids
        )
    series = []
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        name = (
            str(state.attributes.get("friendly_name") or entity_id)
            if state
            else entity_id
        )
        unit = str(state.attributes.get("unit_of_measurement") or "") if state else ""
        rows = [
            (max(s.last_changed, start), s.state)
            for s in raw.get(entity_id, [])
            if hasattr(s, "state")
        ]
        known = [r for r in rows if r[1].lower() not in history.UNAVAILABLE]
        numeric = bool(known) and sum(
            history.to_float(v) is not None for _t, v in known
        ) >= 0.8 * len(known)
        if numeric and stats.get(entity_id):
            series.append(history.stats_series(entity_id, name, unit, stats[entity_id]))
        elif numeric:
            series.append(history.numeric_series(entity_id, name, unit, rows))
        elif known:
            series.append(history.state_series(entity_id, name, rows, end, start))
        else:
            series.append(history.Series(entity_id, name, unit))
    names = ", ".join(s.name for s in series)
    report = history.HistoryReport(
        title=title or (names if len(names) <= 40 else "Sensor history"),
        start=start,
        end=end,
        series=tuple(series),
        style=style,
        tall=tall,
        grid=grid,
    )
    return await coordinator.async_print(jobs.history_job(report))


async def async_print_type(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    kind: PrintType,
    *,
    profile: str | None = None,
    difficulty: str | None = None,
    seed: int | None = None,
    ignore_limits: bool = False,
    words: list[str] | str | None = None,
) -> dict[str, Any]:
    """Print one type. Shared by the ``print`` action and the buttons."""
    if kind is PrintType.MORNING_SLIP:
        return await async_morning_slip(hass, coordinator)
    if kind is PrintType.STORY:
        return await async_story(
            hass, coordinator, profile=profile, ignore_limits=ignore_limits
        )
    limited = kind in KID_TYPES and not ignore_limits and coordinator.limiter.enabled
    if limited:
        check_limits(hass, coordinator, kind, profile)
    job = await async_build_job(
        hass,
        coordinator,
        kind,
        profile=profile,
        difficulty=difficulty,
        seed=seed,
        words=words,
    )
    response = await coordinator.async_print(job)
    if seed is None and response.get("quote_index") is not None:
        coordinator.store.remember("cryptogram", response["quote_index"])
    if limited:
        coordinator.limiter.record(response["length_mm"])
        coordinator.async_update_listeners()
    return response


async def async_preview_type(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    kind: PrintType,
    *,
    profile: str | None = None,
    difficulty: str | None = None,
    seed: int | None = None,
    words: list[str] | str | None = None,
) -> dict[str, Any]:
    """Render a print without printing it. Pass the returned seed to ``print``."""
    seed = jobs.new_seed() if seed is None else seed
    job = await async_build_job(
        hass,
        coordinator,
        kind,
        profile=profile,
        difficulty=difficulty,
        seed=seed,
        words=words,
    )
    return {**await coordinator.async_preview(job), "seed": seed}


async def _is_admin(hass: HomeAssistant, call: ServiceCall) -> bool:
    if not call.context.user_id:
        return False
    user = await hass.auth.async_get_user(call.context.user_id)
    return bool(user and user.is_admin)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> TinyPressCoordinator:
    entries: list[TinyPressConfigEntry] = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_found"
            )
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="choose_printer"
        )
    return entries[0].runtime_data


def resolve_image_path(hass: HomeAssistant, raw: str) -> Path:
    """Allow only files under /media (media dirs) or /config/www."""
    path = Path(raw)
    if not path.is_absolute():
        path = Path(hass.config.path(raw))
    path = path.resolve()
    roots = [Path(hass.config.path("www")).resolve()]
    roots += [Path(p).resolve() for p in hass.config.media_dirs.values()]
    if not any(path.is_relative_to(root) for root in roots) or (
        not hass.config.is_allowed_path(str(path))
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="path_not_allowed",
            translation_placeholders={"path": raw},
        )
    if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="image_not_found",
            translation_placeholders={"path": raw},
        )
    return path


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all actions."""

    async def handle_print(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        ignore = bool(call.data.get(ATTR_IGNORE_LIMITS)) or (
            coordinator.limiter.admins_skip and await _is_admin(hass, call)
        )
        return await async_print_type(
            hass,
            coordinator,
            PrintType(call.data[ATTR_TYPE]),
            profile=call.data.get(ATTR_PROFILE),
            difficulty=call.data.get(ATTR_DIFFICULTY),
            seed=call.data.get(ATTR_SEED),
            ignore_limits=ignore,
            words=call.data.get(ATTR_WORDS),
        )

    async def handle_preview(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        return await async_preview_type(
            hass,
            coordinator,
            PrintType(call.data[ATTR_TYPE]),
            profile=call.data.get(ATTR_PROFILE),
            difficulty=call.data.get(ATTR_DIFFICULTY),
            seed=call.data.get(ATTR_SEED),
            words=call.data.get(ATTR_WORDS),
        )

    async def _ignore(call: ServiceCall, coordinator: TinyPressCoordinator) -> bool:
        return bool(call.data.get(ATTR_IGNORE_LIMITS)) or (
            coordinator.limiter.admins_skip and await _is_admin(hass, call)
        )

    async def handle_print_story(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        return await async_story(
            hass,
            coordinator,
            profile=call.data.get(ATTR_PROFILE),
            topic=call.data.get("topic"),
            length=call.data.get("length"),
            mode=call.data["mode"],
            ignore_limits=await _ignore(call, coordinator),
        )

    async def handle_continue_story(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        return await async_story(
            hass,
            coordinator,
            profile=call.data.get(ATTR_PROFILE),
            length=call.data.get("length"),
            continuing=True,
            choice=call.data.get("choice"),
            final=call.data["final"],
            ignore_limits=await _ignore(call, coordinator),
        )

    async def handle_morning(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        return await async_morning_slip(
            hass, coordinator, kid_mode=call.data["kid_mode"]
        )

    async def handle_history(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        now = dt_util.utcnow()
        end = call.data.get("end")
        end = (
            dt_util.as_utc(dt_util.as_local(end) if end.tzinfo is None else end)
            if end
            else now
        )
        start = call.data.get("start")
        if start is not None:
            start = dt_util.as_utc(
                dt_util.as_local(start) if start.tzinfo is None else start
            )
        elif "days" in call.data:
            start = end - timedelta(days=call.data["days"])
        else:
            start = end - timedelta(hours=call.data.get("hours", 24))
        if start >= end:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="history_bad_period"
            )
        return await async_print_history(
            hass,
            coordinator,
            call.data["entity_id"],
            start=start,
            end=end,
            style=call.data["style"],
            tall=call.data["tall"],
            grid=call.data["grid"],
            title=call.data.get("title"),
        )

    async def handle_print_answers(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        entry = coordinator.store.find_answer(call.data.get(ATTR_PRINT_ID))
        if entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_answers",
                translation_placeholders={
                    "print_id": call.data.get(ATTR_PRINT_ID) or "-"
                },
            )
        return await coordinator.async_print(partial(jobs.answer_job, entry))

    async def handle_print_text(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        job = jobs.text_job(
            call.data[ATTR_TEXT], call.data.get(ATTR_TITLE), call.data[ATTR_SIZE]
        )
        return await coordinator.async_print(job)

    async def handle_print_image(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        path = await hass.async_add_executor_job(
            resolve_image_path, hass, call.data[ATTR_PATH]
        )
        return await coordinator.async_print(jobs.image_job(path))

    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIEW,
        handle_preview,
        schema=PREVIEW_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    for name, handler, schema in (
        (SERVICE_PRINT, handle_print, PRINT_SCHEMA),
        (SERVICE_PRINT_ANSWERS, handle_print_answers, PRINT_ANSWERS_SCHEMA),
        ("print_story", handle_print_story, PRINT_STORY_SCHEMA),
        ("continue_story", handle_continue_story, CONTINUE_STORY_SCHEMA),
        ("print_morning_slip", handle_morning, MORNING_SCHEMA),
        ("print_history", handle_history, HISTORY_SCHEMA),
        (SERVICE_PRINT_TEXT, handle_print_text, PRINT_TEXT_SCHEMA),
        (SERVICE_PRINT_IMAGE, handle_print_image, PRINT_IMAGE_SCHEMA),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
