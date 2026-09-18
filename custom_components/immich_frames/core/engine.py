from __future__ import annotations
import asyncio
import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any
from .settings import *  # noqa: F403
from .models import FrameSnapshot
from .rendering import render
from .filtering import safe_filter
from .errors import ImmichApiError, NoMatchingPhotos

def selected_album_ids(options: dict[str, Any]) -> list[str]:
    """Read multiple selections, falling back to existing single-album frames."""
    values = options.get(CONF_ALBUM_IDS, [options.get(CONF_ALBUM_ID)])
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))


def _with_time_range(query: dict[str, Any], time_range: str, now: datetime) -> dict[str, Any]:
    """Intersect the capture-date filter with a rolling calendar month/year range."""
    months = TIME_RANGE_MONTHS.get(time_range, 0)
    if not months:
        return query
    year, month_index = divmod(now.year * 12 + now.month - 1 - months, 12)
    month = month_index + 1
    cutoff = now.replace(year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1]))
    condition = dict(query.get("takenAt") or {})
    # Retain stricter bounds and other operators from legacy custom filters.
    for operator, boundary, strictest in (("gte", cutoff, max), ("lte", now, min)):
        existing = _datetime(condition.get(operator))
        if existing is not None:
            if existing.tzinfo is None:
                existing = existing.replace(tzinfo=timezone.utc)
            boundary = strictest(existing, boundary)
        condition[operator] = boundary.isoformat()
    return {**query, "takenAt": condition}



def _with_memory_ids(query: dict[str, Any], asset_ids: list[str]) -> dict[str, Any] | None:
    """Intersect a filter with memory IDs using Immich's scalar ID operators."""
    result = dict(query)
    branches = []
    # Distribute existing alternatives so memory IDs never replace user rules.
    for branch in result.pop("or", [{}]):
        condition = branch.get("id", {})
        for asset_id in asset_ids:
            if condition.get("eq", asset_id) == asset_id and condition.get("ne") != asset_id:
                branches.append({**branch, "id": {"eq": asset_id}})
    return {**result, "or": branches} if branches else None



def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None



async def select_candidates(client, options, *, now=None, today=None, size=200):
    options = FrameSettings.from_options(options).options()
    source = options.get(CONF_SOURCE, "all")
    filter_value = safe_filter(dict(options.get("filter") or {}))
    filter_value = _with_time_range(
        filter_value, options.get(CONF_TIME_RANGE, DEFAULT_TIME_RANGE), now or datetime.now(timezone.utc),
    )
    search_options = {"size": size, "order_field": options["order_field"], "order_direction": options["order_direction"] if options["order_direction"] != "random" else "desc"}
    random_order = options["order_direction"] == "random"
    if source == "album":
        album_ids = selected_album_ids(options)
        if not album_ids:
            raise ImmichApiError("Choose at least one album")
        candidates = await client.search({**filter_value, "albumIds": {"any": album_ids}}, random=random_order, **search_options)
    elif source == "smart":
        candidates = await client.smart_search(options.get(CONF_SMART_QUERY, ""), filter_value, size=size, reference_asset_id=options.get("smart_reference_asset_id"))
    elif source == "memories":
        anchor = today or date.today()
        assets: list[dict[str, Any]] = []
        for offset in range(-int(options.get(CONF_MEMORY_WINDOW, 2)), int(options.get(CONF_MEMORY_WINDOW, 2)) + 1):
            assets.extend(await client.memories((anchor + timedelta(days=offset)).isoformat()))
        ids = list(dict.fromkeys(asset.get("id") for memory in assets for asset in memory.get("assets", []) if asset.get("id")))
        memory_filter = _with_memory_ids(filter_value, ids[:1000])
        candidates = await client.search(memory_filter, **search_options) if memory_filter else []
        if not candidates and options.get(CONF_FALLBACK):
            candidates = await client.search(filter_value, random=random_order, **search_options)
    else:
        candidates = await client.search(filter_value, random=random_order, **search_options)
    orientation = options.get(CONF_ORIENTATION, "any")
    candidates = [item for item in candidates if orientation == "any" or item["orientation"] == orientation]
    return candidates

async def snapshot(client, options: dict[str, Any], generation: int, recent_ids: set[str]) -> FrameSnapshot:
    options = FrameSettings.from_options(options).options()
    candidates = await select_candidates(client, options)
    if options.get(CONF_MODE) == "pairs_only":
        # This setting controls portraits; landscapes and squares still
        # follow the independent orientation filter.
        candidates = [item for item in candidates if item["orientation"] != "portrait" or companion(
            item, [other for other in candidates if other["id"] != item["id"]],
            int(options.get(CONF_PAIR_WINDOW, DEFAULT_PAIR_WINDOW)),
        )]
    if not candidates:
        raise NoMatchingPhotos("No photos match this frame")
    primary = next((item for item in candidates if item["id"] not in recent_ids), candidates[0])
    photos = [primary]
    if options.get(CONF_MODE) in ("pairs", "pairs_only"):
        partner = companion(primary, [item for item in candidates if item["id"] != primary["id"]], int(options.get(CONF_PAIR_WINDOW, DEFAULT_PAIR_WINDOW)))
        if partner:
            photos.append(partner)
    try:
        shape = options.get(CONF_SCREEN_SHAPE, DEFAULT_SCREEN_SHAPE)
        fit = slide_photo_fit(options, photos)
        size = SCREEN_SIZES.get(shape, SCREEN_SIZES[DEFAULT_SCREEN_SHAPE])
        sizes = [size] if len(photos) == 1 else [(size[0] // 2, size[1]), (size[0] - size[0] // 2 - 1, size[1])]
        image_data = await asyncio.gather(*(
            client.crop_image(item, tile_size) if fit == PHOTO_FIT_CROP else client.thumbnail(item["id"])
            for item, tile_size in zip(photos, sizes)
        ))
        output, layout = await asyncio.get_running_loop().run_in_executor(
            None, render, photos, image_data,
            shape, fit,
        )
    except (OSError, ValueError) as exc:
        raise ImmichApiError("Could not decode the photo preview from Immich") from exc
    return FrameSnapshot(output, generation, tuple(photos), layout, datetime.now(timezone.utc), len(candidates))

def companion(primary: dict[str, Any], candidates: list[dict[str, Any]], window_days: int, orientation: str = "portrait") -> dict[str, Any] | None:
    capture = primary.get("capture_dt")
    if not capture or primary.get("orientation") != orientation:
        return None
    eligible = [item for item in candidates if item["id"] != primary["id"] and (not primary.get("checksum") or item.get("checksum") != primary["checksum"]) and item.get("orientation") == orientation and item.get("capture_dt") and abs((item["capture_dt"].date() - capture.date()).days) <= window_days]
    return min(eligible, key=lambda item: (abs((item["capture_dt"] - capture).total_seconds()), item["id"])) if eligible else None

