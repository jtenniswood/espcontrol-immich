from custom_components.immich_frames.core.engine import companion
from .models import Photo


def choose_companion(primary, candidates, window_days, orientation="portrait"):
    result = companion(primary.record(), [p.record() for p in candidates], window_days, orientation)
    return Photo.from_record(result) if result else None
