"""Change rendered dimensions through the device's configuration selector."""
from io import BytesIO
from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.translation import async_translate_state
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApiError
from custom_components.immich_frames.const import DOMAIN
from tests_native.test_screen_shape import SHAPES


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("paired", [False, True])
async def test_output_size_control_saves_renders_and_survives_restart(hass, asset, jpeg, paired):
    original = {
        "url": "http://immich.test", "api_key": "key", "source": "all",
        "mode": "pairs" if paired else "single", "orientation": "any",
        "photo_fit": "show_full", "interval": 90,
    }
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data=original)
    entry.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            return [asset, {**asset, "id": "second"}] if paired else [asset]
        return jpeg

    registry = er.async_get(hass)
    # Renaming the control to Target display must preserve existing dashboard references.
    registry.async_get_or_create(
        "select", DOMAIN, f"{entry.entry_id}_output_size", config_entry=entry,
        suggested_object_id="frame_target_output_size", original_name="Target output size",
    )
    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_id = registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_output_size")
        assert entity_id == "select.frame_target_output_size"
        entity = registry.async_get(entity_id)
        assert entity.entity_category == EntityCategory.CONFIG
        assert entity.original_name == "Target display"
        device_id = entity.device_id
        assert hass.states.get(entity_id).state == "landscape"
        assert hass.states.get(entity_id).attributes["options"] == [
            "landscape", "jc1060p470", "jc4880p443", "square", "4848s040", "portrait",
        ]

        # Exercise actual service calls, including changing back to landscape.
        for shape, label, size in SHAPES[1:] + SHAPES[:1]:
            assert async_translate_state(hass, shape, "select", DOMAIN, entity.translation_key, None) == label
            previous = hass.data[DOMAIN][entry.entry_id]
            await hass.services.async_call("select", "select_option", {
                "entity_id": entity_id, "option": shape,
            }, blocking=True)
            await hass.async_block_till_done()
            coordinator = hass.data[DOMAIN][entry.entry_id]
            assert coordinator is not previous
            assert entry.data == {**original, "screen_shape": shape}
            assert hass.states.get(entity_id).state == shape
            assert registry.async_get(entity_id).device_id == device_id
            assert Image.open(BytesIO(coordinator.data.image)).size == size
            assert coordinator.data.layout == ("side_by_side" if paired else "single")
            assert len(coordinator.history) == 1
            with Image.open(coordinator.cache_path.with_suffix(".jpg")) as image:
                assert image.size == size

            # The Configure form reads the same persisted choice.
            result = await hass.config_entries.options.async_init(entry.entry_id)
            result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "display"})
            assert result["data_schema"]({})["screen_shape"] == label
            hass.config_entries.options.async_abort(result["flow_id"])

            # Each device preset must restore its own image after an offline restart.
            assert await hass.config_entries.async_unload(entry.entry_id)
            with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
                assert await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = hass.data[DOMAIN][entry.entry_id]
                assert hass.states.get(entity_id).state == shape
                assert coordinator.data.using_cache
                assert Image.open(BytesIO(coordinator.data.image)).size == size

        # Selecting the existing size should not restart the slideshow.
        await hass.services.async_call("select", "select_option", {
            "entity_id": entity_id, "option": "landscape",
        }, blocking=True)
        await hass.async_block_till_done()
        assert hass.data[DOMAIN][entry.entry_id] is coordinator
        assert await hass.config_entries.async_unload(entry.entry_id)

    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "landscape"
        assert hass.data[DOMAIN][entry.entry_id].data.using_cache
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("old,new,size", [
    ("landscape", "portrait", (800, 1280)),
    ("square", "4848s040", (480, 480)),
    ("landscape", "jc1060p470", (1024, 600)),
    ("portrait", "jc4880p443", (480, 800)),
])
async def test_output_size_control_rejects_old_cache_when_offline(hass, asset, jpeg, old, new, size):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "all",
        "screen_shape": old,
    })
    entry.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_output_size")
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        await hass.services.async_call("select", "select_option", {
            "entity_id": entity_id, "option": new,
        }, blocking=True)
        await hass.async_block_till_done()
        assert entry.data["screen_shape"] == new
        assert entry.entry_id not in hass.data[DOMAIN]
    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == new
        assert Image.open(BytesIO(hass.data[DOMAIN][entry.entry_id].data.image)).size == size
        assert await hass.config_entries.async_unload(entry.entry_id)
