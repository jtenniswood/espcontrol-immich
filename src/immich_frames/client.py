"""Async Immich client used by Home Assistant and the optional renderer.

The package owns all HTTP communication with Immich. Host applications supply
an aiohttp session so they control SSL verification, connection pooling, and
shutdown lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import re
from io import BytesIO
from typing import Any, Self

import aiohttp
from PIL import Image

LOGGER = logging.getLogger(__name__)


class ImmichClientError(RuntimeError):
    """An Immich request or response failed."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _datetime(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _asset_items(value: Any, *, random: bool = False) -> list[dict[str, Any]]:
    """Normalize Immich random and metadata search response envelopes."""
    items = value
    if not random:
        assets = value.get("assets") if isinstance(value, dict) else None
        items = assets.get("items") if isinstance(assets, dict) else None
    if not isinstance(items, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("id"), str)
        for item in items
    ):
        raise ImmichClientError("Immich returned an invalid photo search response")
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
    people = [
        name.strip()
        for person in asset.get("people") or []
        if isinstance(name := person.get("name"), str) and name.strip()
    ]
    tags = [tag.get("name") or tag.get("id", "") for tag in asset.get("tags") or []]
    return {
        "id": asset["id"],
        "filename": asset.get("originalFileName", asset["id"]),
        "width": width,
        "height": height,
        "orientation": orientation,
        "captured": captured.isoformat() if captured else None,
        "capture_dt": captured,
        "exif": exif,
        "people": people,
        "tags": tags,
        "favorite": asset.get("isFavorite"),
        "rating": exif.get("rating"),
        "checksum": asset.get("checksum"),
    }


