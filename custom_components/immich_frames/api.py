from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import aiohttp
from PIL import Image, ImageOps

from .const import (
    CONF_ALBUM_ID, CONF_ALBUM_IDS, CONF_FALLBACK, CONF_MEMORY_WINDOW, CONF_MODE,
    CONF_ORIENTATION, CONF_PAIRS_ONLY, CONF_PAIR_WINDOW, CONF_SMART_QUERY, CONF_SOURCE,
    CONF_SCREEN_SHAPE, CONF_ORIGINAL_ASPECT_RATIO, DEFAULT_SCREEN_SHAPE, SCREEN_SIZES,
)
from .rendering import background_colour


class ImmichApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def selected_album_ids(options: dict[str, Any]) -> list[str]:
    """Read multiple selections, falling back to existing single-album frames."""
    values = options.get(CONF_ALBUM_IDS, [options.get(CONF_ALBUM_ID)])
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))


def _asset_items(value: Any, *, random: bool = False) -> list[dict[str, Any]]:
    """Random search returns an array; metadata/smart search return an envelope."""
    items = value
    if not random:
        assets = value.get("assets") if isinstance(value, dict) else None
        items = assets.get("items") if isinstance(assets, dict) else None
    if not isinstance(items, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in items
    ):
        raise ImmichApiError("Immich returned an invalid photo search response")
    return items


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


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    image: bytes
    generation: int
    photos: tuple[dict[str, Any], ...]
    layout: str
    created_at: datetime
    matching_assets: int
    connected: bool = True
    using_cache: bool = False
    status: str = "ready"

    @property
    def primary(self) -> dict[str, Any]:
        return self.photos[0]

    @property
    def secondary(self) -> dict[str, Any] | None:
        return self.photos[1] if len(self.photos) > 1 else None


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _photo(asset: dict[str, Any]) -> dict[str, Any]:
    exif = asset.get("exifInfo") or {}
    captured = _datetime(asset.get("localDateTime") or asset.get("fileCreatedAt"))
    width, height = asset.get("width"), asset.get("height")
    if width and height and width != height:
        orientation = "landscape" if width > height else "portrait"
    elif width and height:
        orientation = "square"
    else:
        orientation = "unknown"
    people = [person.get("name") or person.get("id", "") for person in asset.get("people") or []]
    tags = [tag.get("name") or tag.get("id", "") for tag in asset.get("tags") or []]
    return {
        "id": asset["id"], "filename": asset.get("originalFileName", asset["id"]),
        "width": width, "height": height, "orientation": orientation,
        "captured": captured.isoformat() if captured else None, "capture_dt": captured,
        "exif": exif, "people": people, "tags": tags,
        "favorite": bool(asset.get("isFavorite")), "rating": exif.get("rating"),
    }


