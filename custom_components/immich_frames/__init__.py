from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import FrameCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Remove retired entities even when Immich is offline during this upgrade.
    registry = er.async_get(hass)
    retired_ids = {
        (domain, f"{entry.entry_id}_{key}")
        for domain, keys in {
            "sensor": ("photo_latitude", "photo_longitude", "slide", "status", "matching_assets"),
            "binary_sensor": ("using_cache", "immich_connected"),
            "select": ("metadata_role",),
        }.items()
        for key in keys
    }
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform == DOMAIN and (entity.domain, entity.unique_id) in retired_ids:
            registry.async_remove(entity.entity_id)
    coordinator = FrameCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await coordinator.async_close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()
    return unloaded
