"""Exercise Configure through Home Assistant's real options-flow manager."""
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN
from tests_native.flow_helpers import finish_settings

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def frame(hass, source="album", title="Kitchen", **settings):
    entry = MockConfigEntry(domain=DOMAIN, title=title, unique_id=f"http://immich.test|{title}", data={
        "url": "http://immich.test", "api_key": "test-key", "frame_name": title,
        "source": source, "mode": "single", "interval": 90, **settings,
    })
    entry.add_to_hass(hass)
    return entry


async def submit(hass, result, **values):
    return await hass.config_entries.options.async_configure(result["flow_id"], values)


async def open_settings(hass, entry, step):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "source"
    if step == "source":
        return result
    return await submit(hass, result, source={"album": "Albums", "smart": "Keywords", "memories": "Memories"}[step])


@pytest.mark.parametrize("source,label", [("all", "All photos"), ("album", "Albums"), ("smart", "Keywords"), ("memories", "Memories")])
async def test_configure_opens_source_directly_with_current_selection(hass, source, label):
    entry = frame(hass, source)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "source"
    assert result["data_schema"]({})["source"] == label
    assert entry.data["source"] == source


async def test_source_edit_reloads_same_frame_without_fetching_albums(hass, asset, jpeg):
    entry = frame(hass, album_id="a")

    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            return [asset]
        return jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request), patch(
        "custom_components.immich_frames.api.ImmichApi.albums", side_effect=AssertionError("Switching to All photos must not fetch albums")
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entities = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
        devices = {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)}
        coordinator = hass.data[DOMAIN][entry.entry_id]
        result = await open_settings(hass, entry, "source")
        result = await submit(hass, result, source="All photos")
        result = await finish_settings(hass.config_entries.options, result)
        await hass.async_block_till_done()
        assert result["type"] == "create_entry"
        assert entry.data["interval"] == 90
        assert entry.data["mode"] == "single"
        assert entry.data["source"] == "all"
        assert "album_id" not in entry.data
        assert entry.data["api_key"] == "test-key"
        assert not entry.options
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1
        assert hass.data[DOMAIN][entry.entry_id] is not coordinator
        assert {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)} == entities
        assert {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)} == devices
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("source,old,new", [
    ("album", {"album_ids": ["a"]}, {"album_ids": ["a", "b"]}),
    ("smart", {"smart_query": "beach"}, {"smart_query": "mountains"}),
    ("memories", {"memory_window_days": 2, "fallback_to_all": False}, {"memory_window_days": 5, "fallback_to_all": True}),
])
async def test_source_forms_edit_saved_settings(hass, source, old, new):
    entry = frame(hass, source, **old)
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=[
        {"id": "a", "albumName": "Family"}, {"id": "b", "albumName": "Trips"},
    ]):
        result = await open_settings(hass, entry, source)
        defaults = result["data_schema"]({})
        assert all(defaults[k] == v for k, v in old.items())
        result = await submit(hass, result, **new)
        assert result["step_id"] == "display"
        assert all(entry.data[k] == v for k, v in old.items())
        with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
            result = await finish_settings(hass.config_entries.options, result)
            await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
    assert result["type"] == "create_entry"
    assert all(entry.data[k] == v for k, v in new.items())
    assert entry.data["source"] == source
    assert "navigation" not in entry.data


async def test_cancel_discards_source_changes(hass):
    entry = frame(hass, "smart", smart_query="beach")
    before = dict(entry.data)
    result = await open_settings(hass, entry, "smart")
    result = await submit(hass, result, smart_query="mountains")
    assert result["step_id"] == "display"
    assert set(result["data_schema"].schema) == {"frame_name"}
    hass.config_entries.options.async_abort(result["flow_id"])
    assert dict(entry.data) == before


async def test_change_source_clears_old_filters_and_validates_name(hass):
    entry = frame(hass, album_id="a")
    frame(hass, "all", title="Bedroom")
    result = await open_settings(hass, entry, "source")
    assert result["data_schema"]({})["source"] == "Albums"
    result = await submit(hass, result, source="Keywords")
    result = await submit(hass, result, smart_query=" ")
    assert result["errors"] == {"base": "smart_query_required"}
    result = await submit(hass, result, smart_query="beach")
    result = await submit(hass, result, frame_name="Bedroom")
    assert result["errors"] == {"frame_name": "name_in_use"}
    assert entry.data["source"] == "album"
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await submit(hass, result, frame_name="Living room")
        result = await finish_settings(hass.config_entries.options, result)
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.title == "Living room"
    assert entry.unique_id == "http://immich.test|Living room"
    assert entry.data["smart_query"] == "beach"
    assert entry.data["source"] == "smart"
    assert "album_id" not in entry.data
