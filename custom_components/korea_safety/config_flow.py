"""Config flow for Korean safety alerts."""

from typing import Any
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import SafetyAlertApiClient
from .exceptions import SafetyAlertConnectionError
from .region_api import SafetyAlertRegionApiClient


class KoreaSafetyConfigFlow(config_entries.ConfigFlow, domain="korea_safety"):
    """Configure a province, district, and optional sub-district."""

    VERSION = 1

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
