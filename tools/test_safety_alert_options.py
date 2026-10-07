"""Offline options-flow checks; related: korea_safety/config_flow.py, device.py."""
import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Flow:
    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


class OptionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "custom_components/korea_safety/config_flow.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "KoreaSafetyOptionsFlow")
        self.api = AsyncMock()
        self.regions = AsyncMock()
        self.regions.async_get_sido_list.return_value = [{"code": "11", "name": "서울"}, {"code": "41", "name": "경기"}]
        self.regions.async_get_sgg_list.return_value = [{"code": "411", "name": "시군구"}]
        self.regions.async_get_emd_list.return_value = [{"code": "4111", "name": "읍면동"}]
        ns = {"Any": object, "config_entries": SimpleNamespace(OptionsFlow=Flow), "DOMAIN": "korea_safety", "LOGGER": logging.getLogger("options_test"),
              "SafetyAlertApiClient": lambda: self.api, "SafetyAlertRegionApiClient": lambda: self.regions,
              "SafetyAlertConnectionError": ConnectionError, "SafetyAlertDataError": ValueError,
              "vol": SimpleNamespace(Schema=lambda x: x, Required=lambda name, **kw: name, In=lambda x: x)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "config_flow.py", "exec"), ns)
        self.flow = ns["KoreaSafetyOptionsFlow"]()
        self.entry = SimpleNamespace(entry_id="existing", data={"area_code": "11", "area_code2": "", "area_code3": "", "area_name": "서울"})
        self.flow.config_entry = self.entry
        self.manager = MagicMock()
        self.manager.async_entries.return_value = [self.entry]
        self.manager.async_reload = AsyncMock(return_value=True)
        self.flow.hass = SimpleNamespace(config_entries=self.manager)

    async def choose_province(self):
        await self.flow.async_step_init()
        result = await self.flow.async_step_init({"sido_code": "41"})
        self.assertEqual(result["step_id"], "sgg")
        self.manager.async_update_entry.assert_not_called()

    async def test_all_districts_and_reload(self):
        await self.choose_province()
        result = await self.flow.async_step_sgg({"sgg_code": ""})
        self.assertEqual(result["type"], "create_entry")
        data = self.manager.async_update_entry.call_args.kwargs["data"]
        self.assertEqual((data["area_code"], data["area_code2"], data["area_code3"]), ("41", "", ""))
        self.manager.async_reload.assert_awaited_once_with("existing")

    async def test_subdistrict(self):
        await self.choose_province()
        await self.flow.async_step_sgg({"sgg_code": "411"})
        await self.flow.async_step_emd({"emd_code": "4111"})
        self.assertEqual(self.manager.async_update_entry.call_args.kwargs["data"]["area_name"], "경기 시군구 읍면동")

    async def test_validation_failure_preserves_entry(self):
        await self.choose_province()
        self.api.async_get_safety_alerts.side_effect = ValueError("invalid board")
        result = await self.flow.async_step_sgg({"sgg_code": ""})
        self.assertEqual(result["reason"], "cannot_connect")
        self.manager.async_update_entry.assert_not_called()
        self.manager.async_reload.assert_not_awaited()

    async def test_duplicate_preserves_entry(self):
        await self.choose_province()
        self.manager.async_entries.return_value.append(SimpleNamespace(entry_id="other", data={"area_code": "41"}))
        result = await self.flow.async_step_sgg({"sgg_code": ""})
        self.assertEqual(result["reason"], "already_configured")
        self.manager.async_update_entry.assert_not_called()

    async def test_region_failure_preserves_entry(self):
        self.regions.async_get_sgg_list.return_value = None
        await self.flow.async_step_init()
        result = await self.flow.async_step_init({"sido_code": "41"})
        self.assertEqual(result["reason"], "cannot_connect")
        self.manager.async_update_entry.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
