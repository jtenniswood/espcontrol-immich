from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
ALBUMS = [{"id": "a", "albumName": "Family"}, {"id": "b", "albumName": "Trips"}]


@pytest.fixture(autouse=True)
def mock_albums():
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=ALBUMS) as albums:
        yield albums


async def start(hass):
    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
        return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
            "url": "http://immich.test", "api_key": "test-key",
        })


async def submit(hass, result, **values):
    return await hass.config_entries.flow.async_configure(result["flow_id"], values)


async def save(hass, result):
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True):
        result = await submit(hass, result, **result["data_schema"]({}))
        await hass.async_block_till_done()
    return result


async def test_back_to_album_keeps_display_settings_and_saves_new_album(hass):
    result = await submit(hass, await start(hass), source="Album")
    result = await submit(hass, result, album_id="a")
    result = await submit(hass, result, frame_name="Kitchen", mode="Matching portrait pairs",
                          orientation="Portrait photos only", screen_shape="Square (1:1, 720 × 720)", pair_window_days=3, pairs_only=True,
                          interval=75, navigation="back")
    assert result["step_id"] == "album"
    assert result["data_schema"]({})["album_id"] == "a"
    assert result["data_schema"]({})["navigation"] == "continue"
    result = await submit(hass, result, album_id="b")
    defaults = result["data_schema"]({})
    assert defaults == {"frame_name": "Kitchen", "screen_shape": "Square (1:1, 720 × 720)", "original_aspect_ratio": False, "mode": "Matching portrait pairs",
                        "orientation": "Portrait photos only", "pair_window_days": 3,
                        "pairs_only": True, "interval": 75, "navigation": "continue"}
    result = await save(hass, result)
    assert result["type"] == "create_entry"
    assert result["data"]["album_id"] == "b"
    assert result["data"]["mode"] == "pairs"
    assert result["data"]["screen_shape"] == "square"
    assert result["data"]["api_key"] == "test-key"
    assert "navigation" not in result["data"]


@pytest.mark.parametrize("label,step", [("Album", "album"), ("Smart Search", "smart")])
async def test_back_without_required_selection(hass, mock_albums, label, step):
    result = await submit(hass, await start(hass), source=label)
    assert result["step_id"] == step
    mock_albums.reset_mock()
    result = await submit(hass, result, navigation="back")
    assert result["step_id"] == "source"
    assert result["data_schema"]({})["source"] == label
    mock_albums.assert_not_awaited()
    result = await submit(hass, result, source="All photos")
    assert result["step_id"] == "display"


@pytest.mark.parametrize("label,error", [("Album", "album_required"), ("Smart Search", "smart_query_required")])
async def test_continue_requires_source_selection(hass, label, error):
    result = await submit(hass, await start(hass), source=label)
    result = await submit(hass, result, navigation="continue")
    assert result["errors"] == {"base": error}


async def test_changing_source_discards_inactive_filters_but_keeps_drafts(hass):
    result = await submit(hass, await start(hass), source="Album")
    result = await submit(hass, result, album_id="b", navigation="back")
    result = await submit(hass, result, source="On This Day memories")
    result = await submit(hass, result, memory_window_days=5, fallback_to_all=True, navigation="back")
    result = await submit(hass, result, source="Smart Search")
    result = await submit(hass, result, smart_query="beach", navigation="back")
    result = await submit(hass, result, source="Album")
    assert result["data_schema"]({})["album_id"] == "b"
    result = await submit(hass, result, navigation="back")
    result = await submit(hass, result, source="Smart Search")
    assert result["data_schema"]({})["smart_query"] == "beach"
    result = await submit(hass, result, navigation="back")
    result = await submit(hass, result, source="On This Day memories")
    assert result["data_schema"]({})["memory_window_days"] == 5
    assert result["data_schema"]({})["fallback_to_all"] is True
    result = await submit(hass, result, navigation="back")
    result = await submit(hass, result, source="All photos")
    result = await save(hass, result)
    assert result["data"]["source"] == "all"
    assert not ({"album_id", "smart_query", "memory_window_days", "fallback_to_all", "navigation"} & result["data"].keys())


