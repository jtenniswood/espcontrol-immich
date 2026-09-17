import pytest

from immich_frames.app import FrameApp


def test_frame_body_supports_sources_and_pair_options() -> None:
    frame = FrameApp._frame_from_body({"name": "Hall", "source": "smart", "smart_query": "beach", "mode": "pairs", "pairs_only": True, "pair_window_days": 2, "filter": {"rating": {"gte": 4}}})
    assert frame.source == "smart"
    assert frame.smart_query == "beach"
    assert frame.pairs_only is True
    assert frame.filter["type"] == {"eq": "IMAGE"}


def test_frame_body_defaults_to_all_photos() -> None:
    assert FrameApp._frame_from_body({"name": "All photos"}).source == "all"


def test_frame_body_supports_album_source() -> None:
    frame = FrameApp._frame_from_body({"name": "Album", "source": "album", "album_id": "album-123"})
    assert frame.source == "album"
    assert frame.album_id == "album-123"


def test_frame_body_requires_album_id_for_album_source() -> None:
    with pytest.raises(ValueError, match="album_id"):
        FrameApp._frame_from_body({"name": "Album", "source": "album"})


def test_frame_body_rejects_invalid_source() -> None:
    with pytest.raises(ValueError, match="source"):
        FrameApp._frame_from_body({"name": "Hall", "source": "unknown"})


def test_frame_body_rejects_unknown_order_field() -> None:
    with pytest.raises(ValueError, match="order_field"):
        FrameApp._frame_from_body({"name": "Hall", "order_field": "secretField"})


def test_frame_body_requires_name() -> None:
    with pytest.raises(ValueError, match="name"):
        FrameApp._frame_from_body({"name": "  "})


def test_frame_body_supports_orientation() -> None:
    frame = FrameApp._frame_from_body({"name": "Portraits", "orientation": "portrait"})
    assert frame.orientation == "portrait"


def test_app_can_start_before_immich_is_configured(tmp_path) -> None:
    app = FrameApp({}, tmp_path)
    assert app.client is None
