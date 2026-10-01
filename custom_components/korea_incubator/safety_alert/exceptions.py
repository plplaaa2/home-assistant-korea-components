"""Exceptions for Safety Alert integration."""


class SafetyAlertError(Exception):
    """Base exception for Safety Alert integration."""


class SafetyAlertConnectionError(SafetyAlertError):
    """Connection error with Safety Alert API."""


class SafetyAlertDataError(SafetyAlertError):
    """Data parsing error with Safety Alert API."""


# Preserve cached alerts during emergency-page responses; related: api.py, device.py.
class SafetyAlertServiceUnavailable(SafetyAlertDataError):
    """The site temporarily serves its emergency page instead of the SMS board."""
