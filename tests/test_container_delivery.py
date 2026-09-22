"""Prove the optional adapter delivers a versioned image through its HTTP API."""

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, Mock

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from immich_frames.app import FrameApp
from immich_frames.models import FrameConfig, Photo


async def test_http_image_matches_state_and_source_edits_reject_old_images(tmp_path):
    raw = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(raw, "JPEG")
    app = FrameApp({}, tmp_path)
    app.storage.save_connection("default", "Home", "http://immich.test", "secret")
    app.clients["default"] = Mock(
        search=AsyncMock(
            return_value=[
                Photo.from_api(
                    {
                        "id": key,
                        "width": 100,
                        "height": 200,
                        "localDateTime": "2026-09-22T12:00:00Z",
                    }
                )
                for key in ("a", "b")
            ]
        ),
        photo_image=AsyncMock(return_value=raw.getvalue()),
        close=AsyncMock(),
    )
    frame = FrameConfig("hall", "Hall", mode="pairs")
    app.storage.save_frame(frame)
    async with TestClient(TestServer(app.application())) as client:
        for _ in range(200):
            response = await client.get("/api/frames/hall/state")
            if response.status == 200:
                break
            await asyncio.sleep(0.01)
        assert response.status == 200
        state = await response.json()
        assert state["asset_ids"] == ["a", "b"]
        response = await client.get("/" + state["image_url"])
        assert response.status == 200
        assert await response.read() == app.sessions["hall"].current.image
        assert "secret" not in str(state)
        response = await client.post("/api/frames/hall/commands/pause")
        assert (await response.json())["paused"]
        response = await client.post("/api/frames/hall/commands/next")
        assert not (await response.json())["paused"]
        response = await client.put("/api/frames/hall", json={"screen_shape": "square"})
        assert response.status == 200
        response = await client.get("/" + state["image_url"])
        assert response.status == 409
        response = await client.delete("/api/frames/hall")
        assert response.status == 204
        assert (await client.get("/api/frames/hall/image")).status == 404
