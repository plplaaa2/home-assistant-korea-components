"""Config flow for Korean safety alerts."""

from typing import Any
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback

from .api import SafetyAlertApiClient
from .exceptions import SafetyAlertConnectionError, SafetyAlertDataError
from .const import DOMAIN, LOGGER
from .region_api import SafetyAlertRegionApiClient


class KoreaSafetyConfigFlow(config_entries.ConfigFlow, domain="korea_safety"):
    """Configure a province, district, and optional sub-district."""

    VERSION = 1

    # Expose existing-entry region editing; related: strings.json, translations/ko.json.
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return KoreaSafetyOptionsFlow()

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input:
            self._data.update(user_input)
            self._data["sido_name"] = self._data["sido_options"][user_input["sido_code"]]
            return await self.async_step_sgg()
        regions = await SafetyAlertRegionApiClient().async_get_sido_list()
        options = {item["code"]: item["name"] for item in regions}
        self._data["sido_options"] = options
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("sido_code", default="1100000000"): vol.In(options)}),
        )

    async def async_step_sgg(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input:
            self._data.update(user_input)
            self._data["sgg_name"] = self._data["sgg_options"][user_input["sgg_code"]]
            return await self.async_step_emd()
        regions = await SafetyAlertRegionApiClient().async_get_sgg_list(self._data["sido_code"])
        if not regions:
            return self.async_abort(reason="cannot_connect")
        options = {item["code"]: item["name"] for item in regions}
        self._data["sgg_options"] = options
        return self.async_show_form(step_id="sgg", data_schema=vol.Schema({vol.Required("sgg_code"): vol.In(options)}))

    async def async_step_emd(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input:
            self._data.update(user_input)
            self._data["emd_name"] = self._data["emd_options"][user_input["emd_code"]]
            return await self._create_entry()
        regions = await SafetyAlertRegionApiClient().async_get_emd_list(self._data["sido_code"], self._data["sgg_code"])
        if not regions:
            return await self._create_entry()
        options = {item["code"]: item["name"] for item in regions}
        self._data["emd_options"] = options
        return self.async_show_form(step_id="emd", data_schema=vol.Schema({vol.Required("emd_code"): vol.In(options)}))

    async def _create_entry(self) -> FlowResult:
        sido = self._data["sido_code"]
        sgg = self._data.get("sgg_code", "")
        emd = self._data.get("emd_code", "")
        try:
            await SafetyAlertApiClient().async_get_safety_alerts(sido, sgg or None, emd or None)
        except SafetyAlertConnectionError:
            return self.async_abort(reason="cannot_connect")
        unique_id = f"{sido}_{sgg}_{emd}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        name = " ".join(filter(None, [self._data["sido_name"], self._data.get("sgg_name"), self._data.get("emd_name")]))
        return self.async_create_entry(title=f"안전알림 ({name})", data={"area_code": sido, "area_name": name, "area_code2": sgg, "area_code3": emd})


# Update configuration only after validation; related: __init__.py, region_api.py.
class KoreaSafetyOptionsFlow(config_entries.OptionsFlow):
    """Edit a configured region while preserving the config entry."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, str] = {}

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            code = user_input["sido_code"]
            self._data = {"area_code": code, "sido_name": self._options[code]}
            return await self.async_step_sgg()
        regions = await SafetyAlertRegionApiClient().async_get_sido_list()
        self._options = {r["code"]: r["name"] for r in regions}
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("sido_code", default=self.config_entry.data["area_code"]): vol.In(self._options),
        }))

    async def async_step_sgg(self, user_input=None):
        if user_input is not None:
            code = user_input["sgg_code"]
            self._data.update(area_code2=code, sgg_name=self._options[code] if code else "")
            if not code:
                self._data.update(area_code3="", emd_name="")
                return await self._save()
            return await self.async_step_emd()
        regions = await SafetyAlertRegionApiClient().async_get_sgg_list(self._data["area_code"])
        if regions is None:
            LOGGER.warning("Safety Alert configuration: district lookup failed for %s", self._data["area_code"])
            return self.async_abort(reason="cannot_connect")
        self._options = {"": "전체", **{r["code"]: r["name"] for r in regions}}
        current = self.config_entry.data.get("area_code2", "")
        default = current if self._data["area_code"] == self.config_entry.data["area_code"] and current in self._options else ""
        return self.async_show_form(step_id="sgg", data_schema=vol.Schema({
            vol.Required("sgg_code", default=default): vol.In(self._options),
        }))

    async def async_step_emd(self, user_input=None):
        if user_input is not None:
            code = user_input["emd_code"]
            self._data.update(area_code3=code, emd_name=self._options[code] if code else "")
            return await self._save()
        regions = await SafetyAlertRegionApiClient().async_get_emd_list(self._data["area_code"], self._data["area_code2"])
        if regions is None:
            LOGGER.warning("Safety Alert configuration: sub-district lookup failed for %s/%s", self._data["area_code"], self._data["area_code2"])
            return self.async_abort(reason="cannot_connect")
        self._options = {"": "전체", **{r["code"]: r["name"] for r in regions}}
        current = self.config_entry.data.get("area_code3", "")
        same_parent = all(self._data[k] == self.config_entry.data.get(k, "") for k in ("area_code", "area_code2"))
        return self.async_show_form(step_id="emd", data_schema=vol.Schema({
            vol.Required("emd_code", default=current if same_parent and current in self._options else ""): vol.In(self._options),
        }))

    async def _save(self):
        codes = tuple(self._data.get(k, "") for k in ("area_code", "area_code2", "area_code3"))
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id != self.config_entry.entry_id and codes == tuple(entry.data.get(k, "") or "" for k in ("area_code", "area_code2", "area_code3")):
                return self.async_abort(reason="already_configured")
        try:
            await SafetyAlertApiClient().async_get_safety_alerts(*codes)
        except (SafetyAlertConnectionError, SafetyAlertDataError) as err:
            LOGGER.warning("Safety Alert configuration validation failed for %s: %s", "/".join(codes), err)
            return self.async_abort(reason="cannot_connect")
        name = " ".join(filter(None, (self._data.get(k) for k in ("sido_name", "sgg_name", "emd_name"))))
        data = {**self.config_entry.data, **dict(zip(("area_code", "area_code2", "area_code3"), codes)), "area_name": name}
        self.hass.config_entries.async_update_entry(self.config_entry, data=data, title=f"안전알림 ({name})", unique_id="_".join(codes))
        LOGGER.warning("Safety Alert region configuration changed to %s; reloading integration", name)
        if not await self.hass.config_entries.async_reload(self.config_entry.entry_id):
            LOGGER.error("Safety Alert configuration saved, but integration reload failed for %s", name)
        return self.async_create_entry(title="", data={})
