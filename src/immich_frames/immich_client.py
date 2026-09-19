"""Compatibility adapter for the app's Photo objects."""
from .client import ImmichClient as ImmichApi
from .client import ImmichClientError as ImmichError  # noqa: F401
from .models import Photo


class ImmichClient(ImmichApi):
    async def search(self, *args, **kwargs):
        return [Photo.from_record(p) for p in await super().search(*args, **kwargs)]

    async def smart_search(self, *args, **kwargs):
        return [Photo.from_record(p) for p in await super().smart_search(*args, **kwargs)]