def _image_size(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.getexif().get(274) in (5, 6, 7, 8):
            return image.size[1], image.size[0]
        return image.size


class ImmichClient:
    """Async, session-injectable client for the Immich API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self.session and not getattr(self.session, "closed", False):
            await self.session.close()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.session is None or getattr(self.session, "closed", False):
            self.session = aiohttp.ClientSession()
            self._owns_session = True
        for attempt in range(3):
            try:
                async with self.session.request(
                    method,
                    self.base_url + path,
                    headers={"x-api-key": self.api_key},
                    timeout=aiohttp.ClientTimeout(total=20),
                    **kwargs,
                ) as response:
                    if response.status >= 400:
                        detail = (await response.text())[:300]
                        if (
                            response.status == 429 or response.status >= 500
                        ) and attempt < 2:
                            await asyncio.sleep(0.25 * (attempt + 1))
                            continue
                        raise ImmichClientError(
                            f"Immich returned HTTP {response.status}: {detail}",
                            response.status,
                        )
                    if "json" in response.headers.get("content-type", ""):
                        return await response.json()
                    return await response.read()
            except (aiohttp.ClientError, TimeoutError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise ImmichClientError(str(exc)) from exc
        raise ImmichClientError("Immich request failed after retries")

    async def version(self) -> str:
        value = await self._request("GET", "/api/server/version")
        if isinstance(value, dict):
            if all(type(value.get(key)) is int for key in ("major", "minor", "patch")):
                return ".".join(str(value[key]) for key in ("major", "minor", "patch"))
            value = value.get("version")
        if isinstance(value, str) and re.fullmatch(
            r"v?\d+\.\d+\.\d+(?:[-+].+)?", value
        ):
            return value.lstrip("v")
        raise ImmichClientError("Immich returned an invalid server version response")

    async def validate_connection(self) -> None:
        version = await self.version()
        major, minor = (int(part) for part in version.split(".")[:2])
        if (major, minor) < (3, 2):
            raise ImmichClientError("Immich 3.2 or later is required")
        await self.search(
            {
                "type": {"eq": "IMAGE"},
                "trashedAt": {"eq": None},
                "visibility": {"eq": "timeline"},
            },
            size=1,
        )

    async def search(
        self,
        filter_value: dict[str, Any],
        size: int = 200,
        random: bool = False,
        order_field: str = "fileCreatedAt",
        order_direction: str = "desc",
    ) -> list[dict[str, Any]]:
        endpoint = "/api/search/random" if random else "/api/search/metadata"
        body: dict[str, Any] = {
            "filter": filter_value,
            "size": min(size, 1000),
            "withExif": True,
            "withPeople": True,
            "withStacked": False,
        }
        if not random:
            body["orderBy"] = {"field": order_field, "direction": order_direction}
        photos: list[dict[str, Any]] = []
        seen_cursors: set[str] = set()
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
        result = await self._request("GET", "/api/albums")
        if not isinstance(result, list) or any(
            not isinstance(album, dict)
            or not isinstance(album.get("id"), str)
            or not album["id"]
            or not isinstance(album.get("albumName"), str)
            for album in result
        ):
            raise ImmichClientError("Immich returned an invalid album list")
        return result

    async def smart_search(
        self,
        query: str,
        filter_value: dict[str, Any],
        size: int = 200,
        reference_asset_id: str | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "query": query,
            "filter": filter_value,
            "size": min(size, 1000),
            "withExif": True,
            "withPeople": True,
        }
        if reference_asset_id:
            body["queryAssetId"] = reference_asset_id
        result = await self._request("POST", "/api/search/smart", json=body)
        return [_photo(asset) for asset in _asset_items(result)]

    async def memories(
        self, for_date: str | None = None, size: int = 100, is_saved: bool | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"size": min(size, 1000)}
        if for_date:
            params["for"] = for_date
        if is_saved is not None:
            params["isSaved"] = str(is_saved).lower()
        result = await self._request("GET", "/api/memories", params=params)
        items = (
            result
            if isinstance(result, list)
            else result.get("memories")
            if isinstance(result, dict)
            else None
        )
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ImmichClientError("Immich returned an invalid memories response")
        return items

    async def thumbnail(self, asset_id: str, size: str = "preview") -> bytes:
        return await self._request(
            "GET", f"/api/assets/{asset_id}/thumbnail", params={"size": size}
        )

    async def crop_image(self, photo: dict[str, Any], size: tuple[int, int]) -> bytes:
        """Use a full-size source only when the preview cannot fill the target."""
        preview = await self.thumbnail(photo["id"])
        loop = asyncio.get_running_loop()
        width, height = await loop.run_in_executor(None, _image_size, preview)
        resolution = min(width / size[0], height / size[1])
        if resolution >= 1:
            return preview
        original = (photo.get("width"), photo.get("height"))
        if all(isinstance(value, (int, float)) and value > 0 for value in original) and all(
            a <= b for a, b in zip(sorted(original), sorted((width, height)))
        ):
            return preview
        try:
            fullsize = await self.thumbnail(photo["id"], "fullsize")
            full_width, full_height = await loop.run_in_executor(
                None, _image_size, fullsize
            )
            if min(full_width / size[0], full_height / size[1]) > resolution:
                return fullsize
        except (ImmichClientError, OSError, ValueError, Image.DecompressionBombError):
            LOGGER.debug("Full-size photo unavailable; using the preview")
        return preview

    async def capabilities(self) -> dict[str, Any]:
        """Return server capabilities used by the optional web application."""
        version = await self.version()
        parts = version.lstrip("v").split(".")
        major, minor = (
            (int(parts[0]), int(parts[1]))
            if len(parts) > 1 and parts[0].isdigit() and parts[1].isdigit()
            else (0, 0)
        )
        return {
            "version": version,
            "structured_search": (major, minor) >= (3, 2),
            "memories": (major, minor) >= (3, 2),
            "smart_search": True,
            "ocr": (major, minor) >= (3, 2),
        }

    async def statistics(self, filter_value: dict[str, Any]) -> int:
        result = await self._request(
            "POST", "/api/search/statistics", json={"filter": filter_value}
        )
        return int(result.get("total", 0))

    async def people(self, size: int = 500) -> list[dict[str, Any]]:
        result = await self._request(
            "GET", "/api/people", params={"size": min(size, 1000), "withHidden": False}
        )
        return result if isinstance(result, list) else result.get("people", [])

    async def tags(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/tags")
        return result if isinstance(result, list) else result.get("tags", [])