@pytest.mark.parametrize("label,step,values", [
    ("All photos", "source", {}),
    ("On This Day memories", "memories", {"memory_window_days": 4, "fallback_to_all": True}),
    ("Smart Search", "smart", {"smart_query": "sea"}),
])
async def test_display_back_targets_previous_step(hass, label, step, values):
    result = await submit(hass, await start(hass), source=label)
    if values:
        result = await submit(hass, result, **values)
    result = await submit(hass, result, navigation="back")
    assert result["step_id"] == step
    defaults = result["data_schema"]({})
    assert all(defaults[key] == value for key, value in values.items())


async def test_display_can_change_source_directly(hass):
    result = await submit(hass, await start(hass), source="Album")
    result = await submit(hass, result, album_id="a")
    result = await submit(hass, result, navigation="source", interval=120)
    assert result["step_id"] == "source"
    result = await submit(hass, result, source="All photos")
    assert result["data_schema"]({})["interval"] == 120
    result = await save(hass, result)
    assert "album_id" not in result["data"]


def existing_frame(hass, title="Frame"):
    entry = MockConfigEntry(domain=DOMAIN, title=title, unique_id=f"http://immich.test|{title}", data={
        "url": "http://immich.test", "api_key": "test-key", "source": "album", "album_id": "a",
        "frame_name": title, "mode": "single", "interval": 90,
    })
    entry.add_to_hass(hass)
    return entry


async def reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(DOMAIN, context={
        "source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id,
    })


async def test_reconfigure_cancel_leaves_entry_unchanged(hass):
    entry = existing_frame(hass)
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    assert result["data_schema"]({})["source"] == "Album"
    result = await submit(hass, result, source="All photos")
    assert result["data_schema"]({})["frame_name"] == "Frame"
    assert result["data_schema"]({})["interval"] == 90
    result = await submit(hass, result, navigation="back", interval=120)
    assert dict(entry.data) == before
    hass.config_entries.flow.async_abort(result["flow_id"])
    assert dict(entry.data) == before


async def test_reconfigure_reloads_same_device_and_entities_with_new_album(hass, asset, jpeg):
    entry = existing_frame(hass)
    album_queries = []

    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            album_queries.append(kwargs["json"]["filter"]["albumIds"])
            return [asset]
        return jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
        device_ids = {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)}
        old_coordinator = hass.data[DOMAIN][entry.entry_id]
        result = await submit(hass, await reconfigure(hass, entry), source="Album")
        assert result["data_schema"]({})["album_id"] == "a"
        result = await submit(hass, result, album_id="b")
        assert entry.data["album_id"] == "a"
        result = await submit(hass, result, **result["data_schema"]({}))
        await hass.async_block_till_done()
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1
        assert entry.data["album_id"] == "b"
        assert album_queries == [{"any": ["a"]}, {"any": ["b"]}]
        assert hass.data[DOMAIN][entry.entry_id] is not old_coordinator
        assert {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)} == entity_ids
        assert {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)} == device_ids
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_duplicate_frame_name_can_be_corrected_without_losing_choices(hass):
    original = existing_frame(hass)
    existing_frame(hass, "Kitchen")
    result = await submit(hass, await reconfigure(hass, original), source="All photos")
    result = await submit(hass, result, frame_name="Kitchen", interval=120)
    assert result["step_id"] == "display"
    assert result["errors"] == {"frame_name": "name_in_use"}
    assert result["data_schema"]({})["interval"] == 120
    assert original.data["source"] == "album"
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await submit(hass, result, frame_name="Living room")
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert original.title == "Living room"
    assert original.unique_id == "http://immich.test|Living room"
    assert original.data["source"] == "all"
    assert original.data["interval"] == 120
    assert "album_id" not in original.data
