"""Legacy shape settings cannot bypass the fixed output frame."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError
from custom_components.immich_frames.const import DOMAIN

SHAPES = [("landscape", "Landscape (16:9)", (1280, 800)),
          ("portrait", "Portrait (9:16)", (1280, 800)),
          ("square", "Square (1:1)", (1280, 800))]


@pytest.mark.parametrize("shape,label,size", SHAPES)
@pytest.mark.parametrize("paired", [False, True])
async def test_legacy_screen_shape_does_not_change_output_or_photo_selection(asset, jpeg, shape, label, size, paired):
    api = ImmichApi("http://immich.test", "key")
    assets = [asset, {**asset, "id": "second"}] if paired else [asset]
    api._request = AsyncMock(side_effect=[assets, *([jpeg] * len(assets))])
    snapshot = await api.snapshot({"screen_shape": shape, "mode": "pairs" if paired else "single"}, 1, set())
    assert Image.open(BytesIO(snapshot.image)).size == ((1280, 800) if paired else size)
    assert snapshot.layout == ("side_by_side" if paired else "single")
    assert [photo["id"] for photo in snapshot.photos] == [a["id"] for a in assets]
    assert api._request.call_args_list[0].kwargs["json"]["filter"] == {
        "type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"eq": "timeline"},
    }


@pytest.mark.parametrize("shape,label,size", SHAPES)
@pytest.mark.parametrize("paired", [False, True])
def test_render_preserves_single_padding_and_fills_pairs_in_order(shape, label, size, paired):
    # Wide photos leave visible black padding, even when placed into a portrait tile.
    payloads = []
    for color in (["red", "blue"] if paired else ["red"]):
        output = BytesIO()
        Image.new("RGB", (800, 400), color).save(output, "PNG")
        payloads.append(output.getvalue())
    output, _ = ImmichApi._render([], payloads)
    image = Image.open(BytesIO(output))
    size = (1280, 800) if paired else size
    width, height = size
    tile_width = width // len(payloads)
    for index in range(len(payloads)):
        center = (index * tile_width + tile_width // 2, height // 2)
        pixel = image.getpixel(center)
        assert pixel[0 if index == 0 else 2] > 240
        if paired:
            assert image.getpixel((center[0], 0))[0 if index == 0 else 2] > 240
            assert image.getpixel((center[0], height - 1))[0 if index == 0 else 2] > 240
        else:
            scaled_height = min(400, tile_width // 2)
            assert max(image.getpixel((center[0], (height - scaled_height) // 2 - 10))) < 10
    if paired:
        for y in range(height):
            assert max(image.getpixel((640, y))) < 10
            assert image.getpixel((639, y))[0] > 240
            assert image.getpixel((641, y))[2] > 240
    assert image.size == size


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("shape,label,size", SHAPES)
@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
async def test_obsolete_output_settings_removed_on_all_edit_routes(hass, shape, label, size, route):
    if route == "setup":
        manager = hass.config_entries.flow
        with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
            result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
                "url": "http://immich.test", "api_key": "key",
            })
        result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    else:
        entry = MockConfigEntry(domain=DOMAIN, title="Frame", unique_id="http://immich.test|Frame", data={
            "url": "http://immich.test", "api_key": "key", "frame_name": "Frame", "source": "all", "screen_shape": shape, "original_aspect_ratio": True,
        })
        entry.add_to_hass(hass)
        if route == "options":
            manager = hass.config_entries.options
            result = await manager.async_init(entry.entry_id)
            result = await manager.async_configure(result["flow_id"], {"next_step_id": "display"})
        else:
            manager = hass.config_entries.flow
            result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
            result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    assert "screen_shape" not in result["data_schema"]({})
    assert "original_aspect_ratio" not in result["data_schema"]({})
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await manager.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    saved = result["data"] if route == "setup" else entry.data
    assert "screen_shape" not in saved
    assert "original_aspect_ratio" not in saved
    assert saved["orientation"] == "any"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("cached_size", [(1920, 1080), (1080, 1920), (300, 300), (1600, 1000), (1280, 800)])
async def test_restart_only_restores_cache_with_current_dimensions(hass, asset, jpeg, cached_size):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "all",
    })
    entry.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]
        cache_path = coordinator.cache_path.with_suffix(".jpg")
        assert await hass.config_entries.async_unload(entry.entry_id)
    # Simulate an image left by an older renderer while preserving its metadata.
    Image.new("RGB", cached_size, "blue").save(cache_path, "JPEG")
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        ready = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        if cached_size == (1280, 800):
            assert ready
            snapshot = hass.data[DOMAIN][entry.entry_id].data
            assert snapshot.using_cache
            assert Image.open(BytesIO(snapshot.image)).size == (1280, 800)
            assert await hass.config_entries.async_unload(entry.entry_id)
        else:
            assert not ready
            assert entry.entry_id not in hass.data[DOMAIN]
