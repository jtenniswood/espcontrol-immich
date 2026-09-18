from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN
from tests_native.flow_helpers import finish_settings

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
ALBUMS = [{"id": "a", "albumName": "Family"}, {"id": "b", "albumName": "Trips"}]


@pytest.fixture(autouse=True)
def mock_albums():
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=ALBUMS) as albums:
        yield albums


async def start(hass, *, setup=False):
    if not setup:
        return await reconfigure(hass, existing_frame(hass))
    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
        return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
            "url": "http://immich.test", "api_key": "test-key",
        })


async def submit(hass, result, **values):
    return await hass.config_entries.flow.async_configure(result["flow_id"], values)


async def save(hass, result):
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await finish_settings(hass.config_entries.flow, result)
        await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    return hass.config_entries.async_entries(DOMAIN)[0].data


async def test_back_to_album_keeps_display_settings_and_saves_new_album(hass):
    result = await submit(hass, await start(hass), source="Albums")
    result = await submit(hass, result, album_ids=["a"])
    result = await submit(hass, result, frame_name="Kitchen", navigation="back")
    assert result["step_id"] == "album"
    assert result["data_schema"]({})["album_ids"] == ["a"]
    result = await submit(hass, result, album_ids=["a", "b"])
    assert result["data_schema"]({}) == {"frame_name": "Kitchen", "navigation": "continue"}
    assert result["last_step"] is True
    result = await save(hass, result)
    assert result["album_ids"] == ["a", "b"]
    assert result["mode"] == "single"
    assert result["interval"] == 90
    assert result["api_key"] == "test-key"
    assert "navigation" not in result


@pytest.mark.parametrize("label,step", [("Albums", "album"), ("Keywords", "smart")])
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


@pytest.mark.parametrize("label,error", [("Albums", "album_required"), ("Keywords", "smart_query_required")])
async def test_continue_requires_source_selection(hass, label, error):
    result = await submit(hass, await start(hass, setup=True), source=label)
    assert "navigation" not in result["data_schema"].schema
    result = await submit(hass, result)
    assert result["errors"] == {"base": error}


async def test_changing_source_discards_inactive_filters_but_keeps_drafts(hass):
    result = await submit(hass, await start(hass), source="Albums")
    result = await submit(hass, result, album_ids=["a", "b"], navigation="back")
    result = await submit(hass, result, source="Memories")
    result = await submit(hass, result, memory_window_days=5, fallback_to_all=True, navigation="back")
    result = await submit(hass, result, source="Keywords")
    result = await submit(hass, result, smart_query="beach", navigation="back")
    result = await submit(hass, result, source="Albums")
    assert result["data_schema"]({})["album_ids"] == ["a", "b"]
    result = await submit(hass, result, navigation="back")
    result = await submit(hass, result, source="Keywords")
    assert result["data_schema"]({})["smart_query"] == "beach"
    result = await submit(hass, result, navigation="back")
    result = await submit(hass, result, source="Memories")
    assert result["data_schema"]({})["memory_window_days"] == 5
    assert result["data_schema"]({})["fallback_to_all"] is True
    result = await submit(hass, result, navigation="back")
    result = await submit(hass, result, source="All photos")
    result = await save(hass, result)
    assert result["source"] == "all"
    assert not ({"album_id", "album_ids", "smart_query", "memory_window_days", "fallback_to_all", "navigation"} & result.keys())


@pytest.mark.parametrize("label,step,values", [
    ("All photos", "source", {}),
    ("Memories", "memories", {"memory_window_days": 4, "fallback_to_all": True}),
    ("Keywords", "smart", {"smart_query": "sea"}),
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
    result = await submit(hass, await start(hass), source="Albums")
    result = await submit(hass, result, album_ids=["a"])
    result = await submit(hass, result, navigation="source")
    assert result["step_id"] == "source"
    result = await submit(hass, result, source="All photos")
    result = await save(hass, result)
    assert "album_id" not in result


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
    assert result["data_schema"]({})["source"] == "Albums"
    result = await submit(hass, result, source="All photos")
    assert result["data_schema"]({})["frame_name"] == "Frame"
    result = await submit(hass, result, navigation="back", frame_name="Draft")
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
        result = await submit(hass, await reconfigure(hass, entry), source="Albums")
        assert result["data_schema"]({})["album_ids"] == ["a"]
        result = await submit(hass, result, album_ids=["a", "b"])
        assert entry.data["album_id"] == "a"
        result = await finish_settings(hass.config_entries.flow, result)
        await hass.async_block_till_done()
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1
        assert entry.data["album_ids"] == ["a", "b"]
        assert album_queries == [{"any": ["a"]}, {"any": ["a", "b"]}]
        assert hass.data[DOMAIN][entry.entry_id] is not old_coordinator
        assert {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)} == entity_ids
        assert {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)} == device_ids
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_duplicate_frame_name_can_be_corrected_without_losing_choices(hass):
    original = existing_frame(hass)
    existing_frame(hass, "Kitchen")
    result = await submit(hass, await reconfigure(hass, original), source="All photos")
    result = await submit(hass, result, frame_name="Kitchen")
    assert result["step_id"] == "display"
    assert result["errors"] == {"frame_name": "name_in_use"}
    assert result["data_schema"]({})["frame_name"] == "Kitchen"
    assert original.data["source"] == "album"
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await submit(hass, result, frame_name="Living room")
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert original.title == "Living room"
    assert original.unique_id == "http://immich.test|Living room"
    assert original.data["source"] == "all"
    assert original.data["interval"] == 90
    assert "album_id" not in original.data
