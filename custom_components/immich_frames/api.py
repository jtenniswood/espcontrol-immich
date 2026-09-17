from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import aiohttp
from PIL import Image, ImageOps


class ImmichApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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
        if self.session is None:
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
        return value if isinstance(value, str) else value.get("version", "unknown")

    async def search(self, filter_value: dict[str, Any], size: int = 200, random: bool = False) -> list[dict[str, Any]]:
        endpoint = "/api/search/random" if random else "/api/search/metadata"
        body = {"filter": filter_value, "size": min(size, 1000), "withExif": True, "withPeople": True, "withStacked": False}
        if not random:
            body["orderBy"] = {"field": "fileCreatedAt", "direction": "desc"}
        result = await self._request("POST", endpoint, json=body)
        return [_photo(asset) for asset in result.get("assets", {}).get("items", [])]

    async def smart_search(self, query: str, filter_value: dict[str, Any], size: int = 200) -> list[dict[str, Any]]:
        result = await self._request("POST", "/api/search/smart", json={"query": query, "filter": filter_value, "size": min(size, 1000), "withExif": True, "withPeople": True})
        return [_photo(asset) for asset in result.get("assets", {}).get("items", [])]

    async def memories(self, for_date: str, size: int = 100) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/memories", params={"for": for_date, "size": min(size, 1000)})
        return result if isinstance(result, list) else result.get("memories", [])

    async def thumbnail(self, asset_id: str) -> bytes:
        return await self._request("GET", f"/api/assets/{asset_id}/thumbnail", params={"size": "preview"})

    async def snapshot(self, options: dict[str, Any], generation: int, recent_ids: set[str]) -> FrameSnapshot:
        filter_value = dict(options.get(CONF_FILTER) or {})
        filter_value.update({"type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"eq": "timeline"}})
        source = options.get(CONF_SOURCE, "filter")
        if source == "smart":
            candidates = await self.smart_search(options.get(CONF_SMART_QUERY, ""), filter_value)
        elif source == "memories":
            anchor = date.today()
            assets: list[dict[str, Any]] = []
            for offset in range(-int(options.get(CONF_MEMORY_WINDOW, 2)), int(options.get(CONF_MEMORY_WINDOW, 2)) + 1):
                assets.extend(await self.memories((anchor + timedelta(days=offset)).isoformat()))
            ids = list(dict.fromkeys(asset.get("id") for memory in assets for asset in memory.get("assets", []) if asset.get("id")))
            candidates = await self.search({**filter_value, "id": {"in": ids[:1000]}}) if ids else []
            if not candidates and options.get("fallback_to_all"):
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
            companion = self._companion(primary, [item for item in candidates if item["id"] != primary["id"]], int(options.get(CONF_PAIR_WINDOW, 0)))
            if companion:
                photos.append(companion)
            elif options.get(CONF_PAIRS_ONLY):
                raise ImmichApiError("No matching pair is available")
        image_data = await asyncio.gather(*(self.thumbnail(item["id"]) for item in photos))
        output, layout = await asyncio.get_running_loop().run_in_executor(None, self._render, photos, image_data)
        return FrameSnapshot(output, generation, tuple(photos), layout, datetime.now(timezone.utc), len(candidates))

    @staticmethod
    def _companion(primary: dict[str, Any], candidates: list[dict[str, Any]], window_days: int) -> dict[str, Any] | None:
        capture = primary.get("capture_dt")
        if not capture or primary.get("orientation") != "portrait":
            return None
        eligible = [item for item in candidates if item.get("orientation") == "portrait" and item.get("capture_dt") and abs((item["capture_dt"].date() - capture.date()).days) <= window_days]
        return min(eligible, key=lambda item: (abs((item["capture_dt"] - capture).total_seconds()), item["id"])) if eligible else None

    @staticmethod
    def _render(photos: list[dict[str, Any]], payloads: list[bytes]) -> tuple[bytes, str]:
        canvas_size = (1920, 1080)
        images: list[Image.Image] = []
        for payload in payloads:
            image = ImageOps.exif_transpose(Image.open(BytesIO(payload))).convert("RGB")
            images.append(image)
        if len(images) == 1:
            canvas = Image.new("RGB", canvas_size, "black")
            images[0].thumbnail(canvas_size, Image.Resampling.LANCZOS)
            canvas.paste(images[0], ((canvas.width - images[0].width) // 2, (canvas.height - images[0].height) // 2))
            layout = "single"
        else:
            canvas = Image.new("RGB", canvas_size, "black")
            width = canvas.width // 2
            for index, image in enumerate(images[:2]):
                image.thumbnail((width, canvas.height), Image.Resampling.LANCZOS)
                canvas.paste(image, (index * width + (width - image.width) // 2, (canvas.height - image.height) // 2))
            layout = "side_by_side"
        output = BytesIO()
        canvas.save(output, "JPEG", quality=85, optimize=True)
        return output.getvalue(), layout


def parse_filter(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Filter must be a JSON object")
    return parsed
