"""Config and options flows for Tiny Press."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    BooleanSelector,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import voluptuous as vol

from .const import (
    BOTTOM_SOURCES,
    CONF_AI_JOKES,
    CONF_AI_TASK,
    CONF_BOTTOM_SOURCE,
    CONF_CALENDARS,
    CONF_CUSTOM_DAYS,
    CONF_EXCLUDED_DAYS,
    CONF_FEEDS,
    CONF_HOLIDAY_CALENDARS,
    CONF_HOLIDAY_GROUPS,
    CONF_MAX_LENGTH_MM,
    CONF_MORNING_BOTTOM,
    CONF_MORNING_FEED,
    CONF_PAPER_WIDTH,
    CONF_POLL_INTERVAL,
    CONF_PRINT_TEST_PAGE,
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_START,
    CONF_QUOTE_FEED,
    CONF_SCHOOL_DAY,
    CONF_SECULAR_DAYS,
    CONF_THEME,
    CONF_TODOS,
    CONF_WEATHER,
    DEFAULT_MAX_LENGTH_MM,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    PAPER_58MM,
    PAPER_80MM,
    PAPER_DOTS,
    Difficulty,
    bottom_source,
)
from .coordinator import TinyPressConfigEntry
from .fetch import (
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    QUIET_MODES,
    FeedConfig,
    FetchError,
    async_fetch_feed,
    feeds_from_options,
)
from .generators import observances
from .generators.feeds import DEFAULT_ITEMS, MAX_ITEMS
from .generators.morning import BOTTOM_OPTIONS
from .jobs import test_page_job
from .limits import (
    CONF_ADMINS_SKIP,
    CONF_COOLDOWN_S,
    CONF_LIMITS_ENABLED,
    CONF_PAPER_MM_DAY,
    CONF_PER_DAY,
    CONF_PER_HOUR,
    DEFAULTS as LIMIT_DEFAULTS,
)
from .printer import escpos
from .printer.transport import PrinterConnectError, PrinterError, PrinterTransport
from .profiles import (
    ADULT,
    CONF_PROFILES,
    GRADES,
    KID,
    Profile,
    grade_label,
    grade_number,
    load_profiles,
    slugify,
)

_LOGGER = logging.getLogger(__name__)

PAPER_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[PAPER_80MM, PAPER_58MM],
        translation_key=CONF_PAPER_WIDTH,
        mode=SelectSelectorMode.LIST,
    )
)


async def _probe(host: str, port: int) -> str | None:
    """Return an error key, or None when the printer answers ESC/POS status."""
    try:
        await PrinterTransport(host, port).read_status()
    except PrinterConnectError:
        return "cannot_connect"
    except PrinterError:
        return "no_status"
    return None


class TinyPressConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a printer by address or from DHCP discovery."""

    VERSION = 1

    def __init__(self) -> None:
        """Start empty."""
        self._host: str | None = None
        self._port: int = DEFAULT_PORT

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host and port, then test-connect and read status."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            if (error := await _probe(host, port)) is None:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                self._host, self._port = host, port
                return await self.async_step_paper()
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Offer a discovered Epson device if it speaks ESC/POS."""
        host = discovery_info.ip
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._async_abort_entries_match({CONF_HOST: host})
        # Epson's MAC ranges also cover inkjets and projectors: only offer
        # devices that answer receipt-printer status on port 9100.
        if await _probe(host, DEFAULT_PORT) is not None:
            return self.async_abort(reason="not_receipt_printer")
        self._host, self._port = host, DEFAULT_PORT
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered printer."""
        if user_input is not None:
            return await self.async_step_paper()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"host": self._host or ""},
        )

    async def async_step_paper(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the paper width and optionally print a test page."""
        assert self._host is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            paper = user_input[CONF_PAPER_WIDTH]
            if user_input.get(CONF_PRINT_TEST_PAGE) and not (
                await self._print_test_page(paper)
            ):
                errors["base"] = "test_page_failed"
            if not errors:
                return self.async_create_entry(
                    title=f"Tiny Press ({self._host})",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_PAPER_WIDTH: paper,
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_PAPER_WIDTH, default=PAPER_80MM): PAPER_SELECTOR,
                vol.Optional(CONF_PRINT_TEST_PAGE, default=True): bool,
            }
        )
        return self.async_show_form(step_id="paper", data_schema=schema, errors=errors)

    async def _print_test_page(self, paper: str) -> bool:
        """Print the test page straight from the flow (before the entry exists)."""
        assert self._host is not None
        job = test_page_job(
            paper,
            {
                "Printer": f"{self._host}:{self._port}",
                "Paper": f"{paper} mm, {PAPER_DOTS[paper]} dots",
            },
        )

        def render() -> bytes:
            image, _ = job.build(PAPER_DOTS[paper]).render()
            return escpos.INIT + escpos.raster(image) + job.extra + escpos.cut()

        data = await self.hass.async_add_executor_job(render)
        try:
            await PrinterTransport(self._host, self._port).send(data)
        except PrinterError as err:
            _LOGGER.warning("Test page failed: %s", err)
            return False
        return True

    @staticmethod
    @callback
    def async_get_options_flow(entry: TinyPressConfigEntry) -> TinyPressOptionsFlow:
        """Return the options flow."""
        return TinyPressOptionsFlow()


def _kid_schema(profile: Profile | None) -> vol.Schema:
    p = profile or Profile(id="", kind=KID, name="")
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=p.name): TextSelector(),
            vol.Required("grade", default=p.grade.lower()): SelectSelector(
                SelectSelectorConfig(
                    options=[g.lower() for g in GRADES],
                    translation_key="grade",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                "math_grade", default=(p.math_grade or p.grade).lower()
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[g.lower() for g in GRADES],
                    translation_key="grade",
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("interests", default=p.interests): TextSelector(),
            vol.Required("stretch", default=p.stretch): BooleanSelector(),
            vol.Optional(
                "spelling_todo",
                description={"suggested_value": p.spelling_todo or None},
            ): EntitySelector(EntitySelectorConfig(domain="todo")),
            vol.Optional("spelling_words", default=p.spelling_words): TextSelector(
                TextSelectorConfig(multiline=True)
            ),
        }
    )


def _adult_schema(profile: Profile | None) -> vol.Schema:
    p = profile or Profile(id="", kind=ADULT, name="")
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=p.name): TextSelector(),
            vol.Required("difficulty", default=p.difficulty): SelectSelector(
                SelectSelectorConfig(
                    options=[d.value for d in Difficulty],
                    translation_key="difficulty",
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
    )


class TinyPressOptionsFlow(OptionsFlowWithReload):
    """Settings and household profiles."""

    def __init__(self) -> None:
        """Start with nothing selected."""
        self._editing: Profile | None = None
        self._feed_id: str | None = None
        self._holiday_input: dict[str, Any] = {}

    @property
    def _profiles(self) -> list[Profile]:
        return load_profiles(dict(self.config_entry.options))

    @property
    def _feeds(self) -> list[dict[str, Any]]:
        return [
            f.as_dict() for f in feeds_from_options(dict(self.config_entry.options))
        ]

    def _save(
        self, profiles: list[Profile] | None = None, **changes: Any
    ) -> ConfigFlowResult:
        options = dict(self.config_entry.options)
        options.update(changes)
        if profiles is not None:
            options[CONF_PROFILES] = [p.as_dict() for p in profiles]
        return self.async_create_entry(data=options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose what to change."""
        menu = ["settings", "kid_limits", "add_kid", "add_adult"]
        if self._profiles:
            menu += ["edit_profile", "remove_profile"]
        menu.append("add_feed")
        if self._feeds:
            menu += ["edit_feed", "remove_feed"]
        menu += ["holidays", "add_day"]
        if self.config_entry.options.get(CONF_CUSTOM_DAYS):
            menu.append("remove_day")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Longest print, poll interval and the AI entity."""
        if user_input is not None:
            return self._save(
                **{
                    CONF_MAX_LENGTH_MM: int(user_input[CONF_MAX_LENGTH_MM]),
                    CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL]),
                    CONF_AI_TASK: user_input.get(CONF_AI_TASK) or None,
                    CONF_AI_JOKES: bool(user_input.get(CONF_AI_JOKES)),
                    CONF_WEATHER: user_input.get(CONF_WEATHER) or None,
                    CONF_CALENDARS: list(user_input.get(CONF_CALENDARS) or []),
                    CONF_TODOS: list(user_input.get(CONF_TODOS) or []),
                    CONF_MORNING_BOTTOM: user_input.get(CONF_MORNING_BOTTOM, "joke"),
                    CONF_BOTTOM_SOURCE: user_input.get(CONF_BOTTOM_SOURCE, "online"),
                    CONF_QUOTE_FEED: user_input.get(CONF_QUOTE_FEED) or None,
                    CONF_MORNING_FEED: user_input.get(CONF_MORNING_FEED) or None,
                    CONF_QUIET_START: user_input.get(CONF_QUIET_START) or None,
                    CONF_QUIET_END: user_input.get(CONF_QUIET_END) or None,
                    CONF_QUIET_MODE: user_input.get(CONF_QUIET_MODE, "skip"),
                }
            )
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAX_LENGTH_MM,
                    default=options.get(CONF_MAX_LENGTH_MM, DEFAULT_MAX_LENGTH_MM),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=100,
                        max=3000,
                        step=10,
                        unit_of_measurement="mm",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=5,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_AI_TASK,
                    description={"suggested_value": options.get(CONF_AI_TASK)},
                ): EntitySelector(EntitySelectorConfig(domain="ai_task")),
                vol.Required(
                    CONF_AI_JOKES, default=bool(options.get(CONF_AI_JOKES, False))
                ): BooleanSelector(),
                vol.Optional(
                    CONF_WEATHER,
                    description={"suggested_value": options.get(CONF_WEATHER)},
                ): EntitySelector(EntitySelectorConfig(domain="weather")),
                vol.Optional(
                    CONF_CALENDARS,
                    description={"suggested_value": options.get(CONF_CALENDARS)},
                ): EntitySelector(
                    EntitySelectorConfig(domain="calendar", multiple=True)
                ),
                vol.Optional(
                    CONF_TODOS,
                    description={"suggested_value": options.get(CONF_TODOS)},
                ): EntitySelector(EntitySelectorConfig(domain="todo", multiple=True)),
                **self._morning_feed_field(options),
                vol.Required(
                    CONF_MORNING_BOTTOM,
                    default=self._bottom_default(options),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(BOTTOM_OPTIONS),
                        translation_key=CONF_MORNING_BOTTOM,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    CONF_BOTTOM_SOURCE, default=bottom_source(options)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(BOTTOM_SOURCES),
                        translation_key=CONF_BOTTOM_SOURCE,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                **self._quote_feed_field(options),
                vol.Optional(
                    CONF_QUIET_START,
                    description={
                        "suggested_value": options.get(
                            CONF_QUIET_START, DEFAULT_QUIET_START
                        )
                    },
                ): TimeSelector(),
                vol.Optional(
                    CONF_QUIET_END,
                    description={
                        "suggested_value": options.get(
                            CONF_QUIET_END, DEFAULT_QUIET_END
                        )
                    },
                ): TimeSelector(),
                vol.Required(
                    CONF_QUIET_MODE, default=options.get(CONF_QUIET_MODE, "skip")
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(QUIET_MODES),
                        translation_key=CONF_QUIET_MODE,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_kid_limits(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Kid-mode rate limits."""
        if user_input is not None:
            return self._save(
                **{
                    CONF_LIMITS_ENABLED: bool(user_input[CONF_LIMITS_ENABLED]),
                    CONF_COOLDOWN_S: int(user_input[CONF_COOLDOWN_S]),
                    CONF_PER_HOUR: int(user_input[CONF_PER_HOUR]),
                    CONF_PER_DAY: int(user_input[CONF_PER_DAY]),
                    CONF_PAPER_MM_DAY: int(user_input[CONF_PAPER_MM_DAY]),
                    CONF_ADMINS_SKIP: bool(user_input[CONF_ADMINS_SKIP]),
                }
            )
        current = {**LIMIT_DEFAULTS, **self.config_entry.options}

        def number(key: str, low: int, high: int, step: int, unit: str) -> Any:
            return {
                vol.Required(key, default=current[key]): NumberSelector(
                    NumberSelectorConfig(
                        min=low,
                        max=high,
                        step=step,
                        unit_of_measurement=unit,
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LIMITS_ENABLED, default=current[CONF_LIMITS_ENABLED]
                ): BooleanSelector(),
                **number(CONF_COOLDOWN_S, 0, 3600, 10, "s"),
                **number(CONF_PER_HOUR, 0, 60, 1, "prints"),
                **number(CONF_PER_DAY, 1, 200, 1, "prints"),
                **number(CONF_PAPER_MM_DAY, 100, 20000, 50, "mm"),
                vol.Required(
                    CONF_ADMINS_SKIP, default=current[CONF_ADMINS_SKIP]
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="kid_limits", data_schema=schema)

    def _check_name(self, name: str, keep_id: str | None = None) -> str | None:
        name = name.strip()
        if not name:
            return "name_required"
        if any(
            p.name.lower() == name.lower() and p.id != keep_id for p in self._profiles
        ):
            return "name_exists"
        return None

    def _new_id(self, name: str) -> str:
        base = slugify(name)
        taken = {p.id for p in self._profiles}
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}_{n}", n + 1
        return candidate

    def _kid_from(self, data: dict[str, Any], profile_id: str) -> Profile:
        return Profile(
            id=profile_id,
            kind=KID,
            name=data[CONF_NAME].strip(),
            grade=grade_label(grade_number(data["grade"])),
            math_grade=grade_label(grade_number(data.get("math_grade", data["grade"]))),
            interests=(data.get("interests") or "").strip(),
            stretch=bool(data.get("stretch")),
            spelling_words=(data.get("spelling_words") or "").strip(),
            spelling_todo=data.get("spelling_todo") or "",
        )

    def _adult_from(self, data: dict[str, Any], profile_id: str) -> Profile:
        return Profile(
            id=profile_id,
            kind=ADULT,
            name=data[CONF_NAME].strip(),
            difficulty=data["difficulty"],
        )

    async def async_step_add_kid(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a kid profile."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := self._check_name(user_input[CONF_NAME]):
                errors[CONF_NAME] = error
            else:
                kid = self._kid_from(user_input, self._new_id(user_input[CONF_NAME]))
                return self._save([*self._profiles, kid])
        return self.async_show_form(
            step_id="add_kid",
            data_schema=self.add_suggested_values_to_schema(
                _kid_schema(None), user_input
            ),
            errors=errors,
        )

    async def async_step_add_adult(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add an adult profile."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := self._check_name(user_input[CONF_NAME]):
                errors[CONF_NAME] = error
            else:
                adult = self._adult_from(
                    user_input, self._new_id(user_input[CONF_NAME])
                )
                return self._save([*self._profiles, adult])
        return self.async_show_form(
            step_id="add_adult",
            data_schema=self.add_suggested_values_to_schema(
                _adult_schema(None), user_input
            ),
            errors=errors,
        )

    def _profile_selector(self, multiple: bool = False) -> SelectSelector:
        return SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=p.id, label=f"{p.name} ({p.kind})")
                    for p in self._profiles
                ],
                multiple=multiple,
                mode=SelectSelectorMode.LIST,
            )
        )

    async def async_step_edit_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a profile to edit."""
        if user_input is not None:
            self._editing = next(
                p for p in self._profiles if p.id == user_input["profile"]
            )
            if self._editing.kind == KID:
                return await self.async_step_edit_kid()
            return await self.async_step_edit_adult()
        return self.async_show_form(
            step_id="edit_profile",
            data_schema=vol.Schema({vol.Required("profile"): self._profile_selector()}),
        )

    def _replace(self, updated: Profile) -> ConfigFlowResult:
        return self._save(
            [updated if p.id == updated.id else p for p in self._profiles]
        )

    async def async_step_edit_kid(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a kid profile."""
        assert self._editing is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := self._check_name(user_input[CONF_NAME], self._editing.id):
                errors[CONF_NAME] = error
            else:
                return self._replace(self._kid_from(user_input, self._editing.id))
        return self.async_show_form(
            step_id="edit_kid",
            data_schema=_kid_schema(self._editing),
            errors=errors,
            description_placeholders={"name": self._editing.name},
        )

    async def async_step_edit_adult(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit an adult profile."""
        assert self._editing is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := self._check_name(user_input[CONF_NAME], self._editing.id):
                errors[CONF_NAME] = error
            else:
                return self._replace(self._adult_from(user_input, self._editing.id))
        return self.async_show_form(
            step_id="edit_adult",
            data_schema=_adult_schema(self._editing),
            errors=errors,
            description_placeholders={"name": self._editing.name},
        )

    async def async_step_remove_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one or more profiles."""
        if user_input is not None:
            gone = set(user_input.get("profiles") or [])
            return self._save([p for p in self._profiles if p.id not in gone])
        return self.async_show_form(
            step_id="remove_profile",
            data_schema=vol.Schema(
                {vol.Required("profiles"): self._profile_selector(multiple=True)}
            ),
        )

    def _morning_feed_field(self, options: Any) -> dict[Any, Any]:
        """Offer the morning slip headlines feed, when any feed is set up."""
        if not self._feeds:
            return {}
        return {
            vol.Optional(
                CONF_MORNING_FEED,
                description={"suggested_value": options.get(CONF_MORNING_FEED)},
            ): self._feed_selector()
        }

    def _quote_feed_field(self, options: Any) -> dict[Any, Any]:
        """Offer a feed for quotes (used when the source is "feed")."""
        if not self._feeds:
            return {}
        return {
            vol.Optional(
                CONF_QUOTE_FEED,
                description={"suggested_value": options.get(CONF_QUOTE_FEED)},
            ): self._feed_selector()
        }

    @staticmethod
    def _bottom_default(options: Any) -> str:
        bottom = options.get(CONF_MORNING_BOTTOM, "joke")
        # v0.9.0's "feed" bottom is gone; headlines are their own setting.
        return "quote" if bottom == "feed" else bottom

    def _feed_selector(self, multiple: bool = False) -> SelectSelector:
        return SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=f["id"], label=f["name"])
                    for f in self._feeds
                ],
                multiple=multiple,
                mode=SelectSelectorMode.LIST
                if multiple
                else SelectSelectorMode.DROPDOWN,
            )
        )

    async def async_step_add_feed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add an RSS or Atom feed (checked by reading it once)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            url = user_input["url"].strip()
            feeds = self._feeds
            if not name:
                errors[CONF_NAME] = "name_required"
            elif any(f["name"].lower() == name.lower() for f in feeds):
                errors[CONF_NAME] = "feed_exists"
            elif not url.startswith(("https://", "http://")):
                errors["url"] = "invalid_url"
            else:
                try:
                    await async_fetch_feed(self.hass, url, 1)
                except FetchError as err:
                    _LOGGER.info("Feed %s didn't load: %s", url, err)
                    errors["url"] = "cannot_read_feed"
                else:
                    base = slugify(name) or "feed"
                    taken = {f["id"] for f in feeds}
                    feed_id, n = base, 2
                    while feed_id in taken:
                        feed_id, n = f"{base}_{n}", n + 1
                    feeds.append(
                        FeedConfig(
                            feed_id, name, url, int(user_input["items"])
                        ).as_dict()
                    )
                    return self._save(**{CONF_FEEDS: feeds})
        defaults = user_input or {}
        return self.async_show_form(
            step_id="add_feed",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
                    vol.Required("url", default=defaults.get("url", "")): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                    vol.Required(
                        "items", default=defaults.get("items", DEFAULT_ITEMS)
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=MAX_ITEMS, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_feed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a feed to change."""
        if user_input is not None:
            self._feed_id = user_input["feed"]
            return await self.async_step_feed_settings()
        return self.async_show_form(
            step_id="edit_feed",
            data_schema=vol.Schema({vol.Required("feed"): self._feed_selector()}),
        )

    async def async_step_feed_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Items per print, and auto-print."""
        feeds = self._feeds
        current = next(f for f in feeds if f["id"] == self._feed_id)
        if user_input is not None:
            updated = FeedConfig.from_dict(
                {
                    **current,
                    "items": int(user_input["items"]),
                    "auto_print": bool(user_input["auto_print"]),
                    "check_minutes": int(user_input["check_minutes"]),
                    "auto_qr": bool(user_input["auto_qr"]),
                }
            ).as_dict()
            return self._save(
                **{
                    CONF_FEEDS: [
                        updated if f["id"] == self._feed_id else f for f in feeds
                    ]
                }
            )
        schema = vol.Schema(
            {
                vol.Required("items", default=current["items"]): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=MAX_ITEMS, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    "auto_print", default=current["auto_print"]
                ): BooleanSelector(),
                vol.Required(
                    "check_minutes", default=current["check_minutes"]
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=5,
                        max=1440,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("auto_qr", default=current["auto_qr"]): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="feed_settings",
            data_schema=schema,
            description_placeholders={"name": current["name"]},
        )

    async def async_step_remove_feed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one or more feeds."""
        if user_input is not None:
            gone = set(user_input.get("feeds") or [])
            options = dict(self.config_entry.options)
            changes: dict[str, Any] = {
                CONF_FEEDS: [f for f in self._feeds if f["id"] not in gone]
            }
            if options.get(CONF_MORNING_FEED) in gone:
                changes[CONF_MORNING_FEED] = None
            return self._save(**changes)
        return self.async_show_form(
            step_id="remove_feed",
            data_schema=vol.Schema(
                {vol.Required("feeds"): self._feed_selector(multiple=True)}
            ),
        )

    async def async_step_holidays(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Theme, secular days, public holiday calendars and holiday groups."""
        options = self.config_entry.options
        if user_input is not None:
            self._holiday_input = {
                CONF_THEME: user_input.get(CONF_THEME, "auto"),
                CONF_SECULAR_DAYS: list(user_input.get(CONF_SECULAR_DAYS) or []),
                CONF_HOLIDAY_CALENDARS: list(
                    user_input.get(CONF_HOLIDAY_CALENDARS) or []
                ),
                CONF_SCHOOL_DAY: user_input.get(CONF_SCHOOL_DAY) or None,
                CONF_HOLIDAY_GROUPS: list(user_input.get(CONF_HOLIDAY_GROUPS) or []),
            }
            if self._holiday_input[CONF_HOLIDAY_GROUPS]:
                return await self.async_step_holiday_days()
            return self._save(**self._holiday_input)
        groups = observances.groups()
        secular = [g["id"] for g in groups if g.get("secular")]
        cultural = [g["id"] for g in groups if not g.get("secular")]
        theme_options = [
            SelectOptionDict(
                value="auto", label="Auto: today's holiday, else the season"
            ),
            SelectOptionDict(value="off", label="Off"),
        ] + [
            SelectOptionDict(value=key, label=key.replace("_", " ").title())
            for key in observances.fixed_themes()
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_THEME, default=options.get(CONF_THEME, "auto")
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=theme_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(
                    CONF_SECULAR_DAYS,
                    default=list(options.get(CONF_SECULAR_DAYS, secular)),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=secular,
                        multiple=True,
                        translation_key="holiday_group",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_HOLIDAY_CALENDARS,
                    description={
                        "suggested_value": options.get(CONF_HOLIDAY_CALENDARS)
                    },
                ): EntitySelector(
                    EntitySelectorConfig(domain="calendar", multiple=True)
                ),
                vol.Optional(
                    CONF_SCHOOL_DAY,
                    description={"suggested_value": options.get(CONF_SCHOOL_DAY)},
                ): DateSelector(),
                vol.Optional(
                    CONF_HOLIDAY_GROUPS,
                    default=list(options.get(CONF_HOLIDAY_GROUPS, [])),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=cultural,
                        multiple=True,
                        translation_key="holiday_group",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="holidays", data_schema=schema)

    async def async_step_holiday_days(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Untick single days inside the picked groups."""
        picked = set(self._holiday_input[CONF_HOLIDAY_GROUPS])
        days = [o for o in observances.all_observances() if o["group"] in picked]
        in_groups = {o["id"] for o in days}
        excluded = set(self.config_entry.options.get(CONF_EXCLUDED_DAYS) or [])
        if user_input is not None:
            kept = set(user_input.get("days") or [])
            excluded = (excluded - in_groups) | (in_groups - kept)
            return self._save(
                **self._holiday_input, **{CONF_EXCLUDED_DAYS: sorted(excluded)}
            )
        names = {g["id"]: g["name"] for g in observances.groups()}
        schema = vol.Schema(
            {
                vol.Optional(
                    "days", default=[o["id"] for o in days if o["id"] not in excluded]
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=o["id"],
                                label=f"{o['name']} ({names.get(o['group'], o['group'])})",
                            )
                            for o in days
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="holiday_days", data_schema=schema)

    async def async_step_add_day(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a family day (every year on the same date)."""
        errors: dict[str, str] = {}
        days = list(self.config_entry.options.get(CONF_CUSTOM_DAYS) or [])
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                base = slugify(name) or "day"
                taken = {d.get("id") for d in days}
                day_id, n = base, 2
                while day_id in taken:
                    day_id, n = f"{base}_{n}", n + 1
                chosen_art = user_input.get("art") or "celebrate"
                days.append(
                    {
                        "id": day_id,
                        "name": name,
                        "date": str(user_input["date"])[5:10],
                        "banner": (user_input.get("banner") or "").strip()
                        or f"Today is {name}!",
                        "art": None if chosen_art == "none" else chosen_art,
                    }
                )
                return self._save(**{CONF_CUSTOM_DAYS: days})
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required("date"): DateSelector(),
                vol.Optional("banner"): str,
                vol.Required("art", default="celebrate"): SelectSelector(
                    SelectSelectorConfig(
                        options=["none", *observances.art_names()],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="add_day", data_schema=schema, errors=errors
        )

    async def async_step_remove_day(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove family days."""
        days = list(self.config_entry.options.get(CONF_CUSTOM_DAYS) or [])
        if user_input is not None:
            gone = set(user_input.get("days") or [])
            return self._save(
                **{CONF_CUSTOM_DAYS: [d for d in days if d["id"] not in gone]}
            )
        schema = vol.Schema(
            {
                vol.Required("days"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=d["id"], label=f"{d['name']} ({d['date']})"
                            )
                            for d in days
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_day", data_schema=schema)
