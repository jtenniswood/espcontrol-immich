"""Upgrade and outage behavior through actual Home Assistant entry lifecycle."""
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import entity_registry as er, device_registry as dr

from custom_components.immich_frames.api import ImmichApi, ImmichApiError, NoMatchingPhotos
from custom_components.immich_frames.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.mark.parametrize("changes", [
    {"album_ids": ["b"]}, {"source": "smart", "smart_query": "mountains"},
    {"url": "http://other.test"}, {"api_key": "different-account"},
])
async def test_changed_source_or_account_cannot_restore_old_image_offline(hass, asset, jpeg, changes):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "album", "album_ids": ["a"],
    })
    entry.add_to_hass(hass)
    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg
    with patch.object(ImmichApi, "_request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.data.primary["id"] == asset["id"]
        assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, data={**entry.data, **changes})
    with patch.object(ImmichApi, "_request", side_effect=ImmichApiError("offline")):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert getattr(entry, "runtime_data", None) is None


async def test_version_one_upgrade_preserves_device_and_entity_identifiers(hass, asset, jpeg):
    entry = MockConfigEntry(domain=DOMAIN, title="Hall", version=1, data={
        "url": "http://immich.test", "api_key": "key", "source": "album", "album_id": "old-album",
        "screen_shape": "jc1060p470", "original_aspect_ratio": True, "mode": "pairs",
    })
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old_entity = registry.async_get_or_create("image", DOMAIN, f"{entry.entry_id}_image", config_entry=entry)
    old_device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)})
    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg
    with patch.object(ImmichApi, "_request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.version == 2
        assert entry.data["album_ids"] == ["old-album"]
        assert entry.data["screen_shape"] == "landscape"
        assert entry.data["photo_fit"] == "show_full"
        assert registry.async_get_entity_id("image", DOMAIN, f"{entry.entry_id}_image") == old_entity.entity_id
        assert {device.id for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)} == {old_device.id}
        coordinator = entry.runtime_data
        with patch.object(ImmichApi, "snapshot", side_effect=NoMatchingPhotos("No photos match this frame")):
            await coordinator.async_refresh()
            assert coordinator.data.status == "no_matching_photos"
            assert coordinator.data.connected
            assert coordinator.data.using_cache
        assert await hass.config_entries.async_unload(entry.entry_id)
