"""Exercise the installed container from connection setup through image delivery.

Run inside the candidate image, without a real Immich account or host mounts.
"""

import asyncio
import importlib.metadata
import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image
from immich_frames.app import FrameApp


async def check():
    raw = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(raw, "JPEG")

    async def version(_):
        return web.json_response({"major": 3, "minor": 2, "patch": 0})

    async def search(request):
        assert request.headers["x-api-key"] == "test-key"
        assets = [
            {
                "id": name,
                "width": 100,
                "height": 200,
                "localDateTime": "2026-09-22T12:00:00Z",
            }
            for name in ("left", "right")
        ]
        return web.json_response(
            assets if request.path.endswith("random") else {"assets": {"items": assets}}
        )

    async def photo(_):
        return web.Response(body=raw.getvalue(), content_type="image/jpeg")

    upstream = web.Application()
    upstream.add_routes(
        [
            web.get("/api/server/version", version),
            web.post("/api/search/{kind}", search),
            web.get("/api/assets/{asset}/thumbnail", photo),
        ]
    )
    async with TestServer(upstream) as server:
        with TemporaryDirectory() as root:
            app = FrameApp({}, Path(root))
            async with TestClient(TestServer(app.application())) as client:
                response = await client.post(
                    "/api/connections",
                    json={
                        "name": "Home",
                        "url": str(server.make_url("/")),
                        "api_key": "test-key",
                    },
                )
                assert response.status == 201, await response.text()
                connection = (await response.json())["id"]
                response = await client.post(
                    "/api/frames",
                    json={"name": "Hall", "connection_id": connection, "mode": "pairs"},
                )
                assert response.status == 201, await response.text()
                frame = (await response.json())["frame_id"]
                for _ in range(200):
                    response = await client.get(f"/api/frames/{frame}/state")
                    if response.status == 200:
                        break
                    await asyncio.sleep(0.05)
                assert response.status == 200
                state = await response.json()
                assert state["asset_ids"] == ["left", "right"]
                response = await client.get("/" + state["image_url"])
                assert response.status == 200
                image = await response.read()
                assert Image.open(BytesIO(image)).size == (1280, 800)
                for command in ("pause", "next", "previous"):
                    response = await client.post(
                        f"/api/frames/{frame}/commands/{command}"
                    )
                    assert response.status == 200
                response = await client.get(f"/api/frames/{frame}/state")
                assert (await response.json())["asset_ids"] == state["asset_ids"]
                assert "test-key" not in await (await client.get("/api/export")).text()
    return {"acceptance": "connection-create-render-image-navigation"}


if __name__ == "__main__":
    result = asyncio.run(check())
    result["python_packages"] = sorted(
        (
            {"name": dist.metadata["Name"], "version": dist.version}
            for dist in importlib.metadata.distributions()
        ),
        key=lambda dist: dist["name"].lower(),
    )
    print(json.dumps(result, indent=2))
