"""Actions (services) and the print jobs they build."""

from __future__ import annotations

from pathlib import Path
import random
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
from homeassistant.util import dt as dt_util
import voluptuous as vol

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
    TEXT_SIZES,
    Difficulty,
    PrintType,
)
from .coordinator import PrintJob, TinyPressConfigEntry, TinyPressCoordinator
from .generators import maze
from .printer import escpos
from .render import layout

SERVICE_PRINT = "print"
SERVICE_PRINT_TEXT = "print_text"
SERVICE_PRINT_IMAGE = "print_image"

SETTING_MAZE_DIFFICULTY = "maze_difficulty"
REPO_URL = "https://github.com/thermitehash/ha-tiny-press"
QR_MM = 32.0  # approximate paper used by the test page's native QR code
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


def _today() -> Any:
    return dt_util.now().date()


def maze_job(
    coordinator: TinyPressCoordinator,
    difficulty: Difficulty,
    seed: int | None = None,
    profile: str | None = None,
) -> PrintJob:
    """Build a maze print."""
    seed = random.SystemRandom().randrange(2**31) if seed is None else seed
    print_id = layout.make_print_id(random.Random(f"maze-{seed}"))
    puzzle = maze.generate(difficulty, seed)
    footer = layout.Footer("Maze", print_id, _today(), difficulty)
    answer = {**puzzle.answer(), "seed": seed, "difficulty": difficulty.value}
    return PrintJob(
        type=PrintType.MAZE,
        label="Maze",
        print_id=print_id,
        difficulty=difficulty.value,
        profile=profile,
        answer=answer,
        build=lambda width: layout.maze_page(width, puzzle, footer),
    )


def test_page_job(coordinator: TinyPressCoordinator) -> PrintJob:
    """The test page: fonts, dither ramp, settings and a native QR code."""
    entry = coordinator.config_entry
    paper = entry.data.get(CONF_PAPER_WIDTH, PAPER_80MM)
    info = {
        "Printer": f"{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}",
        "Paper": f"{paper} mm, {PAPER_DOTS[paper]} dots",
        "Longest print": f"{coordinator.max_length_mm} mm",
    }
    return test_page_print(paper, info)


def test_page_print(paper: str, info: dict[str, str]) -> PrintJob:
    """Build the test page job (also used by the config flow)."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Test page", print_id, _today())
    return PrintJob(
        type=PrintType.TEST_PAGE,
        label="Test page",
        print_id=print_id,
        build=lambda width: layout.test_page(width, info, footer),
        extra=escpos.align("center")
        + escpos.qr_code(REPO_URL, module=5 if paper == PAPER_80MM else 4)
        + escpos.feed(1)
        + escpos.align("left"),
        extra_mm=QR_MM,
    )


def text_job(text: str, title: str | None, size: str) -> PrintJob:
    """Free text."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Note", print_id, _today())
    return PrintJob(
        type="text",
        label="Note",
        print_id=print_id,
        build=lambda width: layout.text_page(width, text, title, size, footer),
    )


def image_job(path: Path) -> PrintJob:
    """Build a picture print from /media or /config/www."""
    print_id = layout.make_print_id()
    footer = layout.Footer("Picture", print_id, _today())
    return PrintJob(
        type="image",
        label="Picture",
        print_id=print_id,
        build=lambda width: layout.image_page(width, path, footer),
    )


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
        kind = PrintType(call.data[ATTR_TYPE])
        profile = call.data.get(ATTR_PROFILE)
        if kind is PrintType.MAZE:
            default = Difficulty(
                coordinator.store.get_setting(SETTING_MAZE_DIFFICULTY, Difficulty.EASY)
            )
            difficulty = normalize_difficulty(call.data.get(ATTR_DIFFICULTY), default)
            job = maze_job(coordinator, difficulty, call.data.get(ATTR_SEED), profile)
        else:
            job = test_page_job(coordinator)
        return await coordinator.async_print(job)

    async def handle_print_text(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        job = text_job(
            call.data[ATTR_TEXT], call.data.get(ATTR_TITLE), call.data[ATTR_SIZE]
        )
        return await coordinator.async_print(job)

    async def handle_print_image(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        path = await hass.async_add_executor_job(
            resolve_image_path, hass, call.data[ATTR_PATH]
        )
        return await coordinator.async_print(image_job(path))

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
