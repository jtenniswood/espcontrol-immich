"""Translate the public container format; never use it as runtime state."""

from __future__ import annotations

import json
import uuid
from dataclasses import fields

from custom_components.immich_frames.core.settings import FrameSettings
from custom_components.immich_frames.core.filtering import compile_filter
from .models import FrameConfig


def saved_frame(data: dict) -> FrameConfig:
    """Preserve the effective v1 container dimensions and cover/contain choice."""
    config = dict(data)
    version = config.get("settings_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Frame settings require a supported application version")
    if version == 1:
        config.setdefault("fit", "cover")
        config["screen_shape"] = "landscape"
        config["photo_fit"] = "show_full" if config["fit"] == "contain" else "crop"
        config["settings_version"] = 2
    config.pop("pairs_only", None)
    frame = FrameConfig(**config)
    frame.settings()
    return frame


def frame_from_body(body: dict, frame_id: str | None = None) -> FrameConfig:
    """Keep public aliases while delegating product rules to FrameSettings."""
    if not isinstance(body, dict):
        raise ValueError("frame must be an object")
    if body.get("settings_version", 2) not in (1, 2):
        raise ValueError("Unsupported frame settings version")
    name, connection = body.get("name", ""), body.get("connection_id", "default")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name is required")
    if not isinstance(connection, str) or not connection.strip():
        raise ValueError("connection_id is required")
    fit = body.get("fit", "cover")
    if fit not in ("cover", "contain"):
        raise ValueError("fit must be cover or contain")
    raw_filter = body.get("filter", {})
    if isinstance(raw_filter, str):
        raw_filter = json.loads(raw_filter)
    values = {
        key: value
        for key, value in body.items()
        if key in {f.name for f in fields(FrameConfig)}
    }
    values.update(
        frame_id=frame_id or str(uuid.uuid4()),
        name=name.strip(),
        connection_id=connection.strip(),
        filter=compile_filter(raw_filter),
        settings_version=2,
    )
    values["photo_fit"] = body.get("photo_fit") or (
        "show_full" if fit == "contain" or "fit" not in body else "crop"
    )
    frame = FrameConfig(**values)
    settings: FrameSettings = frame.settings()
    # Keep the exported legacy shape, but use normalized canonical values.
    if body.get("album_ids") is not None:
        values.update(album_ids=list(settings.album_ids), album_id=None)
    return FrameConfig(**values)
