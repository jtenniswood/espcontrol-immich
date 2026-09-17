from __future__ import annotations

from typing import Any
from datetime import date, timedelta

from .models import FrameConfig, Photo


ALLOWED_VISIBILITY = ["timeline", "archive", "hidden"]


def safe_filter(user_filter: dict[str, Any]) -> dict[str, Any]:
    """Apply the frame's non-negotiable safety constraints to an Immich filter."""
    result = dict(user_filter)
    result["type"] = {"eq": "IMAGE"}
    result["trashedAt"] = {"eq": None}
    requested_visibility = result.get("visibility")
    if requested_visibility is None:
        result["visibility"] = {"eq": "timeline"}
    else:
        # Never permit a user rule to widen the query to locked assets.
        if "in" in requested_visibility:
            visible = [item for item in requested_visibility["in"] if item in ALLOWED_VISIBILITY]
            result["visibility"] = {"in": visible or ["timeline"]}
        elif requested_visibility.get("eq") not in ALLOWED_VISIBILITY:
            result["visibility"] = {"eq": "timeline"}
    return result


def _with_memory_ids(query: dict[str, Any], asset_ids: list[str]) -> dict[str, Any] | None:
    """Intersect a filter with memory IDs using Immich's scalar ID operators."""
    result = dict(query)
    branches = []
    for branch in result.pop("or", [{}]):
        condition = branch.get("id", {})
        for asset_id in asset_ids:
            if condition.get("eq", asset_id) == asset_id and condition.get("ne") != asset_id:
                branches.append({**branch, "id": {"eq": asset_id}})
    return {**result, "or": branches} if branches else None


async def select_candidates(client: Any, frame: FrameConfig, today: str | None = None, size: int = 100) -> list[Photo]:
    """Resolve the configured source into authorized photo candidates."""
    query = safe_filter(frame.filter)
    if frame.source == "album":
        album_ids = frame.album_ids if frame.album_ids is not None else ([frame.album_id] if frame.album_id else [])
        if not album_ids:
            return []
        query["albumIds"] = {"any": list(dict.fromkeys(album_ids))}
        random_order = frame.order_direction == "random"
        photos = await client.search(query, size=size, random=random_order, order_field=frame.order_field, order_direction=frame.order_direction if not random_order else "desc")
        return [photo for photo in photos if frame.orientation == "any" or photo.orientation == frame.orientation]
    if frame.source == "smart":
        if not frame.smart_query and not frame.smart_reference_asset_id:
            return []
        return await client.smart_search(frame.smart_query or "", query, size=size, reference_asset_id=frame.smart_reference_asset_id)
    if frame.source == "memories":
        anchor = date.fromisoformat(today) if today else date.today()
        memories: list[dict[str, Any]] = []
        for offset in range(-frame.memory_window_days, frame.memory_window_days + 1):
            memories.extend(await client.memories(for_date=(anchor + timedelta(days=offset)).isoformat(), size=size))
        assets = [asset for memory in memories for asset in memory.get("assets", [])]
        seen: set[str] = set()
        unique_assets: list[dict[str, Any]] = []
        for asset in assets:
            asset_id = asset.get("id")
            if asset_id and asset_id not in seen:
                seen.add(asset_id)
                unique_assets.append(asset)
        assets = unique_assets
        asset_ids = [asset["id"] for asset in assets if asset.get("id") and asset.get("type", "IMAGE") == "IMAGE"]
        if not asset_ids:
            return []
        # Memory records are intentionally lightweight and may not contain EXIF,
        # people, or tags. Re-query the IDs through metadata search so the frame's
        # ordinary filter and the same metadata contract apply to every source.
        memory_filter = _with_memory_ids(query, asset_ids[:1000])
        if memory_filter is None:
            return []
        photos = await client.search(memory_filter, size=size, order_field=frame.order_field, order_direction=frame.order_direction if frame.order_direction != "random" else "desc")
        return [photo for photo in photos if frame.orientation == "any" or photo.orientation == frame.orientation]
    random_order = frame.order_direction == "random"
    photos = await client.search(query, size=size, random=random_order, order_field=frame.order_field, order_direction=frame.order_direction if not random_order else "desc")
    return [photo for photo in photos if frame.orientation == "any" or photo.orientation == frame.orientation]
