from immich_frames.client import ImmichClientError

ImmichApiError = ImmichClientError


class NoMatchingPhotos(ImmichApiError):
    """The source query completed but returned no eligible photos."""
