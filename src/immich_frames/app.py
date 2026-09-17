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
from .filtering import FilterValidationError, compile_filter
from .selection import select_candidates
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
        if self.publisher:
            self.publisher.set_command_handler(self._handle_command)
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def _handle_command(self, frame_id: str, command: str) -> None:
        if command not in {"next", "refresh"} or self.loop is None:
            return
        frame = next((item for item in self.storage.list_frames() if item.frame_id == frame_id), None)
        if frame:
            asyncio.run_coroutine_threadsafe(self.refresh_frame(frame), self.loop)

    async def refresh_frame(self, frame: FrameConfig) -> None:
        try:
            candidates = await select_candidates(self.client, frame, size=100)
            if not candidates and frame.source == "memories" and frame.fallback_to_all:
                fallback = FrameConfig(
                    frame_id=frame.frame_id, name=frame.name, mode=frame.mode, pair_window_days=frame.pair_window_days,
                    pairs_only=frame.pairs_only, slideshow_interval=frame.slideshow_interval, filter=frame.filter,
                    output_width=frame.output_width, output_height=frame.output_height, fit=frame.fit,
                )
                candidates = await select_candidates(self.client, fallback, size=100)
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
        try:
            frame = self._frame_from_body(body)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, FilterValidationError) as exc:
            raise web.HTTPBadRequest(text=f"Invalid frame configuration: {exc}") from exc
        self.storage.save_frame(frame)
        self.start_frame(frame)
        return web.json_response({"frame_id": frame.frame_id}, status=201)

    @staticmethod
    def _frame_from_body(body: dict[str, Any], frame_id: str | None = None) -> FrameConfig:
        raw_filter = body.get("filter", {})
        if isinstance(raw_filter, str):
            raw_filter = json.loads(raw_filter)
        if not isinstance(raw_filter, dict):
            raise ValueError("filter must be an object")
        mode = body.get("mode", "single")
        if mode not in ("single", "pairs"):
            raise ValueError("mode must be single or pairs")
        fit = body.get("fit", "cover")
        if fit not in ("cover", "contain"):
            raise ValueError("fit must be cover or contain")
        source = body.get("source", "filter")
        if source not in ("filter", "memories", "smart"):
            raise ValueError("source must be filter, memories, or smart")
        order_direction = body.get("order_direction", "desc")
        if order_direction not in ("asc", "desc", "random"):
            raise ValueError("order_direction must be asc, desc, or random")
        return FrameConfig(
            frame_id=frame_id or str(uuid.uuid4()), name=str(body["name"]).strip(), mode=mode,
            pair_window_days=max(0, min(7, int(body.get("pair_window_days", 0)))), pairs_only=bool(body.get("pairs_only", False)),
            slideshow_interval=max(10, min(86400, int(body.get("slideshow_interval", 30)))), filter=compile_filter(raw_filter),
            source=source, memory_window_days=max(0, min(7, int(body.get("memory_window_days", 2)))),
            fallback_to_all=bool(body.get("fallback_to_all", False)), smart_query=body.get("smart_query"),
            smart_reference_asset_id=body.get("smart_reference_asset_id"), order_field=body.get("order_field", "fileCreatedAt"), order_direction=order_direction,
            output_width=max(320, min(4096, int(body.get("output_width", 1920)))), output_height=max(240, min(4096, int(body.get("output_height", 1080)))), fit=fit,
        )

    async def home(self, _: web.Request) -> web.Response:
        return web.Response(text="""<!doctype html><meta name=viewport content='width=device-width'><title>Immich Frames</title>
<h1>Immich Frames</h1><p>Create a Home Assistant photo frame.</p>
<form id=f><label>Name <input name=name required></label><label>Mode <select name=mode><option value=single>Single image</option><option value=pairs>Matching pairs</option></select></label><label>Pair window (days) <input name=pair_window_days type=number min=0 max=7 value=0></label><label><input name=pairs_only type=checkbox> Pairs only</label><label>Immich filter JSON <textarea name=filter>{}</textarea></label><button>Create frame</button></form>
<pre id=frames>Loading…</pre><script>
const out=document.querySelector('#frames'); async function load(){out.textContent=JSON.stringify(await (await fetch('/api/frames')).json(),null,2)}
document.querySelector('#f').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));data.filter=JSON.parse(data.filter||'{}');data.pairs_only=e.target.pairs_only.checked;const response=await fetch('/api/frames',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});if(!response.ok) alert(await response.text());e.target.reset();load()};load();
</script>""", content_type="text/html")

    async def list_frames(self, _: web.Request) -> web.Response:
        return web.json_response([{"frame_id": f.frame_id, "name": f.name, "mode": f.mode} for f in self.storage.list_frames()])

    async def refresh(self, request: web.Request) -> web.Response:
        frame = next((item for item in self.storage.list_frames() if item.frame_id == request.match_info["frame_id"]), None)
        if frame is None:
            raise web.HTTPNotFound()
        await self.refresh_frame(frame)
        return web.json_response({"frame_id": frame.frame_id, "generation": self.generation.get(frame.frame_id, 0)})

    async def update_frame(self, request: web.Request) -> web.Response:
        frame = next((item for item in self.storage.list_frames() if item.frame_id == request.match_info["frame_id"]), None)
        if frame is None:
            raise web.HTTPNotFound()
        body = await request.json()
        try:
            updated = self._frame_from_body({
                "name": body.get("name", frame.name), "mode": body.get("mode", frame.mode),
                "pair_window_days": body.get("pair_window_days", frame.pair_window_days), "pairs_only": body.get("pairs_only", frame.pairs_only),
                "slideshow_interval": body.get("slideshow_interval", frame.slideshow_interval), "filter": body.get("filter", frame.filter),
                "source": body.get("source", frame.source), "memory_window_days": body.get("memory_window_days", frame.memory_window_days), "fallback_to_all": body.get("fallback_to_all", frame.fallback_to_all),
                "smart_query": body.get("smart_query", frame.smart_query), "smart_reference_asset_id": body.get("smart_reference_asset_id", frame.smart_reference_asset_id),
                "order_field": body.get("order_field", frame.order_field), "order_direction": body.get("order_direction", frame.order_direction),
                "output_width": body.get("output_width", frame.output_width), "output_height": body.get("output_height", frame.output_height), "fit": body.get("fit", frame.fit),
            }, frame.frame_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise web.HTTPBadRequest(text=f"Invalid frame configuration: {exc}") from exc
        self.storage.save_frame(updated)
        self.start_frame(updated)
        return web.json_response({"frame_id": updated.frame_id})

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
        app.add_routes([web.get("/", self.home), web.get("/api/health", self.health), web.get("/api/frames", self.list_frames), web.post("/api/frames", self.create_frame), web.put("/api/frames/{frame_id}", self.update_frame), web.post("/api/frames/{frame_id}/refresh", self.refresh), web.delete("/api/frames/{frame_id}", self.delete_frame)])
        return app

    async def start_existing(self) -> None:
        self.loop = asyncio.get_running_loop()
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
