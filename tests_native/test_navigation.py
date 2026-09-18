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


@pytest.mark.parametrize("setup", [False, True])
@pytest.mark.parametrize("label,error", [("Albums", "album_required"), ("Keywords", "smart_query_required")])
async def test_continue_requires_source_selection(hass, label, error, setup):
    result = await submit(hass, await start(hass, setup=setup), source=label)
    assert "navigation" not in result["data_schema"].schema
    values = {"album_ids": []} if label == "Albums" else {"smart_query": ""}
    result = await submit(hass, result, **values)
    assert result["errors"] == {"base": error}


@pytest.mark.parametrize("label,values,active", [
    ("All photos", {}, set()),
    ("Albums", {"album_ids": ["b"]}, {"album_ids"}),
    ("Memories", {}, {"memory_window_days", "fallback_to_all"}),
    ("Keywords", {"smart_query": "sea"}, {"smart_query"}),
])
async def test_source_edits_clear_inactive_filters_without_navigation(hass, label, values, active):
    entry = existing_frame(hass)
    hass.config_entries.async_update_entry(entry, data={
        **entry.data, "album_ids": ["a"], "memory_window_days": 2,
        "fallback_to_all": False, "smart_query": "beach",
    })
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await submit(hass, await reconfigure(hass, entry), source=label)
        if values:
            assert "navigation" not in result["data_schema"].schema
            assert result["last_step"] is True
            result = await submit(hass, result, **values)
        saved = await save(hass, result)
    fields = {"album_id", "album_ids", "smart_query", "memory_window_days", "fallback_to_all"}
    assert fields & saved.keys() == active
    assert all(saved[key] == value for key, value in values.items())
    assert "navigation" not in saved


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
    result = await submit(hass, result, source="Keywords")
    assert result["step_id"] == "smart"
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
        assert entry.data["album_id"] == "a"
        result = await submit(hass, result, album_ids=["a", "b"])
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


async def test_reconfigure_preserves_existing_name_title_and_unique_id(hass):
    original = existing_frame(hass)
    # A renamed display title must not change the stored identity during source edits.
    hass.config_entries.async_update_entry(original, title="Living room", unique_id="legacy-frame-id")
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await submit(hass, await reconfigure(hass, original), source="All photos")
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert original.title == "Living room"
    assert original.data["frame_name"] == "Frame"
    assert original.unique_id == "legacy-frame-id"
    assert original.data["source"] == "all"
    assert original.data["interval"] == 90
    assert "album_id" not in original.data
