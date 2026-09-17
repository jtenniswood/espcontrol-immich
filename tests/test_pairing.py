from datetime import datetime, timezone

from immich_frames.models import Photo
from immich_frames.pairing import choose_companion


def photo(asset_id: str, day: int, hour: int = 12) -> Photo:
    taken = datetime(2026, 9, day, hour, tzinfo=timezone.utc)
    return Photo(asset_id, 1000, 1500, taken, taken, f"{asset_id}.jpg")


def test_same_day_is_preferred_and_tie_is_stable() -> None:
    primary = photo("primary", 17, 10)
    same_day = photo("same-day", 17, 14)
    nearby = photo("nearby", 18, 10)
    assert choose_companion(primary, [nearby, same_day], 1).id == "same-day"


def test_window_is_respected() -> None:
    primary = photo("primary", 17)
    assert choose_companion(primary, [photo("other", 20)], 2) is None


def test_non_portrait_has_no_companion() -> None:
    primary = Photo("primary", 1500, 1000, datetime(2026, 9, 17, tzinfo=timezone.utc), datetime(2026, 9, 17, tzinfo=timezone.utc), "x.jpg")
    assert choose_companion(primary, [photo("other", 17)], 0) is None


def test_landscape_pairing_can_be_used_for_portrait_output() -> None:
    primary = Photo("primary", 1500, 1000, datetime(2026, 9, 17, tzinfo=timezone.utc), datetime(2026, 9, 17, tzinfo=timezone.utc), "x.jpg")
    companion = Photo("other", 1600, 1000, datetime(2026, 9, 17, 1, tzinfo=timezone.utc), datetime(2026, 9, 17, 1, tzinfo=timezone.utc), "y.jpg")
    assert choose_companion(primary, [companion], 0, "landscape").id == "other"
