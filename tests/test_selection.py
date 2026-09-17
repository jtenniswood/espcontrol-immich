import pytest

from immich_frames.selection import safe_filter
from immich_frames.filtering import FilterValidationError, compile_filter
from immich_frames.models import FrameConfig, Photo
from immich_frames.selection import select_candidates


@pytest.mark.parametrize("field", ["id", "libraryId"])
@pytest.mark.parametrize("condition", [{"in": ["a"]}, {"notIn": ["a"]}, {}])
def test_id_filters_reject_unsupported_list_operators(field, condition):
    with pytest.raises(FilterValidationError):
        compile_filter({field: condition})


@pytest.mark.parametrize("field", ["id", "libraryId"])
def test_id_filters_accept_scalar_comparisons(field):
    assert compile_filter({field: {"eq": "a", "ne": "b"}})[field] == {"eq": "a", "ne": "b"}


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
            assert filter["or"] == [{"id": {"eq": "a"}}]
            return [Photo.from_api({"id": "a", "width": 100, "height": 100, "originalFileName": "a.jpg"})]

    frame = FrameConfig("f", "Memories", source="memories", memory_window_days=1)
    result = await select_candidates(Client(), frame, today="2026-09-17")
    assert [item.id for item in result] == ["a"]


async def test_orientation_is_applied_after_metadata_search() -> None:
    class Client:
        async def search(self, filter, size=100, random=False, order_field="fileCreatedAt", order_direction="desc"):
            return [
                Photo("portrait", 100, 200, None, None, "portrait.jpg"),
                Photo("landscape", 200, 100, None, None, "landscape.jpg"),
            ]

    frame = FrameConfig("f", "Portraits", orientation="portrait")
    result = await select_candidates(Client(), frame)
    assert [item.id for item in result] == ["portrait"]


async def test_album_candidates_use_album_id_filter() -> None:
    class Client:
        async def search(self, filter, size=100, random=False, order_field="fileCreatedAt", order_direction="desc"):
            assert filter["albumIds"] == {"any": ["album-123"]}
            return [Photo("album-photo", 100, 100, None, None, "album.jpg")]

    frame = FrameConfig("f", "Album", source="album", album_id="album-123")
    result = await select_candidates(Client(), frame)
    assert [item.id for item in result] == ["album-photo"]
