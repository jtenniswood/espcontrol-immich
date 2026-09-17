from immich_frames.selection import safe_filter
from immich_frames.filtering import FilterValidationError, compile_filter
from immich_frames.models import FrameConfig, Photo
from immich_frames.selection import select_candidates


def test_selection_defaults_to_timeline_images() -> None:
    assert safe_filter({}) == {"type": {"eq": "IMAGE"}, "trashedAt": {"eq": None}, "visibility": {"eq": "timeline"}}


def test_selection_cannot_include_locked_assets() -> None:
    result = safe_filter({"visibility": {"in": ["timeline", "locked", "archive"]}, "type": {"eq": "VIDEO"}})
    assert result["type"] == {"eq": "IMAGE"}
    assert result["visibility"] == {"in": ["timeline", "archive"]}
    assert result["trashedAt"] == {"eq": None}


def test_filter_compiler_rejects_unknown_fields() -> None:
    try:
        compile_filter({"notARealImmichField": {"eq": True}})
    except FilterValidationError as exc:
        assert "notARealImmichField" in str(exc)
    else:
        raise AssertionError("unknown filter field was accepted")


def test_filter_compiler_supports_or_branches() -> None:
    result = compile_filter({"or": [{"city": {"eq": "Bath"}}, {"isFavorite": {"eq": True}}]})
    assert len(result["or"]) == 2
    assert result["type"] == {"eq": "IMAGE"}


def test_filter_compiler_rejects_unsupported_operator() -> None:
    try:
        compile_filter({"rating": {"contains": 4}})
    except FilterValidationError as exc:
        assert "contains" in str(exc)
    else:
        raise AssertionError("unsupported filter operator was accepted")


async def test_memory_candidates_are_deduplicated() -> None:
    class Client:
        async def memories(self, for_date=None, size=100):
            return [{"assets": [{"id": "a", "width": 100, "height": 100, "originalFileName": "a.jpg"}]}]

        async def search(self, filter, size=100, order_field="fileCreatedAt", order_direction="desc"):
            assert filter["id"] == {"in": ["a"]}
            return [Photo.from_api({"id": "a", "width": 100, "height": 100, "originalFileName": "a.jpg"})]

    frame = FrameConfig("f", "Memories", source="memories", memory_window_days=1)
    result = await select_candidates(Client(), frame, today="2026-09-17")
    assert [item.id for item in result] == ["a"]
