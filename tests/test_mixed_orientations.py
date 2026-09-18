"""Exercise actual slide refreshes with mixed orientations and portrait pairing."""
from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from immich_frames.app import FrameApp
from immich_frames.models import FrameConfig, Photo


@pytest.mark.parametrize("source", ["all", "album", "smart", "memories"])
@pytest.mark.parametrize("orientation,expected", [("any", ["landscape"]), ("landscape", ["landscape"]), ("portrait", ["a", "b"])])
async def test_mixed_slideshow_and_orientation_filters(tmp_path, source, orientation, expected):
    app = FrameApp({}, tmp_path)
    assets = [Photo.from_api({"id": name, "width": width, "height": 200, "localDateTime": "2026-09-17T12:00:00Z"})
              for name, width in [("landscape", 300), ("a", 100), ("b", 100)]]
    output = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(output, "JPEG")
    client = Mock(search=AsyncMock(return_value=assets), smart_search=AsyncMock(return_value=assets),
                  memories=AsyncMock(return_value=[{"assets": [{"id": photo.id} for photo in assets]}]),
                  thumbnail=AsyncMock(return_value=output.getvalue()))
    app.clients["default"] = client
    frame = FrameConfig("f", "Mixed", mode="pairs", pairs_only=True, orientation=orientation,
                        source=source, album_ids=["album"], smart_query="beach", memory_window_days=0)
    await app.refresh_frame(frame)
    assert [photo.id for photo in app.slides["f"].photos] == expected
    if orientation == "any":
        await app.refresh_frame(frame)
        assert [photo.id for photo in app.slides["f"].photos] == ["a", "b"]
        assert app.slides["f"].layout == "side_by_side"


@pytest.mark.parametrize("pairs_only,expected", [(False, "portrait"), (True, "landscape")])
async def test_unmatched_portrait_setting_does_not_block_landscape(tmp_path, pairs_only, expected):
    app = FrameApp({}, tmp_path)
    output = BytesIO()
    Image.new("RGB", (100, 200)).save(output, "JPEG")
    app.clients["default"] = Mock(search=AsyncMock(return_value=[
        Photo("portrait", 100, 200, None, None, "portrait.jpg"),
        Photo("landscape", 200, 100, None, None, "landscape.jpg"),
    ]), thumbnail=AsyncMock(return_value=output.getvalue()))
    await app.refresh_frame(FrameConfig("f", "Mixed", mode="pairs", pairs_only=pairs_only))
    assert app.slides["f"].primary.id == expected
    assert app.slides["f"].layout == "single"
