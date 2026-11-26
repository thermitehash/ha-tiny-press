"""Status polling and the print pipeline."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import io
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from PIL import Image

from .const import (
    CONF_AI_JOKES,
    CONF_AI_TASK,
    CONF_MAX_LENGTH_MM,
    CONF_PAPER_WIDTH,
    CONF_POLL_INTERVAL,
    DEFAULT_MAX_LENGTH_MM,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    DOTS_PER_MM,
    EVENT_PRINTED,
    FEED_MM,
    OFFLINE_REPAIR_AFTER_HOURS,
    PAPER_80MM,
    PAPER_DOTS,
    SETTING_ADULT_PROFILE,
    SETTING_KID_PROFILE,
    PaperState,
)
from .limits import RateLimiter
from .printer import escpos
from .printer.escpos import PrinterStatus
from .printer.queue import PrintQueue
from .printer.transport import PrinterError, PrinterTransport
from .profiles import ADULT, KID, Profile, find_profile
from .render.canvas import Canvas
from .repairs import async_clear_offline_issue, async_raise_offline_issue
from .store import TinyPressStore

_LOGGER = logging.getLogger(__name__)

type TinyPressConfigEntry = ConfigEntry[TinyPressCoordinator]


@dataclass(frozen=True, slots=True)
class PrinterState:
    """What the entities show."""

    online: bool
    status: PrinterStatus | None = None

    @property
    def paper(self) -> PaperState:
        """Collapse the status bits into one paper state."""
        if not self.online or self.status is None:
            return PaperState.OFFLINE
        if self.status.cover_open:
            return PaperState.COVER_OPEN
        if self.status.paper_out:
            return PaperState.OUT
        if not self.status.online:
            return PaperState.OFFLINE
        if self.status.paper_near_end:
            return PaperState.NEAR_END
        return PaperState.OK


@dataclass(frozen=True, slots=True)
class PrintJob:
    """A print to make: how to draw it, plus metadata."""

    type: str
    label: str
    print_id: str
    build: Callable[[int], Canvas]
    difficulty: str | None = None
    profile: str | None = None
    # Answer keys: {"print_id", "type", "answer"} per puzzle on the page.
    answers: tuple[dict[str, Any], ...] = ()
    response: dict[str, Any] = field(default_factory=dict)  # extra response data
    extra: bytes = b""  # native ESC/POS appended after the raster (e.g. a QR)
    extra_mm: float = 0.0
    # Optional: the page as sections, each followed by native ESC/POS (a QR
    # code per feed item). Used instead of ``build`` when set.
    sections: Callable[[int], list[Section]] | None = None


@dataclass(frozen=True, slots=True)
class Section:
    """Part of a page, then native bytes (and the paper they use)."""

    canvas: Canvas
    extra: bytes = b""
    extra_mm: float = 0.0


def _stack(images: list[Image.Image], width: int) -> Image.Image:
    """One image from parts, top to bottom (for previews)."""
    if len(images) == 1:
        return images[0]
    out = Image.new("1", (width, max(1, sum(i.height for i in images))), 1)
    y = 0
    for image in images:
        out.paste(image, (0, y))
        y += image.height
    return out


def render_job(
    job: PrintJob, width: int, max_dots: int
) -> tuple[list[tuple[Image.Image, bytes]], int, float, bool]:
    """Render a job's raster parts within the length cap.

    Returns ([(image, native bytes after it)], raster height, extra mm,
    truncated).
    """
    if job.sections is None:
        image, truncated = job.build(width).render(max_dots)
        return [(image, job.extra)], image.height, job.extra_mm, truncated
    parts: list[tuple[Image.Image, bytes]] = []
    height = 0
    extra_mm = 0.0
    budget = max_dots
    truncated = False
    for section in job.sections(width):
        if budget <= 0:
            truncated = True
            break
        image, cut = section.canvas.render(budget)
        budget -= image.height
        height += image.height
        extra = section.extra
        if cut or budget < section.extra_mm * DOTS_PER_MM:
            extra = b""  # no room for the QR: stop here
            truncated = truncated or cut or bool(section.extra)
        parts.append((image, extra))
        if extra:
            budget -= int(section.extra_mm * DOTS_PER_MM)
            extra_mm += section.extra_mm
        if truncated:
            break
    return parts, height, extra_mm, truncated


class TinyPressCoordinator(DataUpdateCoordinator[PrinterState]):
    """Polls DLE EOT status and owns the print queue."""

    config_entry: TinyPressConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: TinyPressConfigEntry, store: TinyPressStore
    ) -> None:
        """Set up from the config entry."""
        interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.store = store
        self.queue = PrintQueue(
            PrinterTransport(entry.data[CONF_HOST], entry.data[CONF_PORT])
        )

    @property
    def width(self) -> int:
        """Printable width in dots."""
        return PAPER_DOTS[self.config_entry.data.get(CONF_PAPER_WIDTH, PAPER_80MM)]

    @property
    def max_length_mm(self) -> int:
        """Longest single print allowed."""
        return int(
            self.config_entry.options.get(CONF_MAX_LENGTH_MM, DEFAULT_MAX_LENGTH_MM)
        )

    async def _async_update_data(self) -> PrinterState:
        try:
            status = await self.queue.poll_status()
        except PrinterError as err:
            _LOGGER.debug("Status poll failed: %s", err)
            state = PrinterState(online=False)
        else:
            if status is None:  # a job is printing; keep the last reading
                return self.data or PrinterState(online=True)
            state = PrinterState(online=True, status=status)
        self._track_offline(state.online)
        return state

    def _track_offline(self, online: bool) -> None:
        """Raise a Repairs issue once the printer is unreachable for 24 h."""
        if online:
            self.store.set_offline_since(None)
            async_clear_offline_issue(self.hass, self.config_entry.entry_id)
            return
        now = dt_util.utcnow()
        since = self.store.offline_since
        if since is None:
            self.store.set_offline_since(now.isoformat())
            return
        started = datetime.fromisoformat(since)
        if now - started >= timedelta(hours=OFFLINE_REPAIR_AFTER_HOURS):
            async_raise_offline_issue(
                self.hass,
                self.config_entry.entry_id,
                self.config_entry.title,
                started,
            )

    @property
    def ai_task_entity(self) -> str | None:
        """The ``ai_task`` entity chosen in the options, if any."""
        return self.config_entry.options.get(CONF_AI_TASK) or None

    @property
    def use_ai_jokes(self) -> bool:
        """True when jokes and facts should come from the AI first."""
        return bool(self.config_entry.options.get(CONF_AI_JOKES)) and bool(
            self.ai_task_entity
        )

    def kid_profile(self, wanted: str | None = None) -> Profile:
        """Return a kid profile by name/ID, else the one chosen in the select."""
        return find_profile(
            self.config_entry.options,
            KID,
            wanted,
            self.store.get_setting(SETTING_KID_PROFILE),
        )

    @property
    def limiter(self) -> RateLimiter:
        """Kid-mode limits (settings from the options, counts from the store)."""
        return RateLimiter(self.store, dict(self.config_entry.options))

    def adult_profile(self, wanted: str | None = None) -> Profile:
        """Return an adult profile by name/ID, else the one chosen in the select."""
        return find_profile(
            self.config_entry.options,
            ADULT,
            wanted,
            self.store.get_setting(SETTING_ADULT_PROFILE),
        )

    async def async_preview(
        self, job: PrintJob | Callable[[], PrintJob]
    ) -> dict[str, Any]:
        """Render a job to a PNG (as a data URI) without printing it."""
        if not isinstance(job, PrintJob):
            job = await self.hass.async_add_executor_job(job)
        max_dots = max(1, self.max_length_mm - FEED_MM) * DOTS_PER_MM
        width = self.width

        def render() -> tuple[str, float, bool]:
            parts, height, extra_mm, truncated = render_job(job, width, max_dots)
            image = _stack([part for part, _ in parts], width)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            length = height / DOTS_PER_MM + FEED_MM + extra_mm
            return f"data:image/png;base64,{encoded}", length, truncated

        try:
            image, length, truncated = await self.hass.async_add_executor_job(render)
        except (OSError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="render_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return {
            "print_id": job.print_id,
            "type": job.type,
            "profile": job.profile,
            "length_mm": round(length, 1),
            "truncated": truncated,
            "image": image,
            **job.response,
        }

    async def async_print(
        self, job: PrintJob | Callable[[], PrintJob]
    ) -> dict[str, Any]:
        """Build (in the executor), render, send and record a print.

        ``job`` may be a ready ``PrintJob`` or a function that builds one;
        generators and data files are CPU/disk work, so they run off the loop.
        """
        if not isinstance(job, PrintJob):
            job = await self.hass.async_add_executor_job(job)
        max_dots = max(1, self.max_length_mm - FEED_MM) * DOTS_PER_MM
        width = self.width

        def render() -> tuple[bytes, int, float, bool]:
            parts, height, extra_mm, truncated = render_job(job, width, max_dots)
            data = escpos.INIT
            for image, extra in parts:
                data += escpos.raster(image) + extra
            return data + escpos.cut(), height, extra_mm, truncated

        try:
            data, height, extra_mm, truncated = await self.hass.async_add_executor_job(
                render
            )
        except (OSError, ValueError) as err:
            self._fire(job, success=False)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="render_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        try:
            await self.queue.print_job(data)
        except PrinterError as err:
            self._fire(job, success=False)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="print_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        length_mm = round(height / DOTS_PER_MM + FEED_MM + extra_mm, 1)
        printed_at = dt_util.utcnow().isoformat()
        self.store.record_print(
            {
                "type": job.type,
                "print_id": job.print_id,
                "printed_at": printed_at,
                "length_mm": length_mm,
                "profile": job.profile,
                "difficulty": job.difficulty,
            },
            list(job.answers),
        )
        self._fire(job, success=True)
        self.async_update_listeners()
        await self.async_request_refresh()
        return {
            "print_id": job.print_id,
            "type": job.type,
            "profile": job.profile,
            "length_mm": length_mm,
            "truncated": truncated,
            **job.response,
        }

    def _fire(self, job: PrintJob, *, success: bool) -> None:
        self.hass.bus.async_fire(
            EVENT_PRINTED,
            {
                "type": job.type,
                "print_id": job.print_id,
                "profile": job.profile,
                "success": success,
            },
        )
