from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN
from custom_components.immich_frames.api import ImmichApiError


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("favourite,expected", [(True, "Yes"), (False, "No"), (None, "")])
async def test_basic_setup_registers_entities_and_caches_image(hass, asset, jpeg, favourite, expected):
    if favourite is not None:
        asset = {**asset, "isFavorite": favourite}

    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            return [asset]
        if path == "/api/assets/portrait-a/thumbnail":
            return jpeg
        raise AssertionError(path)

    entry = MockConfigEntry(domain=DOMAIN, title="Immich Frame", data={
        "url": "http://immich.test", "api_key": "test-key", "source": "all",
    })
    entry.add_to_hass(hass)
    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.data.primary["id"] == asset["id"]
        assert coordinator.cache_path.with_suffix(".jpg").is_file()
        assert hass.states.get("image.immich_frame_image") is not None
        assert hass.states.get("sensor.immich_frame_filename") is None
        assert hass.states.get("sensor.immich_frame_date").state == "17 September, 2026"
        assert hass.states.get("sensor.immich_frame_favourite").state == expected
        # Check the states published to Home Assistant, including valid zero ratings.
        snapshot = coordinator.data
        coordinator.async_set_updated_data(replace(snapshot, photos=({"rating": 0},)))
        assert hass.states.get("sensor.immich_frame_rating").state == "0"
        coordinator.async_set_updated_data(replace(snapshot, photos=({},)))
        for name in ("date", "location", "people", "tags", "rating", "camera", "favourite"):
            assert hass.states.get(f"sensor.immich_frame_{name}").state == ""
        coordinator.async_set_updated_data(replace(snapshot, photos=({"captured": "invalid"},)))
        assert hass.states.get("sensor.immich_frame_date").state == ""
        coordinator.async_set_updated_data(snapshot)
        assert hass.states.get("sensor.immich_frame_filename") is None
        assert await hass.config_entries.async_unload(entry.entry_id)
    # A server outage after restart should restore the cached image and metadata.
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.data[DOMAIN][entry.entry_id].data.using_cache
        assert hass.states.get("sensor.immich_frame_filename") is None
        assert hass.states.get("sensor.immich_frame_date").state == "17 September, 2026"
        assert hass.states.get("sensor.immich_frame_favourite").state == expected
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_failed_setup_closes_api(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={"url": "http://immich.test", "api_key": "test-key"})
    entry.add_to_hass(hass)
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")), patch(
        "custom_components.immich_frames.api.ImmichApi.close"
    ) as close:
        assert not await hass.config_entries.async_setup(entry.entry_id)
        close.assert_awaited_once()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_pair_details_use_left_photo_and_interval_survives_reload(hass, asset, jpeg):
    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            return [{**asset, "isFavorite": False},
                    {**asset, "id": "portrait-b", "originalFileName": "b.jpg", "isFavorite": True, "exifInfo": {"city": "Bristol"}}]
        return jpeg

    entry = MockConfigEntry(domain=DOMAIN, title="Immich Frame", data={
        "url": "http://immich.test", "api_key": "test-key", "mode": "pairs",
    })
    entry.add_to_hass(hass)
    # Upgrading an existing frame removes even a renamed photo-details selector.
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "select", DOMAIN, f"{entry.entry_id}_metadata_role", config_entry=entry,
        suggested_object_id="immich_frame_metadata_photo", original_name="Metadata photo",
    )
    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert registry.async_get("select.immich_frame_metadata_photo") is None
        assert hass.states.get("select.immich_frame_metadata_photo") is None
        timer_entity_id = registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_interval")
        assert registry.async_get(timer_entity_id).entity_category == EntityCategory.CONFIG
        assert hass.states.get("sensor.immich_frame_location").state == "Bath"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.data.secondary["filename"] == "b.jpg"
        assert hass.states.get("sensor.immich_frame_filename") is None
        assert hass.states.get("sensor.immich_frame_favourite").state == "No"
        await hass.services.async_call("number", "set_value", {
            "entity_id": timer_entity_id, "value": 90,
        }, blocking=True)
        assert entry.data["interval"] == 90
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(timer_entity_id).state == "90"
        assert hass.states.get("sensor.immich_frame_filename") is None
        assert hass.states.get("sensor.immich_frame_favourite").state == "No"
        assert registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_metadata_role") is None
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_cache_write_failure_does_not_fail_setup(hass, asset, jpeg):
    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={"url": "http://immich.test", "api_key": "test-key"})
    entry.add_to_hass(hass)
    with patch("custom_components.immich_frames.api.ImmichApi._request", request), patch(
        "custom_components.immich_frames.coordinator.FrameCoordinator._write_cache", side_effect=OSError("Disk full")
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.data[DOMAIN][entry.entry_id].data.image
        assert await hass.config_entries.async_unload(entry.entry_id)
