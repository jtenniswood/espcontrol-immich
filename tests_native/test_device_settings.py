"""Device settings drive real selection/rendering and survive reloads."""
from io import BytesIO
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.translation import async_translate_state
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApiError
from custom_components.immich_frames.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def frame(hass, **settings):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "all", **settings,
    })
    entry.add_to_hass(hass)
    return entry


async def set_value(hass, entry, domain, key, value):
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    if domain == "switch":
        service, data = ("turn_on" if value else "turn_off"), {}
    else:
        service = "select_option" if domain == "select" else "set_value"
        data = {"option" if domain == "select" else "value": value}
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()
    return entity_id


async def test_device_settings_change_photos_fit_and_pairing_then_restore(hass, asset, jpeg):
    entry = frame(hass)
    # Two portraits three days apart, plus one landscape and one square.
    assets = [asset, {**asset, "id": "b", "localDateTime": "2026-09-20T12:00:00Z"},
              {**asset, "id": "wide", "width": 200, "height": 100},
              {**asset, "id": "square", "width": 100, "height": 100}]

    async def request(_api, method, path, **kwargs):
        return assets if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        expected = {
            ("select", "photo_fit"): "Photo fit", ("select", "mode"): "Display mode",
            ("select", "orientation"): "Photo orientation", ("number", "pair_window_days"): "Pairing window",
        }
        assert registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_pairs_only") is None
        entity_ids = {item.entity_id for item in er.async_entries_for_config_entry(registry, entry.entry_id)}
        for (domain, key), name in expected.items():
            entity = registry.async_get(registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}"))
            assert entity.entity_category == EntityCategory.CONFIG
            assert entity.original_name == name
        assert async_translate_state(hass, "pairs", "select", DOMAIN, "mode", None) == "Pair portrait photos"
        assert async_translate_state(hass, "crop", "select", DOMAIN, "photo_fit", None) == "Crop to fit"
        assert async_translate_state(hass, "any", "select", DOMAIN, "orientation", None) == "Mixed (landscapes and portraits)"

        # The JPEG visibly changes between full-image padding and edge-to-edge crop.
        data = hass.data[DOMAIN][entry.entry_id].data
        assert Image.open(BytesIO(data.image)).getpixel((0, 400))[2] < 150
        await set_value(hass, entry, "select", "photo_fit", "crop")
        assert Image.open(BytesIO(hass.data[DOMAIN][entry.entry_id].data.image)).getpixel((0, 400))[2] > 240
        await set_value(hass, entry, "select", "mode", "pairs")
        assert hass.data[DOMAIN][entry.entry_id].data.layout == "single"
        await set_value(hass, entry, "number", "pair_window_days", 3)
        assert hass.data[DOMAIN][entry.entry_id].data.layout == "side_by_side"
        # Landscape photos still appear on their own in pair mode.
        for orientation, expected_id in [("landscape", "wide"), ("portrait", asset["id"])]:
            await set_value(hass, entry, "select", "orientation", orientation)
            assert hass.data[DOMAIN][entry.entry_id].data.primary["id"] == expected_id
        assert hass.data[DOMAIN][entry.entry_id].data.layout == "side_by_side"
        await set_value(hass, entry, "number", "interval", 75)
        assert entry.data["interval"] == 75
        assert entry.data["pair_window_days"] == 3
        assert entry.data["mode"] == "pairs"
        assert entry.data["photo_fit"] == "crop"
        assert entry.data["orientation"] == "portrait"
        assert {item.entity_id for item in er.async_entries_for_config_entry(registry, entry.entry_id)} == entity_ids

        # Configure reads the values chosen on the device page.
        manager = hass.config_entries.options
        result = await manager.async_init(entry.entry_id)
        result = await manager.async_configure(result["flow_id"], {"next_step_id": "display"})
        assert result["data_schema"]({})["mode"] == "Pair portrait photos"
        result = await manager.async_configure(result["flow_id"], {})
        assert result["data_schema"]({})["photo_fit"] == "crop"
        assert result["data_schema"]({})["orientation"] == "Portrait photos only"
        assert result["data_schema"]({})["interval"] == 75
        result = await manager.async_configure(result["flow_id"], {})
        assert result["data_schema"]({})["pair_window_days"] == 3
        manager.async_abort(result["flow_id"])
        assert await hass.config_entries.async_unload(entry.entry_id)
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.data[DOMAIN][entry.entry_id].data.using_cache
        assert hass.data[DOMAIN][entry.entry_id].data.layout == "side_by_side"
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("domain,key,value", [
    ("select", "mode", "pairs"), ("select", "orientation", "landscape"),
    ("select", "photo_fit", "crop"),
    ("number", "pair_window_days", 7),
])
async def test_changed_settings_do_not_restore_incompatible_cached_photos(hass, asset, jpeg, domain, key, value):
    entry = frame(hass)

    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        await set_value(hass, entry, domain, key, value)
        assert entry.data[key] == value
        assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.parametrize("mode,fit", [("single", "show_full"), ("pairs", "crop")])
async def test_legacy_mode_change_preserves_fit_and_invalid_window_is_rejected(hass, asset, jpeg, mode, fit):
    entry = frame(hass, mode=mode)

    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await set_value(hass, entry, "select", "mode", "pairs" if mode == "single" else "single")
        assert entry.data["photo_fit"] == fit
        for invalid in [-1, 8]:
            with pytest.raises(HomeAssistantError):
                await set_value(hass, entry, "number", "pair_window_days", invalid)
        assert "pair_window_days" not in entry.data
        assert await hass.config_entries.async_unload(entry.entry_id)
