"""Home Assistant compatibility facade over the shared engine."""
from .core.client import ImmichApi as _Client
from .core.client import _photo  # noqa: F401
from .core.errors import ImmichApiError, NoMatchingPhotos  # noqa: F401
from .core.models import FrameSnapshot  # noqa: F401
from .core.engine import snapshot, companion, selected_album_ids, _with_time_range, _with_memory_ids, _datetime  # noqa: F401
from .core.rendering import render


class ImmichApi(_Client):
    snapshot = snapshot
    _companion = staticmethod(companion)
    _render = staticmethod(render)
