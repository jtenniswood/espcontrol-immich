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

@pytest.mark.parametrize("size", [(1920, 1080), (800, 1280), (4096, 4096)])
def test_requested_output_dimensions_use_fixed_frame(size):
    frame = FrameApp._frame_from_body({"name": "Frame", "output_width": size[0], "output_height": size[1]})
    assert (frame.output_width, frame.output_height) == (1280, 800)


def test_multiple_albums_take_precedence_over_legacy_selection() -> None:
    frame = FrameApp._frame_from_body({"name": "Albums", "source": "album", "album_ids": ["a", "b", "a"], "album_id": "old"})
    assert frame.album_ids == ["a", "b"]
    assert frame.album_id is None


@pytest.mark.parametrize("album_ids", [[], "a", [None], [""], ["a", 12]])
def test_invalid_multiple_album_selection_is_rejected(album_ids) -> None:
    with pytest.raises(ValueError, match="album_ids"):
        FrameApp._frame_from_body({"name": "Albums", "source": "album", "album_ids": album_ids, "album_id": "old"})
