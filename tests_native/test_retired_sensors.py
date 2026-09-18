from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApiError
from custom_components.immich_frames.const import DOMAIN

RETIRED = (
    ("sensor", "photo_latitude"), ("sensor", "photo_longitude"), ("sensor", "photo_filename"),
    ("sensor", "slide"), ("sensor", "status"), ("binary_sensor", "using_cache"),
    ("sensor", "matching_assets"), ("binary_sensor", "immich_connected"),
    ("select", "metadata_role"), ("switch", "pairs_only"), ("button", "refresh"),
)


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("online", [True, False])
async def test_upgrade_removes_only_this_frames_retired_entities(hass, asset, jpeg, online):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={"url": "http://immich.test", "api_key": "key", "pairs_only": True})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    retired = [registry.async_get_or_create(
        domain, DOMAIN, f"{entry.entry_id}_{key}", config_entry=entry,
        suggested_object_id=f"custom_{key}",
    ).entity_id for domain, key in RETIRED]
    location = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_photo_location", config_entry=entry,
        suggested_object_id="custom_location",
    ).entity_id
    unrelated = registry.async_get_or_create(
        "sensor", DOMAIN, "different_frame_photo_latitude", suggested_object_id="other_latitude",
    ).entity_id
    other_domain = registry.async_get_or_create(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_status", config_entry=entry,
        suggested_object_id="unrelated_status",
    ).entity_id

    async def request(_api, method, path, **kwargs):
        if not online:
            raise ImmichApiError("Offline")
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id) is online
        await hass.async_block_till_done()
        assert "pairs_only" not in entry.data
        assert all(registry.async_get(entity_id) is None for entity_id in retired)
        assert all(hass.states.get(entity_id) is None for entity_id in retired)
        assert registry.async_get(location) is not None
        assert registry.async_get(unrelated) is not None
        assert registry.async_get(other_domain) is not None
        if online:
            assert hass.states.get(location).state == "Bath"
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            retired_keys = {(domain, f"{entry.entry_id}_{key}") for domain, key in RETIRED}
            assert not any((e.domain, e.unique_id) in retired_keys
                           for e in er.async_entries_for_config_entry(registry, entry.entry_id))
            assert hass.states.get("binary_sensor.frame_immich_connected") is None
            assert hass.states.get("sensor.frame_matching_assets") is None
            assert await hass.config_entries.async_unload(entry.entry_id)
