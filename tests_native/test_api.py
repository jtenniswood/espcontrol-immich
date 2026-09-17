from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from custom_components.espcontrol_immich.api import ImmichApi, ImmichApiError


@pytest.mark.parametrize("source", ["all", "album", "filter"])
async def test_first_snapshot_from_random_list(source, asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    api._request = AsyncMock(side_effect=[[asset], jpeg])
    snapshot = await api.snapshot({"source": source, "album_id": "album-id"}, 1, set())
    assert snapshot.primary["id"] == "portrait-a"
    assert snapshot.primary["exif"]["city"] == "Bath"
    assert snapshot.layout == "single"
    assert Image.open(BytesIO(snapshot.image)).size == (1920, 1080)
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


async def test_pair_mode_finds_pair_after_landscape(asset, jpeg):
    api = ImmichApi("http://immich.test", "test-key")
    landscape = {**asset, "id": "landscape", "width": 200, "height": 100}
    companion = {**asset, "id": "portrait-b"}
    api._request = AsyncMock(side_effect=[[landscape, asset, companion], jpeg, jpeg])
    snapshot = await api.snapshot({"mode": "pairs", "pairs_only": True}, 1, set())
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
