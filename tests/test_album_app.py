"""Exercise album catalog, frame editing, and export through the add-on API."""
from unittest.mock import AsyncMock, Mock

from aiohttp.test_utils import TestClient, TestServer

from immich_frames.app import FrameApp


async def test_album_selection_survives_create_edit_export_and_import(tmp_path):
    app = FrameApp({}, tmp_path)
    app.storage.save_connection("home", "Home", "http://immich.test", "test-key")
    upstream = Mock(albums=AsyncMock(return_value=[
        {"id": "a", "albumName": "Family"}, {"id": "b", "albumName": "Trips"},
    ]), close=AsyncMock())
    app.clients["home"] = upstream
    app.start_frame = Mock()
    async with TestClient(TestServer(app.application())) as client:
        response = await client.get("/api/catalog/albums?connection_id=home")
        assert response.status == 200
        assert [album["albumName"] for album in await response.json()] == ["Family", "Trips"]
        upstream.albums.assert_awaited_once()

        response = await client.post("/api/frames", json={
            "name": "Combined", "connection_id": "home", "source": "album", "album_ids": ["a", "b"],
        })
        assert response.status == 201
        frame_id = (await response.json())["frame_id"]
        assert app.storage.list_frames()[0].album_ids == ["a", "b"]

        response = await client.put(f"/api/frames/{frame_id}", json={"slideshow_interval": 120})
        assert response.status == 200
        assert app.storage.list_frames()[0].album_ids == ["a", "b"]

        # Older API clients can still replace the selection with a single album.
        response = await client.put(f"/api/frames/{frame_id}", json={"album_id": "b"})
        assert response.status == 200
        assert app.storage.list_frames()[0].album_ids is None
        assert app.storage.list_frames()[0].album_id == "b"
        response = await client.put(f"/api/frames/{frame_id}", json={"album_ids": ["a", "b"]})
        assert response.status == 200

        response = await client.get("/api/export")
        exported = await response.json()
        assert exported["frames"][0]["album_ids"] == ["a", "b"]
        exported["frames"][0]["frame_id"] = "imported"
        response = await client.post("/api/import", json=exported)
        assert response.status == 201
        imported = next(frame for frame in app.storage.list_frames() if frame.frame_id == "imported")
        assert imported.album_ids == ["a", "b"]
