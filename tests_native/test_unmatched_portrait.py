"""Unmatched portraits keep their edges and colour fill, including after reload."""
import json
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi
from custom_components.immich_frames.const import DOMAIN
from custom_components.immich_frames.coordinator import FrameCoordinator


@pytest.mark.parametrize("fit", [None, "crop", "show_full"])
@pytest.mark.parametrize("missing_date", [False, True])
@pytest.mark.parametrize("shape,size", [
    ("landscape", (1280, 800)), ("portrait", (800, 1280)), ("square", (720, 720)),
])
async def test_unmatched_portrait_keeps_top_and_bottom(asset, fit, missing_date, shape, size):
    photo = Image.new("RGB", (400, 1200), (40, 100, 200))
    photo.paste("red", (0, 0, 400, 120))
    photo.paste("lime", (0, 1080, 400, 1200))
    payload = BytesIO()
    photo.save(payload, "PNG")
    asset = {**asset, "width": 400, "height": 1200}
    if missing_date:
        asset.pop("localDateTime")
    api = ImmichApi("http://immich.test", "key")
    api._request = AsyncMock(side_effect=[[asset], payload.getvalue()])
    options = {"mode": "pairs", "screen_shape": shape}
    if fit is not None:
        options["photo_fit"] = fit
    snapshot = await api.snapshot(options, 1, set())
    assert snapshot.layout == "single"
    assert api._request.await_count == 2
    with Image.open(BytesIO(snapshot.image)) as output:
        assert output.size == size
        assert output.getpixel((size[0] // 2, 10))[0] > 240
        assert output.getpixel((size[0] // 2, size[1] - 10))[1] > 240
        # The blue photo supplies a non-black, dimmed background on both sides.
        for x in (10, size[0] - 10):
            fill = output.getpixel((x, size[1] // 2))
            assert 40 < fill[2] < 110
            assert fill[2] > fill[0]


@pytest.mark.parametrize("orientation,paired", [
    ("portrait", False), ("landscape", False), ("portrait", True),
])
async def test_cache_records_effective_fit_and_rejects_old_portrait_crop(hass, orientation, paired):
    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test", "api_key": "key", "mode": "pairs", "photo_fit": "crop",
    })
    entry.add_to_hass(hass)
    coordinator = FrameCoordinator(hass, entry)
    coordinator.cache_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 800), "blue").save(coordinator.cache_path.with_suffix(".jpg"))
    photos = [{"id": "first", "orientation": orientation}]
    if paired:
        photos.append({"id": "second", "orientation": orientation})
    state = {
        "generation": 1, "created_at": "2026-09-18T12:00:00+00:00",
        "photos": photos, "output_size": [1280, 800], "photo_fit": "crop",
        "photo_settings": {"mode": "pairs"},
        "layout": "side_by_side" if paired else "single",
    }
    state_path = coordinator.cache_path.with_suffix(".json")
    state_path.write_text(json.dumps(state))
    await hass.async_add_executor_job(coordinator._load_cache)
    assert coordinator.data is None  # Old fit metadata cannot establish provenance.
    from datetime import datetime, timezone
    from custom_components.immich_frames.api import FrameSnapshot
    rendered, layout = ImmichApi._render(photos, [coordinator.cache_path.with_suffix(".jpg").read_bytes()] * len(photos), fit="show_full" if orientation == "portrait" and not paired else "crop")
    snapshot = FrameSnapshot(rendered, 1, tuple(photos), layout, datetime.now(timezone.utc), len(photos))
    await coordinator._save_cache(snapshot)
    await hass.async_add_executor_job(coordinator._load_cache)
    assert coordinator.data is not None
    assert coordinator.data.image == rendered
    assert coordinator.data.using_cache
    await coordinator.async_close()
