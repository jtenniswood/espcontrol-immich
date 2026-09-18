"""Legacy original-aspect settings still produce a bounded 16:10 frame."""
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from custom_components.immich_frames.api import ImmichApi


def preview(size, *, orientation=None):
    data = BytesIO()
    image = Image.new("RGB", size, "red")
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(data, "JPEG", exif=exif)
    return data.getvalue()


@pytest.mark.parametrize("size", [(400, 200), (200, 400), (300, 300), (2400, 1600), (1600, 2400)])
def test_single_photo_preserves_proportions_inside_fixed_frame(size):
    output, layout = ImmichApi._render([], [preview(size)])
    with Image.open(BytesIO(output)) as image:
        assert image.size == (1280, 800)
        assert image.format == "JPEG"
        assert image.getpixel((640, 400))[0] > 240
        assert 120 <= image.getpixel((0, 0))[0] <= 135
        assert max(image.getpixel((0, 0))[1:]) < 10
    assert layout == "single"


def test_fixed_frame_respects_exif_rotation():
    output, _ = ImmichApi._render([], [preview((400, 200), orientation=6)])
    with Image.open(BytesIO(output)) as image:
        assert image.size == (1280, 800)
        assert image.getexif().get(274, 1) == 1
        assert image.getpixel((640, 550))[0] > 240
        assert 120 <= image.getpixel((790, 400))[0] <= 135
        assert max(image.getpixel((790, 400))[1:]) < 10


@pytest.mark.parametrize("mode,companion,size,layout", [
    ("single", False, (1280, 800), "single"),
    ("pairs", False, (1280, 800), "single"),
    ("pairs", True, (1280, 800), "side_by_side"),
])
async def test_legacy_original_ratio_cannot_bypass_output_frame(asset, mode, companion, size, layout):
    api = ImmichApi("http://immich.test", "key")
    assets = [asset, {**asset, "id": "second"}] if companion else [asset]
    api._request = AsyncMock(side_effect=[assets, *([preview((200, 400))] * len(assets))])
    snapshot = await api.snapshot({"mode": mode, "screen_shape": "square", "original_aspect_ratio": True}, 1, set())
    assert Image.open(BytesIO(snapshot.image)).size == size
    assert snapshot.layout == layout
    assert len(snapshot.photos) == len(assets)
