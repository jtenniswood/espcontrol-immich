"""A source edit must beat an older manual refresh already in flight."""

import asyncio
from dataclasses import replace
from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from PIL import Image

from immich_frames.app import FrameApp
from immich_frames.models import FrameConfig
from custom_components.immich_frames.core.models import FrameSnapshot


async def test_inflight_refresh_cannot_publish_replaced_source(tmp_path):
    app = FrameApp({}, tmp_path)
    app.clients["default"] = Mock(close=AsyncMock())
    frame = FrameConfig("frame", "Hall", source="album", album_ids=["old"])
    raw = BytesIO()
    Image.new("RGB", (1280, 800), "blue").save(raw, "JPEG")
    began, release = asyncio.Event(), asyncio.Event()

    async def render(_client, options, generation, recent_ids, **clock):
        album = options.album_ids[0]
        if album == "old":
            began.set()
            await release.wait()
        return FrameSnapshot(
            raw.getvalue(),
            generation,
            ({"id": album},),
            "single",
            datetime.now(timezone.utc),
            1,
        )

    with patch("immich_frames.app.snapshot", render):
        old = asyncio.create_task(app.refresh_frame(frame))
        await began.wait()
        app.start_frame(replace(frame, album_ids=["new"]))
        release.set()
        await old

        async def new_slide():
            while "frame" not in app.slides:
                await asyncio.sleep(0)

        await asyncio.wait_for(new_slide(), 2)
        assert app.slides["frame"].primary.id == "new"
        assert [slide.primary.id for slide in app.history["frame"]] == ["new"]
        await app.shutdown(None)
