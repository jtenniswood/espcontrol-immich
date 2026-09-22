"""Atomic, verified slide records shared by every installation type."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from .models import FrameSnapshot
from .rendering import image_size
from .settings import FrameSettings

CACHE_VERSION = 2
RENDER_VERSION = 1


def signature(options: dict, connection: str, *, today: date | None = None) -> str:
    settings = FrameSettings.from_options(options).options()
    settings.pop("interval")  # Timer edits do not change the rendered photo.
    if settings["source"] != "album":
        settings.pop("album_ids")
    else:
        settings["album_ids"].sort()
    if settings["source"] != "smart":
        settings.pop("smart_query")
        settings.pop("smart_reference_asset_id")
    if settings["source"] != "memories":
        settings.pop("memory_window_days")
        settings.pop("fallback_to_all")
    else:
        settings["memory_date"] = (today or date.today()).isoformat()
    data = {"settings": settings, "connection": connection, "renderer": RENDER_VERSION}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def connection_identity(url: str, api_key: str) -> str:
    """Account-sensitive identity; never store the URL or API key in the cache."""
    return hashlib.sha256(json.dumps([url.rstrip("/"), api_key]).encode()).hexdigest()


class SnapshotStore:
    def __init__(self, path: Path):
        self.path = path

    def write(
        self,
        snapshot: FrameSnapshot,
        options: FrameSettings,
        connection: str,
        *,
        today: date | None = None,
    ) -> None:
        settings = FrameSettings.from_options(options)
        if image_size(snapshot.image) != settings.output_size:
            raise ValueError("Snapshot dimensions do not match the frame")
        state = {
            "cache_version": CACHE_VERSION,
            "render_version": RENDER_VERSION,
            "signature": signature(settings, connection, today=today),
            "output_size": settings.output_size,
            "generation": snapshot.generation,
            "layout": snapshot.layout,
            "created_at": snapshot.created_at.isoformat(),
            "matching_assets": snapshot.matching_assets,
            "photos": [
                {key: value for key, value in photo.items() if key != "capture_dt"}
                for photo in snapshot.photos
            ],
            "image": base64.b64encode(snapshot.image).decode("ascii"),
            "sha256": hashlib.sha256(snapshot.image).hexdigest(),
        }
        state["record_sha256"] = hashlib.sha256(
            json.dumps(state, sort_keys=True).encode()
        ).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One file and one replacement: a crash cannot mix generations.
        name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as stream:
                name = stream.name
                json.dump(state, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if name is not None:
                Path(name).unlink(missing_ok=True)

    def read(
        self,
        options: FrameSettings,
        connection: str,
        *,
        now: datetime | None = None,
        today: date | None = None,
    ) -> FrameSnapshot | None:
        try:
            state = json.loads(self.path.read_text())
            if not isinstance(state, dict):
                return None
            checksum = state.pop("record_sha256")
            if (
                hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
                != checksum
            ):
                return None
            if (
                state["cache_version"] != CACHE_VERSION
                or state["render_version"] != RENDER_VERSION
            ):
                return None
            if state["signature"] != signature(options, connection, today=today):
                return None
            settings = FrameSettings.from_options(options)
            if state["output_size"] != list(settings.output_size):
                return None
            image = base64.b64decode(state["image"], validate=True)
            if (
                hashlib.sha256(image).hexdigest() != state["sha256"]
                or image_size(image) != settings.output_size
            ):
                return None
            photos = state["photos"]
            if not isinstance(photos, list) or len(photos) not in (1, 2):
                return None
            if any(
                not isinstance(p, dict)
                or not isinstance(p.get("id"), str)
                or not p["id"]
                for p in photos
            ):
                return None
            if state["layout"] != ("single" if len(photos) == 1 else "side_by_side"):
                return None
            # Rolling time ranges must still apply when a frame restarts offline.
            if settings.time_range != "all_time":
                from .engine import _with_time_range, _datetime

                bounds = _with_time_range(
                    {}, settings.time_range, now or datetime.now(timezone.utc)
                )["takenAt"]
                lower, upper = _datetime(bounds["gte"]), _datetime(bounds["lte"])
                for photo in photos:
                    captured = _datetime(photo.get("captured"))
                    if captured is None:
                        return None
                    if captured.tzinfo is None:
                        captured = captured.replace(tzinfo=timezone.utc)
                    if not lower <= captured <= upper:
                        return None
            return FrameSnapshot(
                image,
                int(state["generation"]),
                tuple(photos),
                state["layout"],
                datetime.fromisoformat(state["created_at"]),
                int(state["matching_assets"]),
                connected=False,
                using_cache=True,
                status="cached",
            )
        except (OSError, KeyError, TypeError, ValueError):
            # Includes all old two-file caches: they cannot prove their source.
            return None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self.path.with_suffix(".jpg").unlink(missing_ok=True)


async def finish_write(future):
    """Do not release a host's update lock while its disk write is still running."""
    import asyncio

    task = asyncio.ensure_future(future)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        finally:
            raise
