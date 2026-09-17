from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_translate_state
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN
from custom_components.immich_frames.api import ImmichApiError


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_basic_setup_registers_entities_and_caches_image(hass, asset, jpeg):
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
        assert hass.states.get("image.immich_frame_frame") is not None
        assert hass.states.get("sensor.immich_frame_photo_filename").state == "a.jpg"
        assert await hass.config_entries.async_unload(entry.entry_id)
    # A server outage after restart should restore the cached image and metadata.
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.data[DOMAIN][entry.entry_id].data.using_cache
        assert hass.states.get("sensor.immich_frame_photo_filename").state == "a.jpg"
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
async def test_metadata_switch_updates_sensors_and_interval_survives_reload(hass, asset, jpeg):
    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            return [asset, {**asset, "id": "portrait-b", "originalFileName": "b.jpg"}]
        return jpeg

    entry = MockConfigEntry(domain=DOMAIN, title="Immich Frame", data={
        "url": "http://immich.test", "api_key": "test-key", "mode": "pairs", "pairs_only": True,
    })
    entry.add_to_hass(hass)
    # Simulate upgrading an existing frame: its entity ID and service options stay valid.
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "select", DOMAIN, f"{entry.entry_id}_metadata_role", config_entry=entry,
        suggested_object_id="immich_frame_metadata_photo", original_name="Metadata photo",
    )
    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        select_entry = registry.async_get("select.immich_frame_metadata_photo")
        assert select_entry.original_name == "Show photo details for"
        assert select_entry.translation_key == "metadata_role"
        label = async_translate_state(hass, "secondary", "select", DOMAIN, select_entry.translation_key, None)
        assert label == "Right photo in a pair"
        await hass.services.async_call("select", "select_option", {
            "entity_id": "select.immich_frame_metadata_photo", "option": "secondary",
        }, blocking=True)
        assert hass.states.get("sensor.immich_frame_photo_filename").state == "b.jpg"
        await hass.services.async_call("number", "set_value", {
            "entity_id": "number.immich_frame_slide_interval", "value": 90,
        }, blocking=True)
        assert entry.data["interval"] == 90
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("number.immich_frame_slide_interval").state == "90"
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
