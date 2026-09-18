"""Exercise actual slide refreshes with mixed orientations and portrait pairing."""
from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from immich_frames.app import FrameApp
from immich_frames.models import FrameConfig, Photo


@pytest.mark.parametrize("mode", ["pairs", "pairs_only"])
@pytest.mark.parametrize("source", ["all", "album", "smart", "memories"])
@pytest.mark.parametrize("orientation,expected", [("any", ["landscape"]), ("landscape", ["landscape"]), ("portrait", ["a", "b"])])
async def test_mixed_slideshow_and_orientation_filters(tmp_path, source, orientation, expected, mode):
    app = FrameApp({}, tmp_path)
    assets = [Photo.from_api({"id": name, "width": width, "height": 200, "localDateTime": "2026-09-17T12:00:00Z"})
              for name, width in [("landscape", 300), ("a", 100), ("b", 100)]]
    output = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(output, "JPEG")
    client = Mock(search=AsyncMock(return_value=assets), smart_search=AsyncMock(return_value=assets),
                  memories=AsyncMock(return_value=[{"assets": [{"id": photo.id} for photo in assets]}]),
                  thumbnail=AsyncMock(return_value=output.getvalue()))
    app.clients["default"] = client
    frame = FrameConfig("f", "Mixed", mode=mode, orientation=orientation,
                        source=source, album_ids=["album"], smart_query="beach", memory_window_days=0)
    await app.refresh_frame(frame)
    assert [photo.id for photo in app.slides["f"].photos] == expected
    if orientation == "any":
        await app.refresh_frame(frame)
        assert [photo.id for photo in app.slides["f"].photos] == ["a", "b"]
        assert app.slides["f"].layout == "side_by_side"


async def test_unmatched_portrait_and_landscape_both_appear(tmp_path):
    app = FrameApp({}, tmp_path)
    output = BytesIO()
    Image.new("RGB", (100, 200)).save(output, "JPEG")
    app.clients["default"] = Mock(search=AsyncMock(return_value=[
        Photo("portrait", 100, 200, None, None, "portrait.jpg"),
        Photo("landscape", 200, 100, None, None, "landscape.jpg"),
    ]), thumbnail=AsyncMock(return_value=output.getvalue()))
    frame = FrameConfig("f", "Mixed", mode="pairs")
    for expected in ["portrait", "landscape"]:
        await app.refresh_frame(frame)
        assert app.slides["f"].primary.id == expected
        assert app.slides["f"].layout == "single"


@pytest.mark.parametrize("has_pair", [False, True])
async def test_pairs_only_skips_single_portraits(tmp_path, has_pair):
    app = FrameApp({}, tmp_path)
    photos = [Photo("undated", 100, 200, None, None, "undated.jpg")]
    if has_pair:
        photos.extend(Photo.from_api({"id": name, "width": 100, "height": 200,
                                     "localDateTime": "2026-09-17T12:00:00Z"}) for name in ["a", "b"])
    output = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(output, "JPEG")
    client = Mock(search=AsyncMock(return_value=photos), thumbnail=AsyncMock(return_value=output.getvalue()))
    app.clients["default"] = client
    frame = FrameConfig("f", "Portrait pairs", mode="pairs_only", pair_window_days=0)
    await app.refresh_frame(frame)
    if has_pair:
        assert [photo.id for photo in app.slides["f"].photos] == ["a", "b"]
        assert app.slides["f"].layout == "side_by_side"
    else:
        assert "f" not in app.slides
        client.thumbnail.assert_not_awaited()
