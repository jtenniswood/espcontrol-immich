from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApiError
from custom_components.immich_frames.const import DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("online", [True, False])
async def test_upgrade_removes_only_this_frames_coordinate_sensors(hass, asset, jpeg, online):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={"url": "http://immich.test", "api_key": "key"})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    retired = [registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_photo_{axis}", config_entry=entry,
        suggested_object_id=f"custom_{axis}",
    ).entity_id for axis in ("latitude", "longitude")]
    location = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_photo_location", config_entry=entry,
        suggested_object_id="custom_location",
    ).entity_id
    unrelated = registry.async_get_or_create(
        "sensor", DOMAIN, "different_frame_photo_latitude", suggested_object_id="other_latitude",
    ).entity_id

    async def request(_api, method, path, **kwargs):
        if not online:
            raise ImmichApiError("Offline")
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id) is online
        await hass.async_block_till_done()
        assert all(registry.async_get(entity_id) is None for entity_id in retired)
        assert all(hass.states.get(entity_id) is None for entity_id in retired)
        assert registry.async_get(location) is not None
        assert registry.async_get(unrelated) is not None
        if online:
            assert hass.states.get(location).state == "Bath"
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert not any(e.unique_id.endswith(("_photo_latitude", "_photo_longitude"))
                           for e in er.async_entries_for_config_entry(registry, entry.entry_id))
            assert await hass.config_entries.async_unload(entry.entry_id)
