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
@pytest.mark.parametrize("fit", ["crop", "show_full"])
@pytest.mark.parametrize("source_size", [(300, 450), (1600, 2400)])
async def test_fullsize_is_preferred_without_downloading_preview(asset, shape, size, fit, source_size):
    # Source choice is independent of preview dimensions and source metadata.
    fullsize = picture(source_size, "blue")
    api = api_with_images({**asset, "width": source_size[0], "height": source_size[1]},
                          picture((1600, 2400), "red"), fullsize)
    snapshot = await api.snapshot({"photo_fit": fit, "screen_shape": shape}, 1, set())
    expected, _ = api._render([], [fullsize], shape, fit)
    assert snapshot.image == expected
    assert Image.open(BytesIO(snapshot.image)).size == size
    assert api._request.await_count == 2
    assert api._request.await_args_list[-1].kwargs["params"] == {"size": "fullsize"}


@pytest.mark.parametrize("fit", ["crop", "show_full"])
@pytest.mark.parametrize("fallback", [
    ImmichApiError("Forbidden", 403), ImmichApiError("Not found", 404),
    ImmichApiError("Unavailable", 503), ImmichApiError("Timeout"),
    b"unsupported or corrupt image",
    picture((1600, 2400))[:500],  # Recognisable JPEG header, incomplete pixels.
    Image.DecompressionBombError("Too many pixels"),
])
async def test_unusable_fullsize_falls_back_to_preview(asset, fit, fallback):
    preview = picture((300, 450))
    api = api_with_images({**asset, "width": 4000, "height": 6000}, preview, fallback)
    snapshot = await api.snapshot({"photo_fit": fit}, 1, set())
    expected, _ = api._render([], [preview], fit=fit)
    assert snapshot.image == expected
    assert snapshot.connected
    assert not snapshot.using_cache
    assert [call.kwargs["params"]["size"] for call in api._request.await_args_list[1:]] == ["fullsize", "preview"]


@pytest.mark.parametrize("orientation", [5, 6, 7, 8])
async def test_unknown_original_dimensions_still_use_fullsize_and_rotate_it(asset, orientation):
    fullsize = picture((2400, 1600), orientation=orientation)
    api = api_with_images({**asset, "width": None, "height": None}, picture((300, 450)), fullsize)
    snapshot = await api.snapshot({"photo_fit": "crop"}, 1, set())
    expected, _ = api._render([], [fullsize], fit="crop")
    assert snapshot.image == expected
    assert api._request.await_count == 2


@pytest.mark.parametrize("fit", ["crop", "show_full"])
@pytest.mark.parametrize("second_unavailable", [False, True])
async def test_pairs_request_both_fullsize_sources_and_fall_back_independently(asset, fit, second_unavailable):
    assets = [{**asset, "width": 2400, "height": 3200}, {**asset, "id": "second", "width": 2400, "height": 3200}]
    fullsizes = {asset["id"]: picture((1200, 1600), "blue"), "second": picture((1200, 1600), "red")}
    preview = picture((639, 800), "lime")
    api = ImmichApi("http://immich.test", "key")

    async def request(method, path, **kwargs):
        if path == "/api/search/random":
            return assets
        asset_id = path.split("/")[-2]
        if kwargs["params"]["size"] == "fullsize":
            if asset_id == "second" and second_unavailable:
                raise ImmichApiError("Forbidden", 403)
            return fullsizes[asset_id]
        assert asset_id == "second" and second_unavailable
        return preview

    api._request = AsyncMock(side_effect=request)
    snapshot = await api.snapshot({"mode": "pairs", "photo_fit": fit}, 1, set())
    expected, _ = api._render([], [fullsizes[asset["id"]], preview if second_unavailable else fullsizes["second"]], fit=fit)
    assert snapshot.image == expected
    assert snapshot.layout == "side_by_side"
    assert api._request.await_count == (4 if second_unavailable else 3)
    with Image.open(BytesIO(snapshot.image)) as image:
        assert max(image.getpixel((640, 400))) < 10


async def test_unmatched_portrait_uses_fullsize_with_full_photo_fit(asset):
    fullsize = picture((1200, 1600))
    api = api_with_images(asset, picture((100, 200), "red"), fullsize)
    snapshot = await api.snapshot({"mode": "pairs", "photo_fit": "crop"}, 1, set())
    expected, _ = api._render([], [fullsize], fit="show_full")
    assert snapshot.image == expected
    assert api._request.await_count == 2


async def test_both_sources_unusable_reports_failure(asset):
    api = api_with_images(asset, b"corrupt preview", b"corrupt fullsize")
    with pytest.raises(ImmichApiError, match="Could not decode the photo"):
        await api.snapshot({}, 1, set())


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
