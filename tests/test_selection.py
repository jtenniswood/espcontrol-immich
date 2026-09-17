from immich_frames.selection import safe_filter


def test_selection_defaults_to_timeline_images() -> None:
    assert safe_filter({}) == {"type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"eq": "timeline"}}


def test_selection_cannot_include_locked_assets() -> None:
    result = safe_filter({"visibility": {"in": ["timeline", "locked", "archive"]}, "type": {"eq": "VIDEO"}})
    assert result["type"] == {"eq": "IMAGE"}
    assert result["visibility"] == {"in": ["timeline", "archive"]}
    assert result["trashedAt"] == {"eq": None}

