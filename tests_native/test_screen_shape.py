"""Screen shape affects rendering independently of photo selection."""
import json
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError
from custom_components.immich_frames.const import DOMAIN

SHAPES = [("landscape", "Landscape (16:10, 1280 × 800)", (1280, 800)),
          ("portrait", "Portrait (10:16, 800 × 1280)", (800, 1280)),
          ("square", "Square (1:1, 720 × 720)", (720, 720))]


@pytest.mark.parametrize("shape,label,size", SHAPES)
@pytest.mark.parametrize("paired", [False, True])
async def test_snapshot_uses_screen_shape_without_filtering_photos(asset, jpeg, shape, label, size, paired):
    api = ImmichApi("http://immich.test", "key")
    assets = [asset, {**asset, "id": "second"}] if paired else [asset]
    api._request = AsyncMock(side_effect=[assets, *([jpeg] * len(assets))])
    snapshot = await api.snapshot({"screen_shape": shape, "mode": "pairs" if paired else "single"}, 1, set())
    assert Image.open(BytesIO(snapshot.image)).size == size
    assert snapshot.layout == ("side_by_side" if paired else "single")
    assert [photo["id"] for photo in snapshot.photos] == [a["id"] for a in assets]
    assert api._request.call_args_list[0].kwargs["json"]["filter"] == {
        "type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"eq": "timeline"},
    }


@pytest.mark.parametrize("shape,label,size", SHAPES)
@pytest.mark.parametrize("paired", [False, True])
def test_render_keeps_whole_photo_proportions_and_pair_order(shape, label, size, paired):
    # Wide photos leave visible black padding, even when placed into a portrait tile.
    payloads = []
    for color in (["red", "blue"] if paired else ["red"]):
        output = BytesIO()
        Image.new("RGB", (800, 400), color).save(output, "PNG")
        payloads.append(output.getvalue())
    output, _ = ImmichApi._render([], payloads, shape)
    image = Image.open(BytesIO(output))
    width, height = size
    tile_width = width // len(payloads)
    for index in range(len(payloads)):
        center = (index * tile_width + tile_width // 2, height // 2)
        pixel = image.getpixel(center)
        assert pixel[0 if index == 0 else 2] > 240
        scaled_height = min(400, tile_width // 2)
        assert max(image.getpixel((center[0], (height - scaled_height) // 2 - 10))) < 10
    assert image.size == size


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("shape,label,size", SHAPES)
@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
async def test_screen_shape_saved_and_prefilled_on_all_edit_routes(hass, shape, label, size, route):
    if route == "setup":
        manager = hass.config_entries.flow
        with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
            result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
                "url": "http://immich.test", "api_key": "key",
            })
        result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    else:
        entry = MockConfigEntry(domain=DOMAIN, title="Frame", unique_id="http://immich.test|Frame", data={
            "url": "http://immich.test", "api_key": "key", "frame_name": "Frame", "source": "all", "screen_shape": shape,
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
    assert result["data_schema"]({})["screen_shape"] == ("Landscape (16:10, 1280 × 800)" if route == "setup" else label)
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await manager.async_configure(result["flow_id"], {"screen_shape": label})
        await hass.async_block_till_done()
    saved = result["data"] if route == "setup" else entry.data
    assert saved["screen_shape"] == shape
    assert saved["orientation"] == "any"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_shape_change_reloads_image_and_rejects_old_cache(hass, asset, jpeg):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "all",
    })
    entry.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        manager = hass.config_entries.options
        result = await manager.async_init(entry.entry_id)
        result = await manager.async_configure(result["flow_id"], {"next_step_id": "display"})
        # A failing server must not bring back the old landscape cache after saving portrait.
        with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
            await manager.async_configure(result["flow_id"], {"screen_shape": "Portrait (10:16, 800 × 1280)"})
            await hass.async_block_till_done()
            assert entry.entry_id not in hass.data[DOMAIN]
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert Image.open(BytesIO(hass.data[DOMAIN][entry.entry_id].data.image)).size == (800, 1280)
        assert await hass.config_entries.async_unload(entry.entry_id)
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        snapshot = hass.data[DOMAIN][entry.entry_id].data
        assert snapshot.using_cache
        assert Image.open(BytesIO(snapshot.image)).size == (800, 1280)
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("old_size", [None, [1920, 1080]])
async def test_old_output_size_cache_is_rejected_after_upgrade(hass, asset, jpeg, old_size):
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
        state_path = coordinator.cache_path.with_suffix(".json")
        state = json.loads(state_path.read_text())
        assert state["output_size"] == [1280, 800]
        assert await hass.config_entries.async_unload(entry.entry_id)

    # Simulate a cache written by an older integration with the same shape name.
    if old_size is None:
        state.pop("output_size")
    else:
        state["output_size"] = old_size
    state_path.write_text(json.dumps(state))
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.entry_id not in hass.data[DOMAIN]
