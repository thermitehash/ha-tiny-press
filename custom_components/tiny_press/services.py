"""Actions (services) and the print jobs they build."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
import logging
from pathlib import Path
import re
from typing import Any

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
from .ai import async_ai_joke
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
    CONF_PAPER_WIDTH,
    CONF_WEATHER,
    DOMAIN,
    EVENT_RATE_LIMITED,
    PAPER_80MM,
    PAPER_DOTS,
    SETTING_MAZE_DIFFICULTY,
    SETTING_SUDOKU_DIFFICULTY,
    TEXT_SIZES,
    Difficulty,
    PrintType,
)
from .coordinator import PrintJob, TinyPressConfigEntry, TinyPressCoordinator
from .generators.weather import WeatherReport, build_report
from .limits import KID_TYPES

_LOGGER = logging.getLogger(__name__)

SERVICE_PRINT = "print"
SERVICE_PREVIEW = "preview"
SERVICE_PRINT_ANSWERS = "print_answers"
ATTR_IGNORE_LIMITS = "ignore_limits"
ATTR_PRINT_ID = "print_id"
ATTR_WORDS = "words"
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
