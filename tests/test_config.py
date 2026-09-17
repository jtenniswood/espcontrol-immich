import pytest

from immich_frames.app import FrameApp


def test_frame_body_supports_sources_and_pair_options() -> None:
    frame = FrameApp._frame_from_body({"name": "Hall", "source": "smart", "smart_query": "beach", "mode": "pairs", "pairs_only": True, "pair_window_days": 2, "filter": {"rating": {"gte": 4}}})
    assert frame.source == "smart"
    assert frame.smart_query == "beach"
    assert frame.pairs_only is True
    assert frame.filter["type"] == {"eq": "IMAGE"}


def test_frame_body_rejects_invalid_source() -> None:
    with pytest.raises(ValueError, match="source"):
        FrameApp._frame_from_body({"name": "Hall", "source": "unknown"})


def test_app_can_start_before_immich_is_configured(tmp_path) -> None:
    app = FrameApp({}, tmp_path)
    assert app.client is None
