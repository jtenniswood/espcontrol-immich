from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from custom_components.immich_frames.api import ImmichApi, ImmichApiError


@pytest.mark.parametrize("source", ["all", "album", "filter"])
async def test_first_snapshot_from_random_list(source, asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(side_effect=[[asset], jpeg])
    snapshot = await api.snapshot({"source": source, "album_id": "album-id"}, 1, set())
    assert snapshot.primary["id"] == "portrait-a"
    assert snapshot.primary["exif"]["city"] == "Bath"
    assert snapshot.layout == "single"
    assert Image.open(BytesIO(snapshot.image)).size == (1280, 800)
    request = api._request.call_args_list[0]
    assert request.args == ("POST", "/api/search/random")
    query = request.kwargs["json"]["filter"]
    assert query["type"] == {"eq": "IMAGE"}
    assert query["trashedAt"] == {"eq": None}
    assert query["visibility"] == {"eq": "timeline"}
    if source == "album":
        assert query["albumIds"] == {"any": ["album-id"]}


async def test_empty_random_list_is_a_normal_no_photos_error():
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(return_value=[])
    with pytest.raises(ImmichApiError, match="No photos"):
        await api.snapshot({}, 1, set())


@pytest.mark.parametrize("method", ["search", "smart_search"])
async def test_metadata_and_smart_search_use_envelope(method, asset):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(return_value={"assets": {"items": [asset], "nextCursor": None}})
    photos = await (api.search({}) if method == "search" else api.smart_search("beach", {}))
    assert [photo["id"] for photo in photos] == [asset["id"]]


async def test_numeric_server_version():
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(return_value={"major": 3, "minor": 2, "patch": 0})
    assert await api.version() == "3.2.0"


@pytest.mark.parametrize("payload", [None, {}, {"assets": []}, {"assets": {"items": None}}])
async def test_malformed_search_has_actionable_error(payload):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(return_value=payload)
    with pytest.raises(ImmichApiError, match="invalid photo search response"):
        await api.search({})


@pytest.mark.parametrize("source", ["memories", "smart"])
async def test_other_sources_render(source, asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    replies = [{"assets": {"items": [asset]}}, jpeg]
    if source == "memories":
        replies.insert(0, [{"assets": [{"id": asset["id"]}]}])
    api._request = AsyncMock(side_effect=replies)
    snapshot = await api.snapshot({"source": source, "memory_window_days": 0, "smart_query": "beach"}, 1, set())
    assert snapshot.primary["id"] == asset["id"]


async def test_pair_mode_keeps_landscapes_then_shows_portrait_pairs(asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    landscape = {**asset, "id": "landscape", "width": 200, "height": 100}
    companion = {**asset, "id": "portrait-b"}
    api._request = AsyncMock(side_effect=[[landscape, asset, companion], jpeg, [landscape, asset, companion], jpeg, jpeg])
    options = {"mode": "pairs"}
    first = await api.snapshot(options, 1, set())
    assert [photo["id"] for photo in first.photos] == ["landscape"]
    assert first.layout == "single"
    snapshot = await api.snapshot(options, 2, {"landscape"})
    assert [photo["id"] for photo in snapshot.photos] == ["portrait-a", "portrait-b"]
    assert snapshot.layout == "side_by_side"


async def test_corrupt_preview_has_controlled_error(asset):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(side_effect=[[asset], b"not an image"])
    with pytest.raises(ImmichApiError, match="decode"):
        await api.snapshot({}, 1, set())


async def test_empty_memories_fallback_uses_random_list(asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(side_effect=[[], [asset], jpeg])
    snapshot = await api.snapshot({"source": "memories", "memory_window_days": 0, "fallback_to_all": True}, 1, set())
    assert snapshot.primary["id"] == asset["id"]


async def test_unsupported_server_stops_before_search():
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(return_value={"major": 3, "minor": 1, "patch": 0})
    with pytest.raises(ImmichApiError, match="3.2 or later"):
        await api.validate_connection()
    api._request.assert_awaited_once()


async def test_multiple_albums_share_one_photo_pool(asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    companion = {**asset, "id": "photo-from-second-album"}
    api._request = AsyncMock(side_effect=[[asset, companion], jpeg, jpeg])
    snapshot = await api.snapshot({
        "source": "album", "album_ids": ["a", "b", "a"], "album_id": "old",
        "mode": "pairs",
    }, 1, set())
    query = api._request.call_args_list[0].kwargs["json"]["filter"]
    assert query["albumIds"] == {"any": ["a", "b"]}
    assert [photo["id"] for photo in snapshot.photos] == [asset["id"], companion["id"]]


@pytest.mark.parametrize("options", [{}, {"album_id": None}, {"album_ids": []}, {"album_ids": [], "album_id": "old"}])
async def test_empty_album_selection_never_falls_back_to_all_photos(options):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock()
    with pytest.raises(ImmichApiError, match="Choose at least one album"):
        await api.snapshot({"source": "album", **options}, 1, set())
    api._request.assert_not_awaited()


@pytest.mark.parametrize("pairs_only", [False, True])
async def test_retired_setting_does_not_skip_unmatched_portraits(asset, jpeg, pairs_only):
    api = ImmichApi("http://immich.test", "test-key")
    landscape = {**asset, "id": "landscape", "width": 200, "height": 100}
    api._request = AsyncMock(side_effect=[[asset, landscape], jpeg])
    snapshot = await api.snapshot({"mode": "pairs", "pairs_only": pairs_only}, 1, set())
    assert snapshot.primary["id"] == asset["id"]
    assert snapshot.layout == "single"


@pytest.mark.parametrize("source", ["all", "album", "smart", "memories"])
@pytest.mark.parametrize("orientation,expected", [("any", ["landscape"]), ("landscape", ["landscape"]), ("portrait", ["portrait-a", "portrait-b"])])
async def test_orientation_filter_is_independent_of_pairing(asset, jpeg, source, orientation, expected):
    api = ImmichApi("http://immich.test", "test-key")
    assets = [{**asset, "id": "landscape", "width": 200, "height": 100}, asset, {**asset, "id": "portrait-b"}]
    replies = [assets if source in ("all", "album") else {"assets": {"items": assets}}]
    if source == "memories":
        replies.insert(0, [{"assets": [{"id": item["id"]} for item in assets]}])
    api._request = AsyncMock(side_effect=[*replies, *([jpeg] * len(expected))])
    snapshot = await api.snapshot({"source": source, "album_ids": ["a"], "smart_query": "beach", "memory_window_days": 0,
                                   "mode": "pairs", "orientation": orientation}, 1, set())
    assert [photo["id"] for photo in snapshot.photos] == expected


@pytest.mark.parametrize("missing_date", [False, True])
async def test_portraits_only_with_no_pair_shows_single_photo(asset, jpeg, missing_date):
    api = ImmichApi("http://immich.test", "test-key")
    if missing_date:
        asset = {**asset, "localDateTime": None}
    api._request = AsyncMock(side_effect=[[asset], jpeg])
    snapshot = await api.snapshot({"mode": "pairs", "orientation": "portrait"}, 1, set())
    assert snapshot.primary["id"] == asset["id"]
    assert snapshot.layout == "single"


async def test_unmatched_portrait_precedes_later_pair(asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    unmatched = {**asset, "id": "unmatched", "localDateTime": "2026-09-01T12:00:00Z"}
    companion = {**asset, "id": "portrait-b"}
    api._request = AsyncMock(side_effect=[[unmatched, asset, companion], jpeg, [unmatched, asset, companion], jpeg, jpeg])
    snapshot = await api.snapshot({"mode": "pairs"}, 1, set())
    assert [photo["id"] for photo in snapshot.photos] == ["unmatched"]
    snapshot = await api.snapshot({"mode": "pairs"}, 2, {"unmatched"})
    assert [photo["id"] for photo in snapshot.photos] == ["portrait-a", "portrait-b"]


async def test_default_settings_show_both_orientations(asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    landscape = {**asset, "id": "landscape", "width": 200, "height": 100}
    api._request = AsyncMock(side_effect=[[landscape, asset], jpeg, [landscape, asset], jpeg])
    first = await api.snapshot({}, 1, set())
    second = await api.snapshot({}, 2, {first.primary["id"]})
    assert [first.primary["id"], second.primary["id"]] == ["landscape", "portrait-a"]
    assert first.layout == second.layout == "single"
