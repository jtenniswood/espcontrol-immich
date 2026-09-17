from __future__ import annotations

from typing import Any

import aiohttp

from .models import Photo


class ImmichError(RuntimeError):
    pass


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

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._session is None:
            self._session = aiohttp.ClientSession(headers={"x-api-key": self.api_key})
        try:
            async with self._session.request(method, self.base_url + path, headers=self._headers, timeout=aiohttp.ClientTimeout(total=15), **kwargs) as response:
                if response.status >= 400:
                    detail = (await response.text())[:500]
                    raise ImmichError(f"Immich {response.status}: {detail}")
                return await response.json() if "json" in response.headers.get("content-type", "") else await response.read()
        except aiohttp.ClientError as exc:
            raise ImmichError(str(exc)) from exc

    async def version(self) -> str:
        value = await self._request("GET", "/api/server/version")
        return value if isinstance(value, str) else value.get("version", "unknown")

    async def search(self, filter: dict[str, Any], size: int = 100, random: bool = False) -> list[Photo]:
        endpoint = "/api/search/random" if random else "/api/search/metadata"
        body: dict[str, Any] = {"filter": filter, "size": min(size, 1000), "withExif": True, "withPeople": True, "withStacked": False}
        photos: list[Photo] = []
        cursor: str | None = None
        while len(photos) < size:
            if cursor:
                body["cursor"] = cursor
            result = await self._request("POST", endpoint, json=body)
            photos.extend(Photo.from_api(item) for item in result.get("assets", {}).get("items", []))
            cursor = result.get("assets", {}).get("nextCursor")
            if not cursor or not result.get("assets", {}).get("items"):
                break
        return photos[:size]

    async def thumbnail(self, asset_id: str, size: str = "preview") -> bytes:
        return await self._request("GET", f"/api/assets/{asset_id}/thumbnail", params={"size": size})
