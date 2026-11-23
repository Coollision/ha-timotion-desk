"""Config flow: find the desk, then manage presets from the Configure dialog."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_KEEP_CONNECTED,
    CONF_PRESET_HEIGHT,
    CONF_PRESET_NAME,
    CONF_PRESETS,
    DEFAULT_KEEP_CONNECTED,
    DOMAIN,
)
from .protocol import DEVICE_NAME_PREFIX, HEIGHT_MAX_CM, HEIGHT_MIN_CM

_HEIGHT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=HEIGHT_MIN_CM,
        max=HEIGHT_MAX_CM,
        step=1,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="cm",
    )
)


def _is_desk(info: BluetoothServiceInfoBleak) -> bool:
    # Name only: a passive scanner can miss the service UUID (it may sit in the
    # scan response), but the local name is in the advertisement itself.
    return (info.name or "").startswith(DEVICE_NAME_PREFIX)


class TimotionDeskConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a desk by Bluetooth discovery or by picking it from the list."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._candidates: dict[str, BluetoothServiceInfoBleak] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> TimotionDeskOptionsFlow:
        return TimotionDeskOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self._create(self._discovery)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create(self._candidates[address])

        configured = self._async_current_ids()
        self._candidates = {
            info.address: info
            for info in async_discovered_service_info(self.hass, connectable=True)
            if _is_desk(info) and info.address not in configured
        }
        if not self._candidates:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {a: f"{i.name} ({a})" for a, i in self._candidates.items()}
                    )
                }
            ),
        )

    def _create(self, info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        return self.async_create_entry(title=info.name, data={CONF_ADDRESS: info.address})


class TimotionDeskOptionsFlow(OptionsFlowWithReload):
    """Connection settings and an unlimited list of named height presets."""

    def __init__(self) -> None:
        self._edit_name: str | None = None

    # -- helpers -----------------------------------------------------------

    def _presets(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.config_entry.options.get(CONF_PRESETS, [])]

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    @staticmethod
    def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
        return {
            CONF_PRESET_NAME: user_input[CONF_PRESET_NAME].strip(),
            CONF_PRESET_HEIGHT: int(round(user_input[CONF_PRESET_HEIGHT])),
        }

    @staticmethod
    def _preset_schema(name: str = "", height: int = 74) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_PRESET_NAME, default=name): selector.TextSelector(),
                vol.Required(CONF_PRESET_HEIGHT, default=height): _HEIGHT_SELECTOR,
            }
        )

    @staticmethod
    def _name_error(name: str, taken: set[str]) -> str | None:
        if not name:
            return "name_empty"
        return "name_exists" if name in taken else None

    # -- steps -------------------------------------------------------------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["add_preset"]
        if self._presets():
            menu += ["edit_preset", "remove_preset"]
        menu.append("settings")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(**user_input)
        current = self.config_entry.options.get(CONF_KEEP_CONNECTED, DEFAULT_KEEP_CONNECTED)
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({vol.Required(CONF_KEEP_CONNECTED, default=current): bool}),
        )

    async def async_step_add_preset(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        presets = self._presets()
        if user_input is not None:
            preset = self._clean(user_input)
            error = self._name_error(preset[CONF_PRESET_NAME], {p[CONF_PRESET_NAME] for p in presets})
            if error is None:
                return self._save(presets=[*presets, preset])
            errors["base"] = error
        return self.async_show_form(
            step_id="add_preset", data_schema=self._preset_schema(), errors=errors
        )

    async def async_step_edit_preset(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        names = [p[CONF_PRESET_NAME] for p in self._presets()]
        if user_input is not None:
            self._edit_name = user_input[CONF_PRESET_NAME]
            return await self.async_step_edit_preset_details()
        return self.async_show_form(
            step_id="edit_preset",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRESET_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=names, mode=selector.SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_edit_preset_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        presets = self._presets()
        current = next(p for p in presets if p[CONF_PRESET_NAME] == self._edit_name)
        if user_input is not None:
            updated = self._clean(user_input)
            others = {p[CONF_PRESET_NAME] for p in presets if p is not current}
            error = self._name_error(updated[CONF_PRESET_NAME], others)
            if error is None:
                return self._save(presets=[updated if p is current else p for p in presets])
            errors["base"] = error
        return self.async_show_form(
            step_id="edit_preset_details",
            data_schema=self._preset_schema(current[CONF_PRESET_NAME], current[CONF_PRESET_HEIGHT]),
            errors=errors,
        )

    async def async_step_remove_preset(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        presets = self._presets()
        if user_input is not None:
            gone = set(user_input["remove"])
            return self._save(presets=[p for p in presets if p[CONF_PRESET_NAME] not in gone])
        return self.async_show_form(
            step_id="remove_preset",
            data_schema=vol.Schema(
                {
                    vol.Required("remove"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[p[CONF_PRESET_NAME] for p in presets],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )
