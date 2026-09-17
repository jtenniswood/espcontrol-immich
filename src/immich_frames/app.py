from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

from .immich_client import ImmichClient
from .models import FrameConfig, Photo
from .mqtt import MqttPublisher
from .pairing import choose_companion
from .rendering import render_slide
from .storage import Storage

LOG = logging.getLogger("immich_frames")


class FrameApp:
    def __init__(self, config: dict, data_dir: Path) -> None:
        self.config = config
        self.storage = Storage(data_dir)
        self.generation: dict[str, int] = {}
        self.slides: dict[str, Any] = {}
        self.client = ImmichClient(config["immich_url"], config["immich_api_key"])
        self.publisher: MqttPublisher | None = None
        try:
            if config.get("mqtt_host"):
                self.publisher = MqttPublisher(config["mqtt_host"], int(config.get("mqtt_port", 1883)), config.get("mqtt_username"), config.get("mqtt_password"))
        except Exception as exc:
            LOG.warning("MQTT is unavailable; frames will remain locally managed: %s", exc)
        self.tasks: dict[str, asyncio.Task[None]] = {}

    async def refresh_frame(self, frame: FrameConfig) -> None:
        try:
            query = {"type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"in": ["timeline", "archive", "hidden"]}, **frame.filter}
            candidates = await self.client.search(query, size=100, random=True)
            if not candidates:
                LOG.warning("Frame %s has no matching photos", frame.name)
                return
            primary = candidates[0]
            photos: tuple[Photo, ...] = (primary,)
            if frame.mode == "pairs":
                companion = choose_companion(primary, candidates[1:], frame.pair_window_days)
                if companion:
                    photos = (primary, companion)
                elif frame.pairs_only:
                    LOG.info("Frame %s has no complete pair", frame.name)
                    return
            payloads = tuple(await self.client.thumbnail(photo.id) for photo in photos)
            generation = self.generation.get(frame.frame_id, 0) + 1
            slide = render_slide(frame.frame_id, generation, photos, payloads, frame.output_width, frame.output_height, frame.fit)
            self.generation[frame.frame_id] = generation
            self.slides[frame.frame_id] = slide
            if self.publisher:
                self.publisher.publish_frame(frame, slide)
        except Exception:
            LOG.exception("Unable to refresh frame %s", frame.name)

    async def frame_loop(self, frame: FrameConfig) -> None:
        while True:
            await self.refresh_frame(frame)
            await asyncio.sleep(max(10, frame.slideshow_interval))

    def start_frame(self, frame: FrameConfig) -> None:
        old = self.tasks.pop(frame.frame_id, None)
        if old:
            old.cancel()
        self.tasks[frame.frame_id] = asyncio.create_task(self.frame_loop(frame))

    async def create_frame(self, request: web.Request) -> web.Response:
        body = await request.json()
        frame = FrameConfig(frame_id=str(uuid.uuid4()), name=body["name"], mode=body.get("mode", "single"), pair_window_days=int(body.get("pair_window_days", 0)), pairs_only=bool(body.get("pairs_only", False)), slideshow_interval=int(body.get("slideshow_interval", 30)), filter=body.get("filter", {}), output_width=int(body.get("output_width", 1920)), output_height=int(body.get("output_height", 1080)), fit=body.get("fit", "cover"))
        self.storage.save_frame(frame)
        self.start_frame(frame)
        return web.json_response({"frame_id": frame.frame_id}, status=201)

    async def home(self, _: web.Request) -> web.Response:
        return web.Response(text="""<!doctype html><meta name=viewport content='width=device-width'><title>Immich Frames</title>
<h1>Immich Frames</h1><p>Create a Home Assistant photo frame.</p>
<form id=f><label>Name <input name=name required></label><label>Mode <select name=mode><option value=single>Single image</option><option value=pairs>Matching pairs</option></select></label><button>Create frame</button></form>
<pre id=frames>Loading…</pre><script>
const out=document.querySelector('#frames'); async function load(){out.textContent=JSON.stringify(await (await fetch('/api/frames')).json(),null,2)}
document.querySelector('#f').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));await fetch('/api/frames',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});e.target.reset();load()};load();
</script>""", content_type="text/html")

    async def list_frames(self, _: web.Request) -> web.Response:
        return web.json_response([{"frame_id": f.frame_id, "name": f.name, "mode": f.mode} for f in self.storage.list_frames()])

    async def refresh(self, request: web.Request) -> web.Response:
        frame = next((item for item in self.storage.list_frames() if item.frame_id == request.match_info["frame_id"]), None)
        if frame is None:
            raise web.HTTPNotFound()
        await self.refresh_frame(frame)
        return web.json_response({"frame_id": frame.frame_id, "generation": self.generation.get(frame.frame_id, 0)})

    async def delete_frame(self, request: web.Request) -> web.Response:
        frame_id = request.match_info["frame_id"]
        frame = next((item for item in self.storage.list_frames() if item.frame_id == frame_id), None)
        task = self.tasks.pop(frame_id, None)
        if task:
            task.cancel()
        if frame and self.publisher:
            self.publisher.remove_frame(frame)
        self.storage.delete_frame(frame_id)
        return web.Response(status=204)

    async def health(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "version": "0.1.0"})

    def application(self) -> web.Application:
        app = web.Application()
        app.add_routes([web.get("/", self.home), web.get("/api/health", self.health), web.get("/api/frames", self.list_frames), web.post("/api/frames", self.create_frame), web.post("/api/frames/{frame_id}/refresh", self.refresh), web.delete("/api/frames/{frame_id}", self.delete_frame)])
        return app

    async def start_existing(self) -> None:
        for frame in self.storage.list_frames():
            self.start_frame(frame)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    path = Path(os.environ.get("IMMICH_FRAMES_CONFIG", "/data/config.json"))
    options_path = path.with_name("options.json")
    config_path = path if path.exists() else options_path
    config = json.loads(config_path.read_text()) if config_path.exists() else {"immich_url": "", "immich_api_key": ""}
    if not config.get("immich_url") or not config.get("immich_api_key"):
        LOG.error("Configure immich_url and immich_api_key before starting Immich Frames")
    frame_app = FrameApp(config, path.parent)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(frame_app.start_existing())
    web.run_app(frame_app.application(), host="0.0.0.0", port=8099)
