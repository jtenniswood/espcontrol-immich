"""Home Assistant compatibility facade over the shared engine."""

from .core.client import ImmichApi as _Client
from .core.client import _photo  # noqa: F401
from .core.errors import ImmichApiError, NoMatchingPhotos  # noqa: F401
from .core.models import FrameSnapshot  # noqa: F401
from .core.engine import (
    snapshot,
    companion,
    selected_album_ids,
    _with_time_range,
    _with_memory_ids,
    _datetime,
)  # noqa: F401
from .core.rendering import render


class ImmichApi(_Client):
    async def snapshot(self, options, generation, recent_ids, **kwargs):
        from .core.settings import FrameSettings

        try:
            settings = FrameSettings.from_options(options)
        except ValueError as exc:
            raise ImmichApiError(str(exc)) from exc
        return await snapshot(self, settings, generation, recent_ids, **kwargs)

    _companion = staticmethod(companion)
    _render = staticmethod(render)
