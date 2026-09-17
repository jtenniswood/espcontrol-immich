from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .models import Photo


class ImmichError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ImmichClient:
    def __init__(self, base_url: str, api_key: str, session: aiohttp.ClientSession | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session = session
        self._owned_session = session is None
        self._headers = {"x-api-key": self.api_key}

    async def __aenter__(self) -> "ImmichClient":
        if self._session is None:
            self._session = aiohttp.ClientSession(headers={"x-api-key": self.api_key})
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owned_session and self._session:
            await self._session.close()

    async def close(self) -> None:
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._session is None:
            self._session = aiohttp.ClientSession(headers={"x-api-key": self.api_key})
        for attempt in range(3):
            try:
                async with self._session.request(method, self.base_url + path, headers=self._headers, timeout=aiohttp.ClientTimeout(total=15), **kwargs) as response:
                    if response.status >= 400:
                        detail = (await response.text())[:500]
                        retryable = response.status == 429 or response.status >= 500
                        if retryable and attempt < 2:
                            await asyncio.sleep(0.25 * (attempt + 1))
                            continue
                        raise ImmichError(f"Immich {response.status}: {detail}", response.status)
                    return await response.json() if "json" in response.headers.get("content-type", "") else await response.read()
            except aiohttp.ClientError as exc:
                if attempt < 2:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise ImmichError(str(exc)) from exc
        raise ImmichError("Immich request failed after retries")

    async def version(self) -> str:
        value = await self._request("GET", "/api/server/version")
        if isinstance(value, dict) and all(type(value.get(key)) is int for key in ("major", "minor", "patch")):
            return ".".join(str(value[key]) for key in ("major", "minor", "patch"))
        if not isinstance(value, (str, dict)):
            raise ImmichError("Immich returned an invalid server version response")
        return value if isinstance(value, str) else value.get("version", "unknown")

    async def capabilities(self) -> dict[str, Any]:
        version = await self.version()
        parts = version.lstrip("v").split(".")
        major, minor = (int(parts[0]), int(parts[1])) if len(parts) > 1 and parts[0].isdigit() and parts[1].isdigit() else (0, 0)
        return {"version": version, "structured_search": (major, minor) >= (3, 2), "memories": (major, minor) >= (3, 2), "smart_search": True, "ocr": (major, minor) >= (3, 2)}

    async def search(self, filter: dict[str, Any], size: int = 100, random: bool = False, order_field: str = "fileCreatedAt", order_direction: str = "desc") -> list[Photo]:
        endpoint = "/api/search/random" if random else "/api/search/metadata"
        body: dict[str, Any] = {"filter": filter, "size": min(size, 1000), "withExif": True, "withPeople": True, "withStacked": False}
        if not random:
            body["orderBy"] = {"field": order_field, "direction": order_direction}
        photos: list[Photo] = []
        cursor: str | None = None
        while len(photos) < size:
            if cursor:
                body["cursor"] = cursor
            result = await self._request("POST", endpoint, json=body)
            if random:
                if not isinstance(result, list):
                    raise ImmichError("Immich returned an invalid random search response")
                return [Photo.from_api(item) for item in result[:size]]
            photos.extend(Photo.from_api(item) for item in result.get("assets", {}).get("items", []))
            cursor = result.get("assets", {}).get("nextCursor")
            if not cursor or not result.get("assets", {}).get("items"):
                break
        return photos[:size]

    async def statistics(self, filter: dict[str, Any]) -> int:
        result = await self._request("POST", "/api/search/statistics", json={"filter": filter})
        return int(result.get("total", 0))

    async def smart_search(self, query: str, filter: dict[str, Any], size: int = 100, reference_asset_id: str | None = None) -> list[Photo]:
        body: dict[str, Any] = {"query": query, "filter": filter, "size": min(size, 1000), "withExif": True}
        if reference_asset_id:
            body["queryAssetId"] = reference_asset_id
        result = await self._request("POST", "/api/search/smart", json=body)
        return [Photo.from_api(item) for item in result.get("assets", {}).get("items", [])]

    async def albums(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/albums")
        return result if isinstance(result, list) else result.get("albums", [])

    async def people(self, size: int = 500) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/people", params={"size": min(size, 1000), "withHidden": False})
        return result if isinstance(result, list) else result.get("people", [])

    async def tags(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/tags")
        return result if isinstance(result, list) else result.get("tags", [])

    async def memories(self, for_date: str | None = None, is_saved: bool | None = None, size: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"size": min(size, 1000)}
        if for_date:
            params["for"] = for_date
        if is_saved is not None:
            params["isSaved"] = str(is_saved).lower()
        result = await self._request("GET", "/api/memories", params=params)
        return result if isinstance(result, list) else result.get("memories", [])

    async def thumbnail(self, asset_id: str, size: str = "preview") -> bytes:
        return await self._request("GET", f"/api/assets/{asset_id}/thumbnail", params={"size": size})
