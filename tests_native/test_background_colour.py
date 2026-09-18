"""Single-photo padding follows ESPFrame's saturation-weighted accent colour."""
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from custom_components.immich_frames.api import ImmichApi
from custom_components.immich_frames.rendering import background_colour


def png(image):
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize("colour,expected", [
    ((240, 80, 40), (120, 40, 20)),
    ((128, 128, 128), (64, 64, 64)),
    ((255, 255, 255), (127, 127, 127)),
    ((0, 0, 0), (0, 0, 0)),
])
@pytest.mark.parametrize("size", [(1, 1), (13, 7), (800, 400)])
def test_solid_and_neutral_photos_have_half_brightness_fill(colour, expected, size):
    assert background_colour(Image.new("RGB", size, colour)) == expected


def test_vivid_colour_outweighs_large_neutral_areas():
    image = Image.new("RGB", (200, 200), (128, 128, 128))
    image.paste((240, 40, 20), (0, 0, 20, 200))
    # A plain average would be greyish. Saturation weighting selects the red.
    r, g, b = background_colour(image)
    assert 119 <= r <= 120
    assert 20 <= g <= 21
    assert 10 <= b <= 11


@pytest.mark.parametrize("mode", ["single", "pairs"])
async def test_snapshot_fills_single_photo_even_when_companion_is_missing(asset, mode):
    photo = Image.new("RGB", (200, 400), (40, 100, 200))
    api = ImmichApi("http://immich.test", "key")
    api._request = AsyncMock(side_effect=[[asset], png(photo)])
    snapshot = await api.snapshot({"mode": mode, "screen_shape": "landscape"}, 1, set())
    with Image.open(BytesIO(snapshot.image)) as rendered:
        assert rendered.size == (1280, 800)
        assert all(abs(a - b) <= 3 for a, b in zip(rendered.getpixel((0, 0)), (20, 50, 100)))
        assert all(abs(a - b) <= 3 for a, b in zip(rendered.getpixel((640, 400)), (40, 100, 200)))
    assert snapshot.layout == "single"


@pytest.mark.parametrize("size", [(800, 400), (400, 800)])
def test_real_black_photo_edges_are_preserved(size):
    photo = Image.new("RGB", size, "black")
    photo.paste((240, 80, 40), (100, 100, size[0] - 100, size[1] - 100))
    output, _ = ImmichApi._render([], [png(photo)])
    with Image.open(BytesIO(output)) as rendered:
        left, top = (1280 - size[0]) // 2, (800 - size[1]) // 2
        for position in [(left + 20, 400), (left + size[0] - 20, 400),
                         (640, top + 20), (640, top + size[1] - 20)]:
            assert max(rendered.getpixel(position)) < 5
        assert rendered.getpixel((0, 0))[0] > 110
        assert rendered.getpixel((640, 400))[0] > 230


def test_exif_rotation_is_applied_before_placing_photo():
    photo = Image.new("RGB", (800, 400), (40, 100, 200))
    exif = Image.Exif()
    exif[274] = 6
    payload = BytesIO()
    photo.save(payload, "JPEG", exif=exif)
    output, _ = ImmichApi._render([], [payload.getvalue()])
    with Image.open(BytesIO(output)) as rendered:
        # The rotated portrait reaches above the horizontal source's old bounds.
        assert rendered.getpixel((640, 200))[2] > 190
        assert 95 <= rendered.getpixel((200, 400))[2] <= 105
