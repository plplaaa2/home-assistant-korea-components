"""Constants for the standalone Korea Safety integration."""

from logging import getLogger
import pytz
from homeassistant.const import Platform

DOMAIN = "korea_safety"
LOGGER = getLogger(__package__)
TZ_ASIA_SEOUL = pytz.timezone("Asia/Seoul")
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
UPDATE_INTERVAL_MINUTES = 5
