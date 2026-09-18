from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aiohttp import web
from PIL import Image

from .immich_client import ImmichClient, ImmichError
from .models import OUTPUT_SIZE, FrameConfig, Photo, Slide
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
        if not self.storage.get_connection("default") and config.get("immich_url") and config.get("immich_api_key"):
            self.storage.save_connection("default", "Default Immich", config["immich_url"], config["immich_api_key"])
        self.generation: dict[str, int] = {}
        self.slides: dict[str, Any] = {}
        self.clients: dict[str, ImmichClient] = {}
        self.client = self._client_for("default") if self.storage.get_connection("default") else None
        self.publisher = None
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.paused: set[str] = set()
        self.metadata_role: dict[str, str] = {}
        self.history: dict[str, list[Any]] = {}
        self.cache_dir = data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_limit_bytes = max(16, int(config.get("cache_limit_mb", 256))) * 1024 * 1024

    def _client_for(self, connection_id: str) -> ImmichClient:
        if connection_id in self.clients:
            return self.clients[connection_id]
        connection = self.storage.get_connection(connection_id)
        if connection is None:
            raise ValueError(f"Unknown Immich connection: {connection_id}")
        client = ImmichClient(connection[1], connection[2])
        self.clients[connection_id] = client
        return client

    def _handle_command(self, frame_id: str, command: str) -> None:
        if self.loop is None:
            return
        frame = next((item for item in self.storage.list_frames() if item.frame_id == frame_id), None)
        if not frame:
            return
        if command == "pause":
            self.paused.add(frame_id)
            if self.publisher:
                self.publisher.publish_controls(frame, True)
        elif command == "resume":
            self.paused.discard(frame_id)
            if self.publisher:
                self.publisher.publish_controls(frame, False)
        elif command in {"next", "refresh"}:
            asyncio.run_coroutine_threadsafe(self.refresh_frame(frame, force=True), self.loop)
        elif command == "previous" and self.history.get(frame_id):
            slide = self.history[frame_id][-2] if len(self.history[frame_id]) > 1 else self.history[frame_id][-1]
            if self.publisher:
                self.publisher.publish_frame(frame, slide, paused=frame_id in self.paused, role=self.metadata_role.get(frame_id, "primary"))
        elif command == "clear_cache":
            for item in self.cache_dir.glob(f"{frame_id}.*"):
                item.unlink(missing_ok=True)
            if self.publisher:
                self.publisher.publish_cache_size(frame, self.cache_size())
        elif command in {"primary", "secondary"}:
            self.metadata_role[frame_id] = command
            if self.publisher:
                self.publisher.publish_controls(frame, frame_id in self.paused, command)
                slide = self.slides.get(frame_id)
                if slide:
                    self.publisher.publish_frame(frame, slide, paused=frame_id in self.paused, role=command)
        elif command.startswith("interval:"):
            try:
                interval = max(10, min(86400, int(command.split(":", 1)[1])))
            except ValueError:
                return
            updated = self._frame_from_body({"name": frame.name, "connection_id": frame.connection_id, "mode": frame.mode, "pair_window_days": frame.pair_window_days, "slideshow_interval": interval, "filter": frame.filter, "source": frame.source, "album_id": frame.album_id, "album_ids": frame.album_ids, "memory_window_days": frame.memory_window_days, "fallback_to_all": frame.fallback_to_all, "smart_query": frame.smart_query, "smart_reference_asset_id": frame.smart_reference_asset_id, "order_field": frame.order_field, "order_direction": frame.order_direction, "output_width": frame.output_width, "output_height": frame.output_height, "fit": frame.fit, "orientation": frame.orientation}, frame.frame_id)
            self.storage.save_frame(updated)
            if self.publisher:
                self.publisher.publish_controls(updated, frame_id in self.paused)

    async def refresh_frame(self, frame: FrameConfig, force: bool = False) -> None:
        try:
            if frame.frame_id in self.paused and not force:
                return
            client = self._client_for(frame.connection_id)
            candidates = await select_candidates(client, frame, size=1000)
            if not candidates and frame.source == "memories" and frame.fallback_to_all:
                fallback = FrameConfig(
                    frame_id=frame.frame_id, name=frame.name, connection_id=frame.connection_id, mode=frame.mode, pair_window_days=frame.pair_window_days,
                    slideshow_interval=frame.slideshow_interval, filter=frame.filter,
                    output_width=frame.output_width, output_height=frame.output_height, fit=frame.fit, orientation=frame.orientation,
                )
                candidates = await select_candidates(client, fallback, size=1000)
            if not candidates:
                LOG.warning("Frame %s has no matching photos", frame.name)
                return
            recent_ids = {photo.id for old_slide in self.history.get(frame.frame_id, [])[-10:] for photo in old_slide.photos}
            primary = next((photo for photo in candidates if photo.id not in recent_ids), candidates[0])
            photos: tuple[Photo, ...] = (primary,)
            if frame.mode == "pairs":
                companion = choose_companion(primary, [photo for photo in candidates if photo.id != primary.id], frame.pair_window_days)
                if companion:
                    photos = (primary, companion)
            payloads = tuple(await asyncio.gather(*(client.thumbnail(photo.id) for photo in photos)))
            generation = self.generation.get(frame.frame_id, 0) + 1
            slide = render_slide(frame.frame_id, generation, photos, payloads, frame.output_width, frame.output_height, frame.fit)
            self.generation[frame.frame_id] = generation
            self.slides[frame.frame_id] = slide
            self.history.setdefault(frame.frame_id, []).append(slide)
            self.history[frame.frame_id] = self.history[frame.frame_id][-20:]
            cache_path = self.cache_dir / f"{frame.frame_id}.jpg"
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_bytes(slide.jpeg)
            temporary.replace(cache_path)
            state_path = self.cache_dir / f"{frame.frame_id}.json"
            state_temporary = state_path.with_suffix(".tmp")
            state_temporary.write_text(json.dumps(slide.state()))
            state_temporary.replace(state_path)
            cache_size = self.enforce_cache_limit()
            if self.publisher:
                self.publisher.publish_frame(frame, slide, paused=frame.frame_id in self.paused, matching_assets=len(candidates), role=self.metadata_role.get(frame.frame_id, "primary"), cache_size=cache_size)
        except Exception as exc:
            LOG.exception("Unable to refresh frame %s", frame.name)
            if self.publisher:
                status = "invalid_api_key" if isinstance(exc, ImmichError) and exc.status in (401, 403) else "upstream_unavailable"
                cached = self.slides.get(frame.frame_id)
                if cached:
                    self.publisher.publish_frame(frame, cached, paused=frame.frame_id in self.paused, using_cache=True, status=status, connected=False, role=self.metadata_role.get(frame.frame_id, "primary"), cache_size=self.cache_size())
                else:
                    self.publisher.publish_error(frame, status)

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
        try:
            self._client_for(frame.connection_id)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
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
        source = body.get("source", "all")
        if source not in ("all", "album", "filter", "memories", "smart"):
            raise ValueError("source must be all, album, filter, memories, or smart")
        album_id = str(body.get("album_id") or "").strip() or None
        album_ids = body.get("album_ids")
        if album_ids is not None:
            if not isinstance(album_ids, list) or any(not isinstance(value, str) or not value.strip() for value in album_ids):
                raise ValueError("album_ids must be a list of album IDs")
            album_ids = list(dict.fromkeys(value.strip() for value in album_ids))
            album_id = None
        if source == "album" and not (album_ids if album_ids is not None else album_id):
            raise ValueError("album_ids must contain at least one album")
        order_direction = body.get("order_direction", "desc")
        if order_direction not in ("asc", "desc", "random"):
            raise ValueError("order_direction must be asc, desc, or random")
        order_field = body.get("order_field", "fileCreatedAt")
        if order_field not in ("fileCreatedAt", "localDateTime", "fileSizeInBytes", "rating"):
            raise ValueError("order_field is not supported by Immich 3.2")
        orientation = body.get("orientation", "any")
        if orientation not in ("any", "portrait", "landscape", "square"):
            raise ValueError("orientation must be any, portrait, landscape, or square")
        name = str(body.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")
        connection_id = str(body.get("connection_id", "default")).strip()
        if not connection_id:
            raise ValueError("connection_id is required")
        return FrameConfig(
            frame_id=frame_id or str(uuid.uuid4()), name=name, connection_id=connection_id, mode=mode,
            pair_window_days=max(0, min(7, int(body.get("pair_window_days", 2)))),
            slideshow_interval=max(10, min(86400, int(body.get("slideshow_interval", 30)))), filter=compile_filter(raw_filter),
            source=source, album_id=album_id, album_ids=album_ids, memory_window_days=max(0, min(7, int(body.get("memory_window_days", 2)))),
            fallback_to_all=bool(body.get("fallback_to_all", False)), smart_query=body.get("smart_query"),
            smart_reference_asset_id=body.get("smart_reference_asset_id"), order_field=order_field, order_direction=order_direction,
            fit=fit, orientation=orientation,
        )

    async def home(self, _: web.Request) -> web.Response:
        return web.Response(text="""<!doctype html><meta name=viewport content='width=device-width'><title>Immich Frames</title>
<h1>Immich Frames</h1><p>Create a Home Assistant photo frame.</p>
<form id=c><h2>Immich connection</h2><label>Name <input name=name required></label><label>URL <input name=url type=url required></label><label>Read-only API key <input name=api_key type=password required></label><button>Connect</button></form>
<form id=f><label>Name <input name=name required></label><label>Connection <select name=connection_id id=connections></select></label><label>Source <select name=source><option value=all>All photos</option><option value=album>Albums</option><option value=memories>Memories</option><option value=smart>Keywords</option></select></label><fieldset id=album-picker hidden><legend>Albums</legend><label>Search albums <input id=album-search type=search></label><button id=reload-albums type=button>Reload albums</button><p id=album-status role=status></p><div id=album-options></div></fieldset><label>Keywords <input name=smart_query></label><label>Photo orientation filter <select name=orientation><option value=any>Mixed (landscapes and portraits)</option><option value=portrait>Portrait photos only</option><option value=landscape>Landscape photos only</option><option value=square>Square photos only</option></select></label><label>Mode <select name=mode><option value=single>Single portrait images</option><option value=pairs>Pair portrait photos</option></select></label><label>Pair window (days) <input name=pair_window_days type=number min=0 max=7 value=2></label><label>Memory window (days) <input name=memory_window_days type=number min=0 max=7 value=2></label><label><input name=fallback_to_all type=checkbox> Fall back to normal filter if memories are empty</label><label>Order <select name=order_direction><option value=random>Random</option><option value=desc>Newest first</option><option value=asc>Oldest first</option></select></label><button>Create frame</button></form>
<pre id=frames>Loading…</pre><script>
const out=document.querySelector('#frames');
const form=document.querySelector('#f');
const connections=document.querySelector('#connections');
const picker=document.querySelector('#album-picker');
const albumOptions=document.querySelector('#album-options');
const albumStatus=document.querySelector('#album-status');
let albumRequest=0;
function filterAlbums(){
  const query=document.querySelector('#album-search').value.toLocaleLowerCase();
  for(const label of albumOptions.children) label.style.display=label.textContent.toLocaleLowerCase().includes(query)?'block':'none';
}
async function loadAlbums(){
  const request=++albumRequest;
  const selected=new Set([...albumOptions.querySelectorAll('input:checked')].map(input=>input.value));
  albumOptions.replaceChildren();
  picker.hidden=form.elements.source.value!=='album';
  if(picker.hidden) return;
  if(!connections.value){albumStatus.textContent='Connect to Immich to load albums.';return;}
  albumStatus.textContent='Loading albums…';
  try{
    const response=await fetch('/api/catalog/albums?connection_id='+encodeURIComponent(connections.value));
    if(!response.ok) throw new Error('Could not load albums. Check the connection and album.read permission, then reload.');
    const albums=await response.json();
    if(!Array.isArray(albums)||albums.some(album=>!album||typeof album.id!=='string'||typeof album.albumName!=='string')) throw new Error('Immich returned an invalid album list. Try reloading.');
    if(request!==albumRequest) return;
    const names=new Map();
    for(const album of albums) names.set(album.id,album.albumName.trim()||'Untitled album');
    const counts=new Map();
    for(const name of names.values()) counts.set(name.toLocaleLowerCase(),(counts.get(name.toLocaleLowerCase())||0)+1);
    for(const [id,name] of [...names].sort((a,b)=>a[1].localeCompare(b[1])||a[0].localeCompare(b[0]))){
      const label=document.createElement('label');
      label.style.display='block';
      const input=document.createElement('input');
      input.type='checkbox';input.name='album_ids';input.value=id;input.checked=selected.has(id);
      label.append(input,document.createTextNode(counts.get(name.toLocaleLowerCase())>1?`${name} (${id})`:name));
      albumOptions.append(label);
    }
    albumStatus.textContent=names.size?'Select one or more albums. Photos from all selected albums will be shown together.':'No albums are available. Create or share an album in Immich, then reload.';
    filterAlbums();
  }catch(error){if(request===albumRequest) albumStatus.textContent=error.message;}
}
async function load(){
  out.textContent=JSON.stringify(await (await fetch('/api/frames')).json(),null,2);
  const saved=connections.value;
  const values=await (await fetch('/api/connections')).json();
  connections.replaceChildren(...values.map(connection=>new Option(connection.name,connection.id)));
  if(values.some(connection=>connection.id===saved)) connections.value=saved;
  await loadAlbums();
}
connections.onchange=()=>{albumOptions.replaceChildren();loadAlbums();};
form.elements.source.onchange=loadAlbums;
document.querySelector('#reload-albums').onclick=loadAlbums;
document.querySelector('#album-search').oninput=filterAlbums;
document.querySelector('#c').onsubmit=async e=>{
  e.preventDefault();
  const response=await fetch('/api/connections',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});
  if(!response.ok){alert(await response.text());return;}
  e.target.reset();await load();
};
form.onsubmit=async e=>{
  e.preventDefault();
  const fields=new FormData(form);
  const data=Object.fromEntries(fields);
  data.album_ids=fields.getAll('album_ids');
  if(data.source==='album'&&!data.album_ids.length){albumStatus.textContent='Choose at least one album to continue.';return;}
  data.fallback_to_all=form.elements.fallback_to_all.checked;
  for(const key of ['pair_window_days','memory_window_days']) data[key]=Number(data[key]||0);
  const response=await fetch('/api/frames',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});
  if(!response.ok){alert(await response.text());return;}
  form.reset();await load();
};
load();
</script>""", content_type="text/html")

    async def list_frames(self, _: web.Request) -> web.Response:
        return web.json_response([{"frame_id": f.frame_id, "name": f.name, "connection_id": f.connection_id, "mode": f.mode, "orientation": f.orientation} for f in self.storage.list_frames()])

    async def list_connections(self, _: web.Request) -> web.Response:
        return web.json_response(self.storage.list_connections())

    async def create_connection(self, request: web.Request) -> web.Response:
        body = await request.json()
        try:
            connection_id = str(body.get("id") or uuid.uuid4()).strip()
            name, url, api_key = str(body["name"]).strip(), str(body["url"]).strip(), str(body["api_key"]).strip()
        except (AttributeError, KeyError, TypeError) as exc:
            raise web.HTTPBadRequest(text="name, url and api_key are required") from exc
        parsed_url = urlparse(url)
        if not connection_id or not name or not api_key or parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise web.HTTPBadRequest(text="name, url and api_key are required; url must be http or https")
        try:
            async with ImmichClient(url, api_key) as test_client:
                version = await test_client.version()
        except Exception as exc:
            raise web.HTTPBadGateway(text=f"Unable to verify Immich connection: {exc}") from exc
        self.storage.save_connection(connection_id, name, url, api_key)
        client = ImmichClient(url, api_key)
        self.clients[connection_id] = client
        return web.json_response({"id": connection_id, "name": name, "url": url, "version": version}, status=201)

    async def delete_connection(self, request: web.Request) -> web.Response:
        connection_id = request.match_info["connection_id"]
        if connection_id == "default" and self.config.get("immich_url"):
            raise web.HTTPConflict(text="The configured default connection cannot be deleted")
        if any(frame.connection_id == connection_id for frame in self.storage.list_frames()):
            raise web.HTTPConflict(text="Connection is used by a frame")
        if self.storage.get_connection(connection_id) is None:
            raise web.HTTPNotFound()
        client = self.clients.pop(connection_id, None)
        if client:
            await client.close()
        self.storage.delete_connection(connection_id)
        return web.Response(status=204)

    async def export_config(self, _: web.Request) -> web.Response:
        return web.json_response({"frames": [{"frame_id": f.frame_id, "name": f.name, "connection_id": f.connection_id, "mode": f.mode, "pair_window_days": f.pair_window_days, "slideshow_interval": f.slideshow_interval, "filter": f.filter, "source": f.source, "album_id": f.album_id, "album_ids": f.album_ids, "memory_window_days": f.memory_window_days, "fallback_to_all": f.fallback_to_all, "smart_query": f.smart_query, "smart_reference_asset_id": f.smart_reference_asset_id, "order_field": f.order_field, "order_direction": f.order_direction, "output_width": f.output_width, "output_height": f.output_height, "fit": f.fit, "orientation": f.orientation} for f in self.storage.list_frames()]})

    async def import_config(self, request: web.Request) -> web.Response:
        body = await request.json()
        entries = body.get("frames") if isinstance(body, dict) else None
        if not isinstance(entries, list):
            raise web.HTTPBadRequest(text="frames must be an array")
        try:
            frames: list[FrameConfig] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("each frame must be an object")
                frame_id = str(entry.get("frame_id") or uuid.uuid4())
                frame = self._frame_from_body(entry, frame_id)
                self._client_for(frame.connection_id)
                frames.append(frame)
            imported: list[str] = []
            for frame in frames:
                self.storage.save_frame(frame)
                self.start_frame(frame)
                imported.append(frame.frame_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, FilterValidationError) as exc:
            raise web.HTTPBadRequest(text=f"Invalid frame configuration: {exc}") from exc
        return web.json_response({"frame_ids": imported}, status=201)

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
                "name": body.get("name", frame.name), "connection_id": body.get("connection_id", frame.connection_id), "mode": body.get("mode", frame.mode),
                "pair_window_days": body.get("pair_window_days", frame.pair_window_days),
                "slideshow_interval": body.get("slideshow_interval", frame.slideshow_interval), "filter": body.get("filter", frame.filter),
                "source": body.get("source", frame.source), "album_id": body.get("album_id", frame.album_id), "album_ids": body.get("album_ids", None if "album_id" in body else frame.album_ids), "memory_window_days": body.get("memory_window_days", frame.memory_window_days), "fallback_to_all": body.get("fallback_to_all", frame.fallback_to_all),
                "smart_query": body.get("smart_query", frame.smart_query), "smart_reference_asset_id": body.get("smart_reference_asset_id", frame.smart_reference_asset_id),
                "order_field": body.get("order_field", frame.order_field), "order_direction": body.get("order_direction", frame.order_direction),
                "output_width": body.get("output_width", frame.output_width), "output_height": body.get("output_height", frame.output_height), "fit": body.get("fit", frame.fit), "orientation": body.get("orientation", frame.orientation),
            }, frame.frame_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise web.HTTPBadRequest(text=f"Invalid frame configuration: {exc}") from exc
        self._client_for(updated.connection_id)
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

    async def capabilities(self, request: web.Request) -> web.Response:
        try:
            connection_id = request.query.get("connection_id", "default")
            return web.json_response(await self._client_for(connection_id).capabilities())
        except Exception:
            return web.json_response({"version": "unavailable", "structured_search": False, "memories": False, "smart_search": False, "ocr": False}, status=503)

    async def catalog(self, request: web.Request) -> web.Response:
        kind = request.match_info["kind"]
        connection_id = request.query.get("connection_id", "default")
        method_name = {"albums": "albums", "people": "people", "tags": "tags", "memories": "memories"}.get(kind)
        if method_name is None:
            raise web.HTTPNotFound()
        try:
            values = getattr(self._client_for(connection_id), method_name)
        except ValueError as exc:
            raise web.HTTPNotFound(text=str(exc)) from exc
        return web.json_response(await values())

    def application(self) -> web.Application:
        app = web.Application()
        app.add_routes([web.get("/", self.home), web.get("/api/health", self.health), web.get("/api/capabilities", self.capabilities), web.get("/api/catalog/{kind}", self.catalog), web.get("/api/connections", self.list_connections), web.post("/api/connections", self.create_connection), web.delete("/api/connections/{connection_id}", self.delete_connection), web.get("/api/export", self.export_config), web.post("/api/import", self.import_config), web.get("/api/frames", self.list_frames), web.post("/api/frames", self.create_frame), web.put("/api/frames/{frame_id}", self.update_frame), web.post("/api/frames/{frame_id}/refresh", self.refresh), web.delete("/api/frames/{frame_id}", self.delete_frame)])
        app.on_cleanup.append(self.shutdown)
        return app

    async def shutdown(self, _: web.Application) -> None:
        for task in self.tasks.values():
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for client in self.clients.values():
            await client.close()
        if self.publisher:
            self.publisher.close()

    async def start_existing(self) -> None:
        self.loop = asyncio.get_running_loop()
        for frame in self.storage.list_frames():
            self.restore_cached(frame)
            self.start_frame(frame)

    def restore_cached(self, frame: FrameConfig) -> None:
        image_path = self.cache_dir / f"{frame.frame_id}.jpg"
        state_path = self.cache_dir / f"{frame.frame_id}.json"
        if not image_path.exists() or not state_path.exists():
            return
        try:
            with Image.open(image_path) as image:
                if image.size != OUTPUT_SIZE:
                    return
            state = json.loads(state_path.read_text())
            self.metadata_role[frame.frame_id] = state.get("selected_role", "primary")
            photos = [Photo.from_cache(state["primary"])]
            if state.get("secondary", {}).get("available"):
                photos.append(Photo.from_cache(state["secondary"]))
            slide = Slide(frame.frame_id, int(state.get("generation", 0)), tuple(photos), image_path.read_bytes(), state.get("layout", "single"))
            self.generation[frame.frame_id] = slide.generation
            self.slides[frame.frame_id] = slide
            self.history[frame.frame_id] = [slide]
            if self.publisher:
                self.publisher.publish_frame(frame, slide, using_cache=True, status="cached", role=self.metadata_role.get(frame.frame_id, "primary"), cache_size=self.cache_size())
        except (OSError, KeyError, ValueError, TypeError):
            LOG.warning("Ignoring incomplete cache for frame %s", frame.name)

    def cache_size(self) -> int:
        return sum(path.stat().st_size for path in self.cache_dir.iterdir() if path.is_file())

    def enforce_cache_limit(self) -> int:
        files = sorted((path for path in self.cache_dir.iterdir() if path.is_file()), key=lambda path: path.stat().st_mtime)
        total = self.cache_size()
        for path in files:
            if total <= self.cache_limit_bytes:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size
        return total


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
