"""Exercise source selection through snapshots and compare encoded image detail."""
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image, ImageChops, ImageStat

from custom_components.immich_frames.api import ImmichApi, ImmichApiError


def picture(size, colour="blue", orientation=1):
    image = Image.new("RGB", size, colour)
    data = BytesIO()
    exif = Image.Exif()
    exif[274] = orientation
    image.save(data, "JPEG", exif=exif)
    return data.getvalue()


def api_with_images(asset, preview, fullsize):
    api = ImmichApi("http://immich.test", "key")

    async def request(method, path, **kwargs):
        if path == "/api/search/random":
            return [asset]
        assert path == f"/api/assets/{asset['id']}/thumbnail"
        if kwargs["params"]["size"] == "preview":
            return preview
        assert kwargs["params"]["size"] == "fullsize"
        if isinstance(fullsize, Exception):
            raise fullsize
        return fullsize

    api._request = AsyncMock(side_effect=request)
    return api


@pytest.mark.parametrize("shape,size", [("landscape", (1280, 800)), ("portrait", (800, 1280)), ("square", (720, 720))])
async def test_crop_uses_fullsize_when_preview_would_be_enlarged(asset, shape, size):
    preview = picture((300, 450), "red")
    fullsize = picture((1600, 2400))
    api = api_with_images({**asset, "width": 1600, "height": 2400}, preview, fullsize)
    snapshot = await api.snapshot({"photo_fit": "crop", "screen_shape": shape}, 1, set())
    expected, _ = api._render([], [fullsize], shape, "crop")
    assert snapshot.image == expected
    assert Image.open(BytesIO(snapshot.image)).size == size
    assert api._request.await_count == 3


@pytest.mark.parametrize("preview_size,original_size,fit", [
    ((1280, 800), (4000, 2500), "crop"),  # Exact fit needs no enlargement.
    ((1600, 2400), (4000, 6000), "crop"),
    ((300, 450), (300, 450), "crop"),  # Original itself is low resolution.
    ((300, 450), (4000, 6000), "show_full"),
])
async def test_avoids_unnecessary_fullsize_downloads(asset, preview_size, original_size, fit):
    api = api_with_images({**asset, "width": original_size[0], "height": original_size[1]},
                          picture(preview_size), AssertionError("Unexpected download"))
    await api.snapshot({"photo_fit": fit}, 1, set())
    assert api._request.await_count == 2


@pytest.mark.parametrize("fallback", [
    ImmichApiError("Forbidden", 403), ImmichApiError("Not found", 404),
    ImmichApiError("Unavailable", 503), ImmichApiError("Timeout"),
    b"unsupported or corrupt image", picture((100, 150)), picture((300, 450)),
    picture((1600, 2400))[:500],  # Recognisable JPEG header, incomplete pixels.
])
async def test_unusable_fullsize_keeps_current_preview_and_connected_state(asset, fallback):
    preview = picture((300, 450))
    api = api_with_images({**asset, "width": 4000, "height": 6000}, preview, fallback)
    snapshot = await api.snapshot({"photo_fit": "crop"}, 1, set())
    expected, _ = api._render([], [preview], fit="crop")
    assert snapshot.image == expected
    assert snapshot.connected
    assert not snapshot.using_cache


@pytest.mark.parametrize("orientation", [5, 6, 7, 8])
async def test_preview_resolution_accounts_for_exif_rotation(asset, orientation):
    # Stored 800x1280 is displayed as 1280x800, exactly enough for this crop.
    api = api_with_images({**asset, "width": 4000, "height": 6000},
                          picture((800, 1280), orientation=orientation), AssertionError("Unexpected download"))
    await api.snapshot({"photo_fit": "crop"}, 1, set())
    assert api._request.await_count == 2


async def test_unknown_original_dimensions_still_try_fullsize_and_rotate_it(asset):
    fullsize = picture((2400, 1600), orientation=6)
    api = api_with_images({**asset, "width": None, "height": None}, picture((300, 450)), fullsize)
    snapshot = await api.snapshot({"photo_fit": "crop"}, 1, set())
    expected, _ = api._render([], [fullsize], fit="crop")
    assert snapshot.image == expected
    assert api._request.await_count == 3


async def test_pairs_check_each_tile_independently_and_keep_divider(asset):
    assets = [{**asset, "width": 2400, "height": 3200}, {**asset, "id": "second", "width": 2400, "height": 3200}]
    previews = {asset["id"]: picture((320, 400), "red"), "second": picture((639, 800), "lime")}
    fullsize = picture((2400, 3200), "blue")
    api = ImmichApi("http://immich.test", "key")

    async def request(method, path, **kwargs):
        if path == "/api/search/random":
            return assets
        asset_id = path.split("/")[-2]
        if kwargs["params"]["size"] == "fullsize":
            assert asset_id == asset["id"]
            return fullsize
        return previews[asset_id]

    api._request = AsyncMock(side_effect=request)
    snapshot = await api.snapshot({"mode": "pairs", "photo_fit": "crop"}, 1, set())
    expected, _ = api._render([], [fullsize, previews["second"]], fit="crop")
    assert snapshot.image == expected
    assert snapshot.layout == "side_by_side"
    assert api._request.await_count == 4
    with Image.open(BytesIO(snapshot.image)) as image:
        assert max(image.getpixel((640, 400))) < 10


def test_single_output_preserves_more_fine_colour_detail_than_previous_encoding():
    source = Image.new("RGB", (1280, 800), "red")
    for x in range(0, 1280, 4):
        source.paste("blue", (x, 0, x + 2, 800))
    data = BytesIO()
    source.save(data, "PNG")
    improved, _ = ImmichApi._render([], [data.getvalue()], fit="crop")
    previous = BytesIO()
    source.save(previous, "JPEG", quality=85, optimize=True)
    with Image.open(BytesIO(improved)) as new, Image.open(BytesIO(previous.getvalue())) as old:
        new_error = sum(ImageStat.Stat(ImageChops.difference(source, new)).mean)
        old_error = sum(ImageStat.Stat(ImageChops.difference(source, old)).mean)
        assert new_error < old_error / 2
