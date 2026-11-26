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
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import voluptuous as vol

from .const import (
    CONF_AI_JOKES,
    CONF_AI_TASK,
    CONF_CALENDARS,
    CONF_MAX_LENGTH_MM,
    CONF_MORNING_BOTTOM,
    CONF_PAPER_WIDTH,
    CONF_POLL_INTERVAL,
    CONF_PRINT_TEST_PAGE,
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
)
from .coordinator import TinyPressConfigEntry
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

    @property
    def _profiles(self) -> list[Profile]:
        return load_profiles(dict(self.config_entry.options))

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
                vol.Required(
                    CONF_MORNING_BOTTOM,
                    default=options.get(CONF_MORNING_BOTTOM, "joke"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(BOTTOM_OPTIONS),
                        translation_key=CONF_MORNING_BOTTOM,
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