class ImmichApi:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        for attempt in range(3):
            try:
                async with self.session.request(method, self.base_url + path, headers={"x-api-key": self.api_key}, timeout=aiohttp.ClientTimeout(total=20), **kwargs) as response:
                    if response.status >= 400:
                        detail = (await response.text())[:300]
                        if (response.status == 429 or response.status >= 500) and attempt < 2:
                            await asyncio.sleep(0.25 * (attempt + 1))
                            continue
                        raise ImmichApiError(f"Immich returned HTTP {response.status}: {detail}", response.status)
                    if "json" in response.headers.get("content-type", ""):
                        return await response.json()
                    return await response.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise ImmichApiError(str(exc)) from exc
        raise ImmichApiError("Immich request failed after retries")

    async def version(self) -> str:
        value = await self._request("GET", "/api/server/version")
        if isinstance(value, dict):
            if all(type(value.get(key)) is int for key in ("major", "minor", "patch")):
                return ".".join(str(value[key]) for key in ("major", "minor", "patch"))
            value = value.get("version")
        if isinstance(value, str) and re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+].+)?", value):
            return value.lstrip("v")
        raise ImmichApiError("Immich returned an invalid server version response")

    async def validate_connection(self) -> None:
        version = await self.version()
        major, minor = (int(part) for part in version.split(".")[:2])
        if (major, minor) < (3, 2):
            raise ImmichApiError("Immich 3.2 or later is required")
        # The version endpoint is public. Search verifies the key and asset.read.
        await self.search({"type": {"eq": "IMAGE"}, "trashedAt": {"eq": None},
                           "visibility": {"eq": "timeline"}}, size=1)

    async def search(self, filter_value: dict[str, Any], size: int = 200, random: bool = False) -> list[dict[str, Any]]:
        endpoint = "/api/search/random" if random else "/api/search/metadata"
        body = {"filter": filter_value, "size": min(size, 1000), "withExif": True, "withPeople": True, "withStacked": False}
        if not random:
            body["orderBy"] = {"field": "fileCreatedAt", "direction": "desc"}
        result = await self._request("POST", endpoint, json=body)
        return [_photo(asset) for asset in _asset_items(result, random=random)]

    async def albums(self) -> list[dict[str, Any]]:
        """List albums accessible to this account, including shared albums."""
        result = await self._request("GET", "/api/albums")
        if not isinstance(result, list) or any(
            not isinstance(album, dict)
            or not isinstance(album.get("id"), str) or not album["id"]
            or not isinstance(album.get("albumName"), str)
            for album in result
        ):
            raise ImmichApiError("Immich returned an invalid album list")
        return result

    async def smart_search(self, query: str, filter_value: dict[str, Any], size: int = 200) -> list[dict[str, Any]]:
        result = await self._request("POST", "/api/search/smart", json={"query": query, "filter": filter_value, "size": min(size, 1000), "withExif": True, "withPeople": True})
        return [_photo(asset) for asset in _asset_items(result)]

    async def memories(self, for_date: str, size: int = 100) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/memories", params={"for": for_date, "size": min(size, 1000)})
        items = result if isinstance(result, list) else result.get("memories") if isinstance(result, dict) else None
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ImmichApiError("Immich returned an invalid memories response")
        return items

    async def thumbnail(self, asset_id: str) -> bytes:
        return await self._request("GET", f"/api/assets/{asset_id}/thumbnail", params={"size": "preview"})

    async def snapshot(self, options: dict[str, Any], generation: int, recent_ids: set[str]) -> FrameSnapshot:
        source = options.get(CONF_SOURCE, "all")
        filter_value = {} if source in ("all", "album") else dict(options.get("filter") or {})
        filter_value.update({"type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"eq": "timeline"}})
        if source == "album":
            album_ids = selected_album_ids(options)
            if not album_ids:
                raise ImmichApiError("Choose at least one album")
            candidates = await self.search({**filter_value, "albumIds": {"any": album_ids}}, random=True)
        elif source == "smart":
            candidates = await self.smart_search(options.get(CONF_SMART_QUERY, ""), filter_value)
        elif source == "memories":
            anchor = date.today()
            assets: list[dict[str, Any]] = []
            for offset in range(-int(options.get(CONF_MEMORY_WINDOW, 2)), int(options.get(CONF_MEMORY_WINDOW, 2)) + 1):
                assets.extend(await self.memories((anchor + timedelta(days=offset)).isoformat()))
            ids = list(dict.fromkeys(asset.get("id") for memory in assets for asset in memory.get("assets", []) if asset.get("id")))
            memory_filter = _with_memory_ids(filter_value, ids[:1000])
            candidates = await self.search(memory_filter) if memory_filter else []
            if not candidates and options.get(CONF_FALLBACK):
                candidates = await self.search(filter_value, random=True)
        else:
            candidates = await self.search(filter_value, random=True)
        orientation = options.get(CONF_ORIENTATION, "any")
        candidates = [item for item in candidates if orientation == "any" or item["orientation"] == orientation]
        if not candidates:
            raise ImmichApiError("No photos match this frame")
        primary = next((item for item in candidates if item["id"] not in recent_ids), candidates[0])
        photos = [primary]
        if options.get(CONF_MODE) == "pairs":
            companion = None
            # Prefer unseen photos, but search the whole candidate batch for a pair.
            for candidate in sorted(candidates, key=lambda item: item["id"] in recent_ids):
                companion = self._companion(candidate, [item for item in candidates if item["id"] != candidate["id"]], int(options.get(CONF_PAIR_WINDOW, 0)))
                if companion:
                    photos = [candidate]
                    break
            if companion:
                photos.append(companion)
            elif options.get(CONF_PAIRS_ONLY):
                raise ImmichApiError("No matching pair is available")
        image_data = await asyncio.gather(*(self.thumbnail(item["id"]) for item in photos))
        try:
            output, layout = await asyncio.get_running_loop().run_in_executor(
                None, self._render, photos, image_data,
                options.get(CONF_SCREEN_SHAPE, DEFAULT_SCREEN_SHAPE),
                options.get(CONF_ORIGINAL_ASPECT_RATIO, False),
            )
        except (OSError, ValueError) as exc:
            raise ImmichApiError("Could not decode the photo preview from Immich") from exc
        return FrameSnapshot(output, generation, tuple(photos), layout, datetime.now(timezone.utc), len(candidates))

    @staticmethod
    def _companion(primary: dict[str, Any], candidates: list[dict[str, Any]], window_days: int) -> dict[str, Any] | None:
        capture = primary.get("capture_dt")
        if not capture or primary.get("orientation") != "portrait":
            return None
        eligible = [item for item in candidates if item.get("orientation") == "portrait" and item.get("capture_dt") and abs((item["capture_dt"].date() - capture.date()).days) <= window_days]
        return min(eligible, key=lambda item: (abs((item["capture_dt"] - capture).total_seconds()), item["id"])) if eligible else None

    @staticmethod
    def _render(photos: list[dict[str, Any]], payloads: list[bytes], screen_shape: str = DEFAULT_SCREEN_SHAPE, original_aspect_ratio: bool = False) -> tuple[bytes, str]:
        canvas_size = SCREEN_SIZES.get(screen_shape, SCREEN_SIZES[DEFAULT_SCREEN_SHAPE])
        images: list[Image.Image] = []
        for payload in payloads:
            image = ImageOps.exif_transpose(Image.open(BytesIO(payload))).convert("RGB")
            images.append(image)
        if len(images) == 1:
            if original_aspect_ratio:
                # Keep the photo proportions without padding, within the output limits.
                canvas = images[0]
                canvas.thumbnail(canvas_size, Image.Resampling.LANCZOS)
            else:
                images[0].thumbnail(canvas_size, Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", canvas_size, background_colour(images[0]))
                canvas.paste(images[0], ((canvas.width - images[0].width) // 2, (canvas.height - images[0].height) // 2))
            layout = "single"
        else:
            # Fill the selected frame with one black pixel between the two tiles.
            canvas = Image.new("RGB", canvas_size, "black")
            divider = canvas.width // 2
            tiles = ((0, divider), (divider + 1, canvas.width - divider - 1))
            for image, (left, width) in zip(images[:2], tiles):
                cropped = ImageOps.fit(image, (width, canvas.height), Image.Resampling.LANCZOS)
                canvas.paste(cropped, (left, 0))
            layout = "side_by_side"
        output = BytesIO()
        # Avoid chroma bleeding across the narrow divider in paired output.
        canvas.save(output, "JPEG", quality=95 if len(images) == 2 else 85,
                    subsampling=0 if len(images) == 2 else -1, optimize=True)
        return output.getvalue(), layout


def parse_filter(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Filter must be a JSON object")
    return parsed
