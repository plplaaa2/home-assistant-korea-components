"""Offline regression checks using real safety-alert classes with dependency stubs.

Related files: both safety-alert api.py, device.py, exceptions.py and sensor.py implementations.
Run: python tools/test_safety_alert_fallback.py
"""

from __future__ import annotations

import ast
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATIONS = (
    "custom_components/korea_incubator/safety_alert",
    "custom_components/korea_safety",
)
# The standalone integration is optional local work and may not be tracked yet.
IMPLEMENTATIONS = tuple(base for base in IMPLEMENTATIONS if (ROOT / base).is_dir())
NORMAL = """
<div class="board-count"><span>1</span></div>
<div class="board-listarea"><table><tbody><tr>
<td>기타</td><td><a>기존 재난문자</a>
<p>발송일시 : 2026/09/26 17:00:38 ㆍ 긴급단계 : 안전안내 ㆍ 송출지역 : 서울특별시</p>
</td></tr></tbody></table></div>
"""
EMPTY = """
<div class="board-count"><span>0</span></div>
<div class="board-listarea"><table><tbody><tr>
<td colspan="2">조회된 데이터가 없습니다.</td>
</tr></tbody></table></div>
"""
EMERGENCY = """
<html><title>국민안전24</title><body>
민방공 경보발령으로 인한 서비스 이용 폭주로 긴급서비스 페이지로 전환 되었습니다.
상황 해제 또는 사용자가 감소전까지 서비스 이용이 제한됩니다.
</body></html>
"""


class UpdateFailed(Exception):
    """Stand-in for the unavailable Home Assistant runtime dependency."""


def load_classes(base):
    """Compile unchanged production class bodies, stubbing only external dependencies."""
    namespace = {
        "datetime": datetime, "timedelta": timedelta,
        "Dict": Dict, "Any": Any, "List": List, "Optional": Optional,
        "BeautifulSoup": BeautifulSoup,
        "re": re,
        "LOGGER": logging.getLogger("safety_fallback_test"),
        "TZ_ASIA_SEOUL": ZoneInfo("Asia/Seoul"),
        "UpdateFailed": UpdateFailed,
    }
    for name in ("exceptions.py", "api.py", "device.py"):
        path = ROOT / base / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = [
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        ]
        nodes.extend(
            n for n in tree.body
            if isinstance(n, ast.ClassDef)
            or (isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("_BASE_URL", "_HEADERS")
                for t in n.targets
            ))
        )
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                     str(path), "exec"), namespace)
    return namespace


