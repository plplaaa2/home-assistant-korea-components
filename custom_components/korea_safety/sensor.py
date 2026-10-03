"""Safety alert sensors."""

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device = data["device"]
    async_add_entities([
        SafetyAlertMessageSensor(coordinator, device, "message", "최근 알림 내용", "MSG_CN"),
        SafetyAlertMessageSensor(coordinator, device, "emergency_step", "최근 알림 단계", "EMRGNCY_STEP_NM"),
        SafetyAlertMessageSensor(coordinator, device, "disaster_type", "최근 재난 유형", "DSSTR_SE_NM"),
        SafetyAlertMessageSensor(coordinator, device, "registered_at", "최근 알림 일시", "REGIST_DT", SensorDeviceClass.TIMESTAMP),
    ])


class _SafetySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_device_info = device.device_info

    @property
    def available(self) -> bool:
        return self._device.available and self.coordinator.last_update_success

    # Expose cached-data freshness; related: api.py, device.py.
    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "data_stale": data.get("data_stale", False),
            "last_successful_update": data.get("last_updated"),
            "update_error": data.get("update_error"),
        }


class SafetyAlertMessageSensor(_SafetySensor):
    def __init__(self, coordinator, device, suffix: str, name: str, field: str, device_class=None) -> None:
        super().__init__(coordinator, device)
        self._attr_name = name
        self._field = field
        self._attr_device_class = device_class
        self._attr_unique_id = f"{device.unique_id}_{suffix}"

    @property
    def native_value(self):
        alerts = (self.coordinator.data or {}).get("parsed_data", {}).get("data", [])
        value = alerts[0].get(self._field) if alerts else None
        # Return aware datetimes for HA timestamp sensors; related: api.py, const.py.
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            if not isinstance(value, str) or not value.strip():
                return None
            try:
                return datetime.strptime(
                    value.strip(), "%Y/%m/%d %H:%M:%S"
                ).replace(tzinfo=ZoneInfo("Asia/Seoul"))
            except ValueError:
                return None
        return value
