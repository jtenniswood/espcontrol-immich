"""Compatibility adapter for the app's Photo objects; HTTP behavior is shared."""
from custom_components.immich_frames.core.client import ImmichApi
from custom_components.immich_frames.core.errors import ImmichApiError as ImmichError
from .models import Photo


class ImmichClient(ImmichApi):
    async def search(self, *args, **kwargs):
        return [Photo.from_record(p) for p in await super().search(*args, **kwargs)]

    async def smart_search(self, *args, **kwargs):
        return [Photo.from_record(p) for p in await super().smart_search(*args, **kwargs)]