class FallbackTests(unittest.TestCase):
    def test_normal_and_true_empty(self):
        for base in IMPLEMENTATIONS:
            with self.subTest(base=base):
                ns = load_classes(base)
                client = ns["SafetyAlertApiClient"]()
                normal = client._parse_html(NORMAL)
                self.assertEqual(normal["rtnResult"]["totCnt"], 1)
                alert = normal["disasterSmsList"][0]
                self.assertEqual(alert["MSG_CN"], "기존 재난문자")
                self.assertEqual(alert["REGIST_DT"], "2026/09/26 17:00:38")
                self.assertEqual(alert["EMRGNCY_STEP_NM"], "안전안내")
                self.assertEqual(client._parse_html(EMPTY),
                                 {"disasterSmsList": [], "rtnResult": {"totCnt": 0}})

    def test_emergency_and_invalid_responses(self):
        for base in IMPLEMENTATIONS:
            with self.subTest(base=base):
                ns = load_classes(base)
                client = ns["SafetyAlertApiClient"]()
                with self.assertRaises(ns["SafetyAlertServiceUnavailable"]):
                    client._parse_html(EMERGENCY)
                for html in (
                    "<html>Maintenance</html>",
                    EMPTY.replace("<span>0", "<span>invalid"),
                    EMPTY.replace("<span>0", "<span>5"),
                    NORMAL.replace("<a>기존 재난문자</a>", ""),
                    NORMAL.replace("<span>1", "<span>0"),
                ):
                    with self.assertRaises(ns["SafetyAlertDataError"]):
                        client._parse_html(html)

    def test_http_200_emergency_exception_is_preserved(self):
        async def scenario(base):
            ns = load_classes(base)
            session = SimpleNamespace(get=AsyncMock(
                return_value=SimpleNamespace(status_code=200, text=EMERGENCY)))
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=session)
            context.__aexit__ = AsyncMock(return_value=False)
            ns["curl_cffi"] = SimpleNamespace(AsyncSession=lambda **kwargs: context)
            with self.assertRaises(ns["SafetyAlertServiceUnavailable"]):
                await ns["SafetyAlertApiClient"]().async_get_safety_alerts()
        for base in IMPLEMENTATIONS:
            with self.subTest(base=base):
                asyncio.run(scenario(base))

    def test_cache_survives_emergency_and_recovers(self):
        async def scenario(base, initial_html):
            ns = load_classes(base)
            client = ns["SafetyAlertApiClient"]()
            device = ns["SafetyAlertDevice"](None, "test", "1100000000", "불광동")
            api = AsyncMock()
            device.api_client = api
            initial = client._parse_html(initial_html)
            api.async_get_safety_alerts.return_value = initial
            await device.async_update()
            snapshot = deepcopy(device.data)
            success = device._last_update_success
            api.async_get_safety_alerts.side_effect = ns["SafetyAlertServiceUnavailable"]("Emergency")
            for _ in range(2):
                await device.async_update()
                self.assertTrue(device.available)
                self.assertTrue(device.data["data_stale"])
                self.assertEqual(device.data["parsed_data"], snapshot["parsed_data"])
                self.assertEqual(device.data["metadata"], snapshot["metadata"])
                self.assertEqual(device.data["last_updated"], snapshot["last_updated"])
                self.assertEqual(device._last_update_success, success)
            api.async_get_safety_alerts.side_effect = None
            api.async_get_safety_alerts.return_value = client._parse_html(NORMAL)
            await device.async_update()
            self.assertFalse(device.data["data_stale"])
            self.assertIsNone(device.data["update_error"])
            successful_data = deepcopy(device.data["parsed_data"])
            api.async_get_safety_alerts.side_effect = ns["SafetyAlertDataError"](
                "Safety Alert response is missing the SMS board")
            await device.async_update()
            self.assertTrue(device.data["data_stale"])
            self.assertTrue(device.available)
            self.assertEqual(device.data["parsed_data"], successful_data)
            api.async_get_safety_alerts.side_effect = None
            api.async_get_safety_alerts.return_value = client._parse_html(EMPTY)
            await device.async_update()
            self.assertEqual(device.data["parsed_data"]["data"], [])
            self.assertFalse(device.data["data_stale"])
        for base in IMPLEMENTATIONS:
            for initial in (NORMAL, EMPTY):
                with self.subTest(base=base, initial=initial):
                    asyncio.run(scenario(base, initial))

    def test_emergency_without_cache_and_other_errors(self):
        async def scenario(base):
            ns = load_classes(base)
            device = ns["SafetyAlertDevice"](None, "test", "1100000000", "불광동")
            device.api_client = AsyncMock()
            for error in (
                ns["SafetyAlertServiceUnavailable"]("Emergency"),
                ns["SafetyAlertDataError"]("Invalid board"),
                ns["SafetyAlertConnectionError"]("HTTP 500"),
            ):
                device.api_client.async_get_safety_alerts.side_effect = error
                with self.assertRaises(UpdateFailed):
                    await device.async_update()
                self.assertFalse(device.available)
                self.assertIsNone(device._last_update_success)
        for base in IMPLEMENTATIONS:
            with self.subTest(base=base):
                asyncio.run(scenario(base))

    def test_sensor_freshness_attributes(self):
        for base in IMPLEMENTATIONS:
            with self.subTest(base=base):
                ns = load_classes(base)
                ns["CoordinatorEntity"] = type("CoordinatorEntity", (), {})
                ns["SensorEntity"] = type("SensorEntity", (), {})
                ns["SensorDeviceClass"] = SimpleNamespace(
                    DATE="date", TIMESTAMP="timestamp")
                if "korea_incubator" in base:
                    path = ROOT / "custom_components/korea_incubator/sensor.py"
                    names = ("KoreaSensor",)
                    sensor_name = "KoreaSensor"
                else:
                    path = ROOT / base / "sensor.py"
                    names = ("_SafetySensor", "SafetyAlertMessageSensor")
                    sensor_name = "SafetyAlertMessageSensor"
                tree = ast.parse(path.read_text(encoding="utf-8"))
                nodes = [ast.ImportFrom(
                    module="__future__", names=[ast.alias(name="annotations")], level=0)]
                nodes.extend(n for n in tree.body
                             if isinstance(n, ast.ClassDef) and n.name in names)
                exec(compile(ast.fix_missing_locations(ast.Module(
                    body=nodes, type_ignores=[])), str(path), "exec"), ns)
                sensor = object.__new__(ns[sensor_name])
                sensor._device = ns["SafetyAlertDevice"](
                    None, "test", "1100000000", "불광동")
                data = {
                    "data_stale": True,
                    "last_updated": "2026-10-01T20:00:00+09:00",
                    "update_error": "Emergency",
                }
                sensor.coordinator = SimpleNamespace(data=data)
                self.assertEqual(sensor.extra_state_attributes, {
                    "data_stale": True,
                    "last_successful_update": data["last_updated"],
                    "update_error": "Emergency",
                })
                data["data_stale"] = False
                data["update_error"] = None
                self.assertFalse(sensor.extra_state_attributes["data_stale"])
                self.assertIsNone(sensor.extra_state_attributes["update_error"])

    def test_standalone_timestamp_values(self):
        base = "custom_components/korea_safety"
        if base not in IMPLEMENTATIONS:
            self.skipTest("Standalone integration is not present in this checkout")
        ns = load_classes(base)
        ns["CoordinatorEntity"] = type("CoordinatorEntity", (), {})
        ns["SensorEntity"] = type("SensorEntity", (), {})
        ns["SensorDeviceClass"] = SimpleNamespace(TIMESTAMP="timestamp")
        ns["ZoneInfo"] = ZoneInfo
        path = ROOT / base / "sensor.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
        sensor = object.__new__(ns["SafetyAlertMessageSensor"])
        sensor._attr_device_class = "timestamp"
        sensor._field = "REGIST_DT"
        def set_alert(value):
            sensor.coordinator = SimpleNamespace(
                data={"parsed_data": {"data": [{"REGIST_DT": value}]}})
        for raw in ("2026/09/26 17:00:38", " 2026/09/26 17:00:38 "):
            with self.subTest(raw=raw):
                set_alert(raw)
                value = sensor.native_value
                self.assertIsInstance(value, datetime)
                self.assertIsNotNone(value.tzinfo)
                self.assertEqual(value.utcoffset(), timedelta(hours=9))
                self.assertEqual(value.isoformat(), "2026-09-26T17:00:38+09:00")
        for raw in ("", " ", None, "invalid", "2026/02/30 17:00:38", 123):
            with self.subTest(raw=raw):
                set_alert(raw)
                self.assertIsNone(sensor.native_value)
        sensor.coordinator = SimpleNamespace(data={})
        self.assertIsNone(sensor.native_value)
        sensor.coordinator = SimpleNamespace(data=None)
        self.assertIsNone(sensor.native_value)
        sensor._attr_device_class = None
        sensor._field = "MSG_CN"
        sensor.coordinator = SimpleNamespace(
            data={"parsed_data": {"data": [{"MSG_CN": "기존 알림"}]}})
        self.assertEqual(sensor.native_value, "기존 알림")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main(verbosity=2)
