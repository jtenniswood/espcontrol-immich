"""Unpadded single images keep their proportions within the output limits."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError
from custom_components.immich_frames.const import DOMAIN


def preview(size, *, orientation=None):
    data = BytesIO()
    image = Image.new("RGB", size, "red")
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(data, "JPEG", exif=exif)
    return data.getvalue()


@pytest.mark.parametrize("size", [(400, 200), (200, 400), (300, 300)])
@pytest.mark.parametrize("screen_shape", ["landscape", "portrait", "square"])
def test_single_image_has_original_dimensions_and_no_black_edges(size, screen_shape):
    output, layout = ImmichApi._render([], [preview(size)], screen_shape, True)
    with Image.open(BytesIO(output)) as image:
        assert image.size == size
        assert image.format == "JPEG"
        # Red reaches every edge: no black canvas was added or retained.
        assert image.getextrema()[0][0] > 240
    assert layout == "single"


def test_original_ratio_respects_exif_rotation():
    output, _ = ImmichApi._render([], [preview((400, 200), orientation=6)], "square", True)
    with Image.open(BytesIO(output)) as image:
        assert image.size == (200, 400)
        assert image.getexif().get(274, 1) == 1


@pytest.mark.parametrize("mode,companion,size,layout", [
    ("single", False, (200, 400), "single"),
    ("pairs", False, (200, 400), "single"),
    ("pairs", True, (720, 720), "side_by_side"),
])
async def test_snapshot_passes_option_to_renderer_without_changing_pairs(asset, mode, companion, size, layout):
    api = ImmichApi("http://immich.test", "key")
    assets = [asset, {**asset, "id": "second"}] if companion else [asset]
    api._request = AsyncMock(side_effect=[assets, *([preview((200, 400))] * len(assets))])
    snapshot = await api.snapshot({"mode": mode, "screen_shape": "square", "original_aspect_ratio": True}, 1, set())
    assert Image.open(BytesIO(snapshot.image)).size == size
    assert snapshot.layout == layout
    assert len(snapshot.photos) == len(assets)


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
async def test_option_saves_and_can_be_disabled_on_all_routes(hass, route):
    if route == "setup":
        manager = hass.config_entries.flow
        with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
            result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
                "url": "http://immich.test", "api_key": "key",
            })
        result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    else:
        entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
            "url": "http://immich.test", "api_key": "key", "source": "all", "original_aspect_ratio": True,
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
    result = await manager.async_configure(result["flow_id"], {})
    assert result["data_schema"]({})["original_aspect_ratio"] is (route != "setup")
    # Navigate back with an edit, then verify the draft is retained.
    result = await manager.async_configure(result["flow_id"], {"original_aspect_ratio": route == "setup", "navigation": "back"})
    result = await manager.async_configure(result["flow_id"], {})
    assert result["data_schema"]({})["original_aspect_ratio"] is (route == "setup")
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await manager.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    saved = result["data"] if route == "setup" else entry.data
    assert saved["original_aspect_ratio"] is (route == "setup")


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_toggle_rejects_padded_cache_then_restores_unpadded_cache(hass, asset):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "all",
    })
    entry.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else preview((200, 400))

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert Image.open(BytesIO(hass.data[DOMAIN][entry.entry_id].data.image)).size == (1280, 800)
        manager = hass.config_entries.options
        result = await manager.async_init(entry.entry_id)
        result = await manager.async_configure(result["flow_id"], {"next_step_id": "display"})
        result = await manager.async_configure(result["flow_id"], {})
        with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
            await manager.async_configure(result["flow_id"], {"original_aspect_ratio": True})
            await hass.async_block_till_done()
            assert entry.entry_id not in hass.data[DOMAIN]
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert Image.open(BytesIO(hass.data[DOMAIN][entry.entry_id].data.image)).size == (200, 400)
        assert await hass.config_entries.async_unload(entry.entry_id)
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        snapshot = hass.data[DOMAIN][entry.entry_id].data
        assert snapshot.using_cache
        assert Image.open(BytesIO(snapshot.image)).size == (200, 400)
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("shape,expected", [
    ("landscape", (1280, 640)),
    ("portrait", (800, 400)),
    ("square", (720, 360)),
])
@pytest.mark.parametrize("rotated", [False, True])
def test_large_original_ratio_photo_fits_output_limit_without_padding(shape, expected, rotated):
    size = (2000, 4000) if rotated else (4000, 2000)
    output, layout = ImmichApi._render([], [preview(size, orientation=6 if rotated else None)], shape, True)
    with Image.open(BytesIO(output)) as image:
        assert image.size == expected
        assert image.getextrema()[0][0] > 240
    assert layout == "single"
