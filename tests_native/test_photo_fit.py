"""Clear fit choices apply to singles, pairs, saved settings and cached output."""
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


@pytest.mark.parametrize("shape,size", [("landscape", (1280, 800)), ("portrait", (800, 1280)), ("square", (720, 720))])
@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("fit", ["crop", "show_full"])
def test_fit_preserves_edges_or_crops_and_keeps_frame_dimensions(shape, size, paired, fit):
    payloads = []
    for colour in (["red", "blue"] if paired else ["red"]):
        photo = Image.new("RGB", (600, 200), colour)
        # Distinct green edges must survive Show full image, and be cropped away.
        photo.paste("lime", (0, 0, 40, 200))
        photo.paste("lime", (560, 0, 600, 200))
        data = BytesIO()
        photo.save(data, "PNG")
        payloads.append(data.getvalue())
    output, layout = ImmichApi._render([], payloads, shape, fit)
    with Image.open(BytesIO(output)) as image:
        assert image.size == size
        assert layout == ("side_by_side" if paired else "single")
        divider = size[0] // 2
        tiles = [(0, divider), (divider + 1, size[0] - divider - 1)] if paired else [(0, size[0])]
        for i, (left, width) in enumerate(tiles):
            channel = 0 if i == 0 else 2
            center = left + width // 2
            assert image.getpixel((center, size[1] // 2))[channel] > 240
            edge = image.getpixel((left + 10, size[1] // 2))
            top = image.getpixel((center, 10))
            if fit == "show_full":
                assert edge[1] > 240
                assert 90 < top[channel] < 140
            else:
                assert edge[channel] > 240
                assert top[channel] > 240
        if paired:
            assert max(image.getpixel((divider, size[1] // 2))) < 10


def test_full_image_respects_exif_rotation():
    output, _ = ImmichApi._render([], [preview((400, 200), orientation=6)], "square", "show_full")
    with Image.open(BytesIO(output)) as image:
        assert image.size == (720, 720)
        assert image.getpixel((360, 10))[0] > 240
        assert 120 < image.getpixel((10, 360))[0] < 135
        assert image.getexif().get(274, 1) == 1


@pytest.mark.parametrize("mode,companion", [("single", False), ("pairs", False), ("pairs", True)])
@pytest.mark.parametrize("fit", ["crop", "show_full"])
async def test_snapshot_passes_fit_to_singles_pairs_and_fallback(asset, mode, companion, fit):
    api = ImmichApi("http://immich.test", "key")
    assets = [asset, {**asset, "id": "second"}] if companion else [asset]
    payload = preview((200, 400))
    api._request = AsyncMock(side_effect=[assets, *([payload] * len(assets))])
    snapshot = await api.snapshot({"mode": mode, "screen_shape": "square", "photo_fit": fit}, 1, set())
    expected, layout = ImmichApi._render(assets, [payload] * len(assets), "square", fit)
    assert snapshot.image == expected
    assert snapshot.layout == layout
    assert len(snapshot.photos) == len(assets)


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
@pytest.mark.parametrize("fit", ["crop", "show_full"])
async def test_fit_saves_and_retains_navigation_draft_on_all_routes(hass, route, fit):
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
    assert result["data_schema"]({})["photo_fit"] == "show_full"
    assert "original_aspect_ratio" not in result["data_schema"]({})
    # Navigate back with an edit, then verify the draft is retained.
    result = await manager.async_configure(result["flow_id"], {"photo_fit": fit, "navigation": "back"})
    result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    assert result["data_schema"]({})["photo_fit"] == fit
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await manager.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    saved = result["data"] if route == "setup" else entry.data
    assert saved["photo_fit"] == fit
    assert "original_aspect_ratio" not in saved


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fit_change_rejects_old_cache_then_restores_matching_cache(hass, asset):
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
        with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
            await manager.async_configure(result["flow_id"], {"photo_fit": "crop"})
            await hass.async_block_till_done()
            assert entry.entry_id not in hass.data[DOMAIN]
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert Image.open(BytesIO(hass.data[DOMAIN][entry.entry_id].data.image)).size == (1280, 800)
        assert await hass.config_entries.async_unload(entry.entry_id)
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        snapshot = hass.data[DOMAIN][entry.entry_id].data
        assert snapshot.using_cache
        assert Image.open(BytesIO(snapshot.image)).size == (1280, 800)
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("options,expected", [
    ({}, "show_full"),
    ({"mode": "single", "original_aspect_ratio": False}, "show_full"),
    ({"mode": "pairs", "original_aspect_ratio": False}, "crop"),
    ({"mode": "pairs", "original_aspect_ratio": True}, "show_full"),
    ({"mode": "pairs", "original_aspect_ratio": True, "photo_fit": "crop"}, "crop"),
])
def test_existing_settings_have_a_clear_fit_default(options, expected):
    from custom_components.immich_frames.const import photo_fit
    assert photo_fit(options) == expected


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("cached_fit", [None, "crop", "show_full"])
async def test_cache_requires_matching_explicit_fit(hass, cached_fit):
    import json
    from custom_components.immich_frames.coordinator import FrameCoordinator

    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "photo_fit": "show_full",
    })
    entry.add_to_hass(hass)
    coordinator = FrameCoordinator(hass, entry)
    coordinator.cache_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 800), "red").save(coordinator.cache_path.with_suffix(".jpg"))
    state = {
        "generation": 1, "created_at": "2026-09-18T12:00:00+00:00",
        "photos": [{"id": "photo"}], "output_size": [1280, 800],
    }
    if cached_fit is not None:
        state["photo_fit"] = cached_fit
    coordinator.cache_path.with_suffix(".json").write_text(json.dumps(state))
    await hass.async_add_executor_job(coordinator._load_cache)
    assert (coordinator.data is not None) is (cached_fit == "show_full")
    await coordinator.async_close()
