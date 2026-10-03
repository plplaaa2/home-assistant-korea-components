"""Binary sensor for recent safety alerts."""

from datetime import datetime, timedelta
import pytz
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from .const import DOMAIN, TZ_ASIA_SEOUL


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SafetyAlertBinarySensor(data["coordinator"], data["device"])])


class SafetyAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "새 안전알림"
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_has_entity_name = True

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.unique_id}_new"
        self._attr_device_info = device.device_info

    @property
    def available(self) -> bool:
        return self._device.available and self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        alerts = (self.coordinator.data or {}).get("parsed_data", {}).get("data", [])
        if not alerts:
            return False
        value = alerts[0].get("REGIST_DT", "")
        try:
            registered = datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ_ASIA_SEOUL)
            return registered >= datetime.now(TZ_ASIA_SEOUL) - timedelta(minutes=10)
        except (TypeError, ValueError):
            return False

    @property
    def extra_state_attributes(self):
        return {"alerts": (self.coordinator.data or {}).get("parsed_data", {}).get("data", [])}
