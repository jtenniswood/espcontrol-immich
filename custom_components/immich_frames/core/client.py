from __future__ import annotations
import asyncio
import logging
import re
from typing import Any
import aiohttp
from PIL import Image
from .errors import ImmichApiError
from .rendering import image_size
from .engine import _datetime
LOGGER = logging.getLogger(__name__)

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
    people = [name.strip() for person in asset.get("people") or []
              if isinstance(name := person.get("name"), str) and name.strip()]
    tags = [tag.get("name") or tag.get("id", "") for tag in asset.get("tags") or []]
    return {
        "id": asset["id"], "filename": asset.get("originalFileName", asset["id"]),
        "width": width, "height": height, "orientation": orientation,
        "captured": captured.isoformat() if captured else None, "capture_dt": captured,
        "exif": exif, "people": people, "tags": tags,
        "favorite": asset.get("isFavorite"), "rating": exif.get("rating"),
    }


class ImmichApi:
    def __init__(self, base_url: str, api_key: str, session=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session
        self._owned_session = session is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self) -> None:
        if self._owned_session and self.session and not getattr(self.session, "closed", False):
            await self.session.close()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.session is None or getattr(self.session, "closed", False):
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

    async def search(self, filter_value: dict[str, Any], size: int = 200, random: bool = False, order_field: str = "fileCreatedAt", order_direction: str = "desc") -> list[dict[str, Any]]:
        endpoint = "/api/search/random" if random else "/api/search/metadata"
        body = {"filter": filter_value, "size": min(size, 1000), "withExif": True, "withPeople": True, "withStacked": False}
        if not random:
            body["orderBy"] = {"field": order_field, "direction": order_direction}
        photos = []
        seen_cursors = set()
        while len(photos) < size:
            result = await self._request("POST", endpoint, json=dict(body))
            items = _asset_items(result, random=random)
            photos.extend(_photo(asset) for asset in items)
            cursor = None if random else result["assets"].get("nextCursor")
            if not items or not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            body["cursor"] = cursor
        return photos[:size]

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

    async def smart_search(self, query: str, filter_value: dict[str, Any], size: int = 200, reference_asset_id: str | None = None) -> list[dict[str, Any]]:
        body = {"query": query, "filter": filter_value, "size": min(size, 1000), "withExif": True, "withPeople": True}
        if reference_asset_id:
            body["queryAssetId"] = reference_asset_id
        result = await self._request("POST", "/api/search/smart", json=body)
        return [_photo(asset) for asset in _asset_items(result)]

    async def memories(self, for_date: str | None = None, size: int = 100, is_saved: bool | None = None) -> list[dict[str, Any]]:
        params = {"size": min(size, 1000)}
        if for_date:
            params["for"] = for_date
        if is_saved is not None:
            params["isSaved"] = str(is_saved).lower()
        result = await self._request("GET", "/api/memories", params=params)
        items = result if isinstance(result, list) else result.get("memories") if isinstance(result, dict) else None
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ImmichApiError("Immich returned an invalid memories response")
        return items

    async def thumbnail(self, asset_id: str, size: str = "preview") -> bytes:
        return await self._request("GET", f"/api/assets/{asset_id}/thumbnail", params={"size": size})

    async def crop_image(self, photo: dict[str, Any], size: tuple[int, int]) -> bytes:
        """Upgrade an undersized preview without making full-size access mandatory."""
        preview = await self.thumbnail(photo["id"])
        loop = asyncio.get_running_loop()
        width, height = await loop.run_in_executor(None, image_size, preview)
        resolution = min(width / size[0], height / size[1])
        if resolution >= 1:
            return preview
        # Avoid downloading an original that is itself no larger than the preview.
        # Compare sorted dimensions because metadata may precede EXIF rotation.
        original = (photo.get("width"), photo.get("height"))
        if all(isinstance(value, (int, float)) and value > 0 for value in original):
            if all(a <= b for a, b in zip(sorted(original), sorted((width, height)))):
                return preview
        try:
            # Immich serves the original, or a full-resolution converted image
            # for formats such as HEIC when full-size generation is enabled.
            fullsize = await self._request(
                "GET", f"/api/assets/{photo['id']}/thumbnail", params={"size": "fullsize"},
            )
            full_width, full_height = await loop.run_in_executor(None, image_size, fullsize)
            if min(full_width / size[0], full_height / size[1]) > resolution:
                return fullsize
        except (ImmichApiError, OSError, ValueError, Image.DecompressionBombError):
            LOGGER.debug("Full-size photo unavailable; using the preview")
        return preview


    async def capabilities(self) -> dict[str, Any]:
        version = await self.version()
        parts = version.lstrip("v").split(".")
        major, minor = (int(parts[0]), int(parts[1])) if len(parts) > 1 and parts[0].isdigit() and parts[1].isdigit() else (0, 0)
        return {"version": version, "structured_search": (major, minor) >= (3, 2), "memories": (major, minor) >= (3, 2), "smart_search": True, "ocr": (major, minor) >= (3, 2)}


    async def statistics(self, filter: dict[str, Any]) -> int:
        result = await self._request("POST", "/api/search/statistics", json={"filter": filter})
        return int(result.get("total", 0))


    async def people(self, size: int = 500) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/people", params={"size": min(size, 1000), "withHidden": False})
        return result if isinstance(result, list) else result.get("people", [])

    async def tags(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/tags")
        return result if isinstance(result, list) else result.get("tags", [])

