"""Diagnostics for EspControl Immich Companion."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return safe support information without image bytes or credentials."""
    coordinator = getattr(entry, "runtime_data", None)
    snapshot = getattr(coordinator, "data", None)
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "runtime": {
            "connected": getattr(snapshot, "connected", None),
            "using_cache": getattr(snapshot, "using_cache", None),
            "status": getattr(snapshot, "status", None),
            "generation": getattr(snapshot, "generation", None),
            "matching_assets": getattr(snapshot, "matching_assets", None),
            "layout": getattr(snapshot, "layout", None),
        },
    }
