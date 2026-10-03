"""Standalone Korean emergency safety alert integration."""

from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, PLATFORMS, UPDATE_INTERVAL_MINUTES
from .device import SafetyAlertDevice
from .exceptions import SafetyAlertConnectionError, SafetyAlertDataError


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one configured safety-alert region."""
    device = SafetyAlertDevice(
        hass,
        entry.entry_id,
        entry.data["area_code"],
        entry.data["area_name"],
        entry.data.get("area_code2"),
        entry.data.get("area_code3"),
        aiohttp.ClientSession(),
    )

    async def async_update_data() -> dict[str, Any]:
        try:
            await device.async_update()
            return device.data
        except (SafetyAlertConnectionError, SafetyAlertDataError) as err:
            raise UpdateFailed(f"Safety alert API error: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await device.async_close_session()
        raise

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "device": device,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a safety-alert config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
        if device := data.get("device"):
            await device.async_close_session()
    return unload_ok
