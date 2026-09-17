from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError
from custom_components.immich_frames.api import _with_memory_ids as native_memory_filter
from custom_components.immich_frames.const import DOMAIN
from immich_frames.selection import _with_memory_ids as renderer_memory_filter

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("build_filter", [native_memory_filter, renderer_memory_filter])
def test_memory_filter_preserves_existing_alternatives_and_id_constraints(build_filter):
    query = {"type": {"eq": "IMAGE"}, "id": {"ne": "excluded"}, "or": [
        {"city": {"eq": "Bath"}}, {"isFavorite": {"eq": True}, "id": {"ne": B}},
        {"id": {"eq": B}}, {"id": {"eq": "not-a-memory"}},
    ]}
    before = deepcopy(query)
    result = build_filter(query, [A, B])
    assert result == {"type": {"eq": "IMAGE"}, "id": {"ne": "excluded"}, "or": [
        {"city": {"eq": "Bath"}, "id": {"eq": A}},
        {"city": {"eq": "Bath"}, "id": {"eq": B}},
        {"isFavorite": {"eq": True}, "id": {"eq": A}},
        {"id": {"eq": B}},
    ]}
    assert query == before


@pytest.mark.parametrize("build_filter", [native_memory_filter, renderer_memory_filter])
def test_empty_or_conflicting_memories_do_not_become_an_unrestricted_search(build_filter):
    assert build_filter({"type": {"eq": "IMAGE"}}, []) is None
    assert build_filter({"or": [{"id": {"eq": "not-a-memory"}}]}, [A, B]) is None


async def test_empty_memories_without_fallback_do_not_search_library():
    api = ImmichApi("http://immich.test", "key")
    api._request = AsyncMock(return_value=[])
    with pytest.raises(ImmichApiError, match="No photos match"):
        await api.snapshot({"source": "memories", "memory_window_days": 0}, 1, set())
    api._request.assert_awaited_once()
    assert api._request.call_args.args == ("GET", "/api/memories")


def check_memory_filter(query):
    # Immich 3.2 IdFilter accepts only scalar eq/ne, not list operators.
    if "in" in query.get("id", {}):
        raise ImmichApiError('Validation failed: filter.id requires eq or ne', 400)
    assert query["type"] == {"eq": "IMAGE"}
    assert query["visibility"] == {"eq": "timeline"}
    assert query["trashedAt"] == {"eq": None}
    branches = query["or"]
    assert branches
    for branch in branches:
        assert set(branch["id"]) == {"eq"}
        assert isinstance(branch["id"]["eq"], str)
    return [branch["id"]["eq"] for branch in branches]


@pytest.mark.parametrize("mode", ["single", "pairs"])
async def test_memories_fetch_metadata_with_supported_id_filters(asset, jpeg, mode):
    photos = [{**asset, "id": A}, {**asset, "id": B}]
    requests = []

    async def request(_api, method, path, **kwargs):
        requests.append((method, path, kwargs))
        if path == "/api/memories":
            return [{"assets": [{"id": A}, {"id": B}, {"id": A}]}]
        if path == "/api/search/metadata":
            assert check_memory_filter(kwargs["json"]["filter"]) == [A, B]
            assert kwargs["json"]["withExif"] is True
            return {"assets": {"items": photos}}
        assert path in (f"/api/assets/{A}/thumbnail", f"/api/assets/{B}/thumbnail")
        return jpeg

    with patch.object(ImmichApi, "_request", request):
        snapshot = await ImmichApi("http://immich.test", "key").snapshot({
            "source": "memories", "memory_window_days": 1, "mode": mode, "pairs_only": True,
        }, 1, set())
    assert snapshot.primary["id"] == A
    assert snapshot.primary["exif"]["city"] == "Bath"
    assert snapshot.layout == ("side_by_side" if mode == "pairs" else "single")
    assert len([item for item in requests if item[1] == "/api/memories"]) == 3
    assert len([item for item in requests if item[1] == "/api/search/metadata"]) == 1


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_second_frame_memories_setup_succeeds(hass, asset, jpeg):
    first = MockConfigEntry(domain=DOMAIN, title="First frame", data={
        "url": "http://immich.test", "api_key": "key", "source": "all",
    })
    second = MockConfigEntry(domain=DOMAIN, title="Immich Frame2", data={
        "url": "http://immich.test", "api_key": "key", "source": "memories", "memory_window_days": 0,
    })
    first.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            return [asset]
        if path == "/api/memories":
            return [{"assets": [{"id": A}]}]
        if path == "/api/search/metadata":
            assert check_memory_filter(kwargs["json"]["filter"]) == [A]
            return {"assets": {"items": [{**asset, "id": A}]}}
        return jpeg

    with patch.object(ImmichApi, "_request", request):
        assert await hass.config_entries.async_setup(first.entry_id)
        await hass.async_block_till_done()
        second.add_to_hass(hass)
        assert await hass.config_entries.async_setup(second.entry_id)
        await hass.async_block_till_done()
        assert hass.data[DOMAIN][first.entry_id].data.primary["id"] == asset["id"]
        assert hass.data[DOMAIN][second.entry_id].data.primary["id"] == A
        assert hass.states.get("image.immich_frame2_frame") is not None
        assert await hass.config_entries.async_unload(first.entry_id)
        assert await hass.config_entries.async_unload(second.entry_id)
