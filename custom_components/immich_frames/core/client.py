"""Home Assistant compatibility adapter over the reusable Immich client."""

from immich_frames.client import ImmichClient, ImmichClientError, _photo  # noqa: F401

from .engine import snapshot

ImmichApiError = ImmichClientError


class ImmichApi(ImmichClient):
    """Expose the frame snapshot operation on the external client."""

    snapshot = snapshot
