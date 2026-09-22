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

from .immich_client import ImmichClient, ImmichError
from .models import FrameConfig, Photo, Slide
from .filtering import FilterValidationError
from .selection import ClientAdapter
from custom_components.immich_frames.core.engine import snapshot
from dataclasses import asdict
from custom_components.immich_frames.core.session import FrameSession
from custom_components.immich_frames.core.cache import (
    SnapshotStore,
    connection_identity,
    signature,
)
from .storage import Storage
from . import __version__

LOG = logging.getLogger("immich_frames")


class FrameApp:
    def __init__(self, config: dict, data_dir: Path) -> None:
        self.config = config
        self.storage = Storage(data_dir)
        if (
            not self.storage.get_connection("default")
            and config.get("immich_url")
            and config.get("immich_api_key")
        ):
            self.storage.save_connection(
                "default",
                "Default Immich",
                config["immich_url"],
                config["immich_api_key"],
            )
        self.sessions: dict[str, FrameSession] = {}
        self.clients: dict[str, ImmichClient] = {}
        self.client = (
            self._client_for("default")
            if self.storage.get_connection("default")
            else None
        )
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.cache_dir = data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_limit_bytes = (
            max(16, int(config.get("cache_limit_mb", 256))) * 1024 * 1024
        )

    def _client_for(self, connection_id: str) -> ImmichClient:
        if connection_id in self.clients:
            return self.clients[connection_id]
        connection = self.storage.get_connection(connection_id)
        if connection is None:
            raise ValueError(f"Unknown Immich connection: {connection_id}")
        client = ImmichClient(connection[1], connection[2])
        self.clients[connection_id] = client
        return client

    def _session_for(self, frame: FrameConfig) -> FrameSession:
        if frame.frame_id not in self.sessions:

            async def produce(settings, generation, recent_ids, **clock):
                return await snapshot(
                    ClientAdapter(self._client_for(frame.connection_id)),
                    settings,
                    generation,
                    recent_ids,
                    **clock,
                )

            self.sessions[frame.frame_id] = FrameSession(
                frame.settings(),
                self._connection_identity(frame),
                self._store(frame),
                produce,
            )
        return self.sessions[frame.frame_id]

    @staticmethod
    def _legacy_slide(frame_id, result):
        return Slide(
            frame_id,
            result.generation,
            tuple(Photo.from_record(p) for p in result.photos),
            result.image,
            result.layout,
            result.created_at,
        )

    @property
    def slides(self):
        """Compatibility view; the session remains the sole state owner."""
        return {
            key: self._legacy_slide(key, session.current)
            for key, session in self.sessions.items()
            if session.current
        }

    @property
    def history(self):
        return {
            key: [self._legacy_slide(key, item) for item in session.history]
            for key, session in self.sessions.items()
        }

    async def refresh_frame(self, frame: FrameConfig, force: bool = False) -> None:
        try:
            await self._session_for(frame).refresh(force=force)
            await asyncio.to_thread(self.enforce_cache_limit)
        except ImmichError:
            LOG.warning("Unable to refresh frame %s", frame.name, exc_info=True)

    async def frame_loop(self, frame: FrameConfig, *, delay_first=False) -> None:
        if delay_first:
            await asyncio.sleep(self._session_for(frame).settings.interval)
        while True:
            await self.refresh_frame(frame)
            await asyncio.sleep(self._session_for(frame).settings.interval)

    def start_frame(self, frame: FrameConfig) -> None:
        session = self._session_for(frame)
        unchanged = signature(session.settings, session.connection) == signature(
            frame.settings(), self._connection_identity(frame)
        )
        session.configure(frame.settings(), self._connection_identity(frame))

        async def produce(settings, generation, recent_ids, **clock):
            return await snapshot(
                ClientAdapter(self._client_for(frame.connection_id)),
                settings,
                generation,
                recent_ids,
                **clock,
            )

        session.produce = produce
        old = self.tasks.pop(frame.frame_id, None)
        if old:
            old.cancel()
        self.tasks[frame.frame_id] = asyncio.create_task(
            self.frame_loop(frame, delay_first=bool(old and unchanged))
        )

    async def create_frame(self, request: web.Request) -> web.Response:
        body = await request.json()
        try:
            frame = self._frame_from_body(body)
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            FilterValidationError,
        ) as exc:
            raise web.HTTPBadRequest(
                text=f"Invalid frame configuration: {exc}"
            ) from exc
        try:
            self._client_for(frame.connection_id)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        self.storage.save_frame(frame)
        self.start_frame(frame)
        return web.json_response({"frame_id": frame.frame_id}, status=201)

    @staticmethod
    def _frame_from_body(
        body: dict[str, Any], frame_id: str | None = None
    ) -> FrameConfig:
        from .compatibility import frame_from_body

        return frame_from_body(body, frame_id)

    async def home(self, _: web.Request) -> web.Response:
        from .ui import home_page

        return web.Response(text=home_page(), content_type="text/html")

    async def list_frames(self, _: web.Request) -> web.Response:
        return web.json_response(
            [
                {
                    "frame_id": f.frame_id,
                    "name": f.name,
                    "connection_id": f.connection_id,
                    "mode": f.mode,
                    "orientation": f.orientation,
                }
                for f in self.storage.list_frames()
            ]
        )

    async def list_connections(self, _: web.Request) -> web.Response:
        return web.json_response(self.storage.list_connections())

    async def create_connection(self, request: web.Request) -> web.Response:
        body = await request.json()
        try:
            connection_id = str(body.get("id") or uuid.uuid4()).strip()
            name, url, api_key = (
                str(body["name"]).strip(),
                str(body["url"]).strip(),
                str(body["api_key"]).strip(),
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise web.HTTPBadRequest(text="name, url and api_key are required") from exc
        parsed_url = urlparse(url)
        if (
            not connection_id
            or not name
            or not api_key
            or parsed_url.scheme not in ("http", "https")
            or not parsed_url.netloc
        ):
            raise web.HTTPBadRequest(
                text="name, url and api_key are required; url must be http or https"
            )
        try:
            async with ImmichClient(url, api_key) as test_client:
                await test_client.validate_connection()
                version = await test_client.version()
        except Exception as exc:
            raise web.HTTPBadGateway(
                text=f"Unable to verify Immich connection: {exc}"
            ) from exc
        self.storage.save_connection(connection_id, name, url, api_key)
        for frame in self.storage.list_frames():
            if frame.connection_id == connection_id and frame.frame_id in self.sessions:
                self.sessions[frame.frame_id].configure(
                    frame.settings(), self._connection_identity(frame)
                )
        old_client = self.clients.pop(connection_id, None)
        if old_client:
            await old_client.close()
        client = ImmichClient(url, api_key)
        self.clients[connection_id] = client
        for frame in self.storage.list_frames():
            if frame.connection_id == connection_id:
                self.start_frame(frame)
        return web.json_response(
            {"id": connection_id, "name": name, "url": url, "version": version},
            status=201,
        )

    async def delete_connection(self, request: web.Request) -> web.Response:
        connection_id = request.match_info["connection_id"]
        if connection_id == "default" and self.config.get("immich_url"):
            raise web.HTTPConflict(
                text="The configured default connection cannot be deleted"
            )
        if any(
            frame.connection_id == connection_id for frame in self.storage.list_frames()
        ):
            raise web.HTTPConflict(text="Connection is used by a frame")
        if self.storage.get_connection(connection_id) is None:
            raise web.HTTPNotFound()
        client = self.clients.pop(connection_id, None)
        if client:
            await client.close()
        self.storage.delete_connection(connection_id)
        return web.Response(status=204)

    async def export_config(self, _: web.Request) -> web.Response:
        return web.json_response(
            {"frames": [asdict(f) for f in self.storage.list_frames()]}
        )

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
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            FilterValidationError,
        ) as exc:
            raise web.HTTPBadRequest(
                text=f"Invalid frame configuration: {exc}"
            ) from exc
        return web.json_response({"frame_ids": imported}, status=201)

    async def refresh(self, request: web.Request) -> web.Response:
        frame = next(
            (
                item
                for item in self.storage.list_frames()
                if item.frame_id == request.match_info["frame_id"]
            ),
            None,
        )
        if frame is None:
            raise web.HTTPNotFound()
        await self.refresh_frame(frame)
        return web.json_response(
            {
                "frame_id": frame.frame_id,
                "generation": self._session_for(frame).generation,
            }
        )

    async def update_frame(self, request: web.Request) -> web.Response:
        frame = next(
            (
                item
                for item in self.storage.list_frames()
                if item.frame_id == request.match_info["frame_id"]
            ),
            None,
        )
        if frame is None:
            raise web.HTTPNotFound()
        body = await request.json()
        try:
            values = {**asdict(frame), **body}
            if "album_id" in body and "album_ids" not in body:
                values["album_ids"] = None
            updated = self._frame_from_body(values, frame.frame_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise web.HTTPBadRequest(
                text=f"Invalid frame configuration: {exc}"
            ) from exc
        self._client_for(updated.connection_id)
        self.storage.save_frame(updated)
        self.start_frame(updated)
        return web.json_response({"frame_id": updated.frame_id})

    async def delete_frame(self, request: web.Request) -> web.Response:
        frame_id = request.match_info["frame_id"]
        frame = next(
            (item for item in self.storage.list_frames() if item.frame_id == frame_id),
            None,
        )
        task = self.tasks.pop(frame_id, None)
        if task:
            task.cancel()
        if session := self.sessions.pop(frame_id, None):
            await session.close()
        self.storage.delete_frame(frame_id)
        return web.Response(status=204)

    async def health(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "version": __version__})

    async def capabilities(self, request: web.Request) -> web.Response:
        try:
            connection_id = request.query.get("connection_id", "default")
            return web.json_response(
                await self._client_for(connection_id).capabilities()
            )
        except Exception:
            return web.json_response(
                {
                    "version": "unavailable",
                    "structured_search": False,
                    "memories": False,
                    "smart_search": False,
                    "ocr": False,
                },
                status=503,
            )

    async def catalog(self, request: web.Request) -> web.Response:
        kind = request.match_info["kind"]
        connection_id = request.query.get("connection_id", "default")
        method_name = {
            "albums": "albums",
            "people": "people",
            "tags": "tags",
            "memories": "memories",
        }.get(kind)
        if method_name is None:
            raise web.HTTPNotFound()
        try:
            values = getattr(self._client_for(connection_id), method_name)
        except ValueError as exc:
            raise web.HTTPNotFound(text=str(exc)) from exc
        return web.json_response(await values())

    def _requested_session(self, request):
        frame_id = request.match_info["frame_id"]
        if frame_id not in self.sessions:
            raise web.HTTPNotFound()
        return self.sessions[frame_id]

    async def frame_state(self, request):
        session = self._requested_session(request)
        result = session.current
        if result is None:
            raise web.HTTPServiceUnavailable(text="Waiting for a photo")
        state = self._legacy_slide(request.match_info["frame_id"], result).state()
        # A versioned image URL prevents a second request returning a newer image
        # than the metadata. Relative URLs also work behind HA ingress.
        state.update(
            paused=session.paused,
            status=result.status,
            using_cache=result.using_cache,
            image_url=f"api/frames/{request.match_info['frame_id']}/image?generation={result.generation}",
        )
        return web.json_response(state, headers={"Cache-Control": "no-store"})

    async def frame_image(self, request):
        session = self._requested_session(request)
        result = session.current
        generation = request.query.get("generation")
        if generation is not None:
            result = next(
                (
                    item
                    for item in reversed(session.history)
                    if str(item.generation) == generation
                ),
                None,
            )
            if result is None:
                raise web.HTTPConflict(text="Photo changed; reload the frame state")
        if result is None:
            raise web.HTTPServiceUnavailable(text="Waiting for a photo")
        return web.Response(
            body=result.image,
            content_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    async def frame_command(self, request):
        session = self._requested_session(request)
        command = request.match_info["command"]
        try:
            if command == "next":
                await session.next()
            elif command == "previous":
                session.previous()
            elif command == "pause":
                session.pause()
            elif command == "resume":
                session.resume()
            elif command == "clear_cache":
                await session.clear_cache()
            else:
                raise web.HTTPNotFound()
        except ImmichError as exc:
            raise web.HTTPBadGateway(text=str(exc)) from exc
        return web.json_response({"paused": session.paused})

    def application(self) -> web.Application:
        app = web.Application()
        app.add_routes(
            [
                web.get("/", self.home),
                web.get("/api/health", self.health),
                web.get("/api/capabilities", self.capabilities),
                web.get("/api/catalog/{kind}", self.catalog),
                web.get("/api/connections", self.list_connections),
                web.post("/api/connections", self.create_connection),
                web.delete("/api/connections/{connection_id}", self.delete_connection),
                web.get("/api/export", self.export_config),
                web.post("/api/import", self.import_config),
                web.get("/api/frames", self.list_frames),
                web.post("/api/frames", self.create_frame),
                web.put("/api/frames/{frame_id}", self.update_frame),
                web.post("/api/frames/{frame_id}/refresh", self.refresh),
                web.delete("/api/frames/{frame_id}", self.delete_frame),
            ]
        )
        app.add_routes(
            [
                web.get("/api/frames/{frame_id}/state", self.frame_state),
                web.get("/api/frames/{frame_id}/image", self.frame_image),
                web.post(
                    "/api/frames/{frame_id}/commands/{command}", self.frame_command
                ),
            ]
        )
        app.on_startup.append(self.start_existing)
        app.on_cleanup.append(self.shutdown)
        return app

    async def shutdown(self, _: web.Application) -> None:
        for task in self.tasks.values():
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for session in self.sessions.values():
            await session.close()
        for client in self.clients.values():
            await client.close()

    async def start_existing(self, _app=None) -> None:
        for frame in self.storage.list_frames():
            await self._session_for(frame).restore()
            self.start_frame(frame)

    def _store(self, frame):
        return SnapshotStore(self.cache_dir / f"{frame.frame_id}.json")

    def _connection_identity(self, frame):
        connection = self.storage.get_connection(frame.connection_id)
        return (
            connection_identity(connection[1], connection[2])
            if connection
            else connection_identity(frame.connection_id, "")
        )

    def cache_size(self) -> int:
        return sum(
            path.stat().st_size for path in self.cache_dir.iterdir() if path.is_file()
        )

    def enforce_cache_limit(self) -> int:
        files = sorted(
            (
                path
                for path in self.cache_dir.iterdir()
                if path.is_file() and not path.name.startswith(".")
            ),
            key=lambda path: path.stat().st_mtime,
        )
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
    config = (
        json.loads(config_path.read_text())
        if config_path.exists()
        else {"immich_url": "", "immich_api_key": ""}
    )
    if not config.get("immich_url") or not config.get("immich_api_key"):
        LOG.error(
            "Configure immich_url and immich_api_key before starting Immich Frames"
        )
    frame_app = FrameApp(config, path.parent)
    web.run_app(frame_app.application(), host="0.0.0.0", port=8099)
