"""Actions (services) and the print jobs they build."""

from __future__ import annotations

from functools import partial
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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
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
    DOMAIN,
    PAPER_80MM,
    PAPER_DOTS,
    SETTING_MAZE_DIFFICULTY,
    TEXT_SIZES,
    Difficulty,
    PrintType,
)
from .coordinator import TinyPressConfigEntry, TinyPressCoordinator

SERVICE_PRINT = "print"
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
    }
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


async def async_print_type(
    hass: HomeAssistant,
    coordinator: TinyPressCoordinator,
    kind: PrintType,
    *,
    profile: str | None = None,
    difficulty: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Print one type. Shared by the ``print`` action and the buttons."""
    match kind:
        case PrintType.MAZE:
            level = maze_difficulty(coordinator, difficulty)
            return await coordinator.async_print(
                partial(jobs.maze_job, level, seed, profile)
            )
        case PrintType.WORD_SEARCH:
            kid = coordinator.kid_profile(profile)
            return await coordinator.async_print(
                partial(jobs.word_search_job, kid, seed)
            )
        case PrintType.MATH:
            kid = coordinator.kid_profile(profile)
            return await coordinator.async_print(partial(jobs.math_job, kid, seed))
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
            return await coordinator.async_print(jobs.joke_job(joke, kid))
        case PrintType.KID_PACK:
            kid = coordinator.kid_profile(profile)
            level = maze_difficulty(coordinator, difficulty)
            return await coordinator.async_print(
                partial(jobs.kid_pack_job, kid, level, seed)
            )
        case _:
            paper, info = test_page_info(coordinator)
            return await coordinator.async_print(jobs.test_page_job(paper, info))


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
        return await async_print_type(
            hass,
            coordinator,
            PrintType(call.data[ATTR_TYPE]),
            profile=call.data.get(ATTR_PROFILE),
            difficulty=call.data.get(ATTR_DIFFICULTY),
            seed=call.data.get(ATTR_SEED),
        )

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

    for name, handler, schema in (
        (SERVICE_PRINT, handle_print, PRINT_SCHEMA),
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
