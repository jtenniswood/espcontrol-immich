from __future__ import annotations

from datetime import date, timedelta

from .models import Photo


def _day(photo: Photo) -> date | None:
    capture = photo.capture_time
    return capture.date() if capture else None


def choose_companion(primary: Photo, candidates: list[Photo], window_days: int, orientation: str = "portrait") -> Photo | None:
    """Choose a deterministic, same-day-first companion for a primary image."""
    if primary.orientation != orientation:
        return None
    primary_day = _day(primary)
    if primary_day is None:
        return None
    eligible = [
        p for p in candidates
        if p.id != primary.id
        and (not primary.checksum or not p.checksum or p.checksum != primary.checksum)
        and p.orientation == orientation
        and _day(p)
    ]
    eligible = [p for p in eligible if abs((_day(p) - primary_day).days) <= max(0, window_days)]
    return min(eligible, key=lambda p: (abs((p.capture_time - primary.capture_time).total_seconds()), p.id)) if eligible else None
