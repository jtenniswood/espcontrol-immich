"""Translate app settings and Photo objects at the shared engine boundary."""
from datetime import date
from custom_components.immich_frames.core.engine import select_candidates as select, _with_memory_ids  # noqa: F401
from custom_components.immich_frames.core.filtering import safe_filter  # noqa: F401
from .client import ImmichClient as ImmichApi
from .models import Photo


class ClientAdapter:
    def __init__(self, client):
        self.client = client

    async def search(self, *args, **kwargs):
        return [p.record() if isinstance(p, Photo) else p for p in await self.client.search(*args, **kwargs)]

    async def smart_search(self, *args, **kwargs):
        return [p.record() if isinstance(p, Photo) else p for p in await self.client.smart_search(*args, **kwargs)]

    async def memories(self, for_date, **kwargs):
        return await self.client.memories(for_date=for_date, **kwargs)

    async def thumbnail(self, asset_id):
        return await self.client.thumbnail(asset_id)

    async def _request(self, *args, **kwargs):
        return await self.client._request(*args, **kwargs)

    crop_image = ImmichApi.crop_image


async def select_candidates(client, frame, today=None, size=100):
    if frame.source == "album" and not (frame.album_ids if frame.album_ids is not None else frame.album_id):
        return []
    photos = await select(ClientAdapter(client), frame.settings(), today=date.fromisoformat(today) if today else None, size=size)
    return [Photo.from_record(p) for p in photos]
