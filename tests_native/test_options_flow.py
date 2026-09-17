"""Exercise Configure through Home Assistant's real options-flow manager."""
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN

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
    assert result["type"] == "menu"
    assert "display" in result["menu_options"]
    return await submit(hass, result, next_step_id=step)


@pytest.mark.parametrize("source,shortcut", [("all", None), ("album", "album"), ("smart", "smart"), ("memories", "memories")])
async def test_menu_offers_current_source_and_display(hass, source, shortcut):
    entry = frame(hass, source)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["source", *([shortcut] if shortcut else []), "display"]


async def test_display_edit_reloads_same_frame_without_fetching_albums(hass, asset, jpeg):
    entry = frame(hass, album_id="a")

    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            assert kwargs["json"]["filter"]["albumIds"] == {"any": ["a"]}
            return [asset]
        return jpeg

    with patch("custom_components.immich_frames.api.ImmichApi._request", request), patch(
        "custom_components.immich_frames.api.ImmichApi.albums", side_effect=AssertionError("Display edits must not fetch albums")
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entities = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
        devices = {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)}
        coordinator = hass.data[DOMAIN][entry.entry_id]
        result = await open_settings(hass, entry, "display")
        assert result["data_schema"]({})["interval"] == 90
        result = await submit(hass, result, interval=120, mode="Matching portrait pairs", pair_window_days=3)
        await hass.async_block_till_done()
        assert result["type"] == "create_entry"
        assert entry.data["interval"] == 120
        assert entry.data["mode"] == "pairs"
        assert entry.data["pair_window_days"] == 3
        assert entry.data["album_id"] == "a"
        assert entry.data["api_key"] == "test-key"
        assert not entry.options
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1
        assert hass.data[DOMAIN][entry.entry_id] is not coordinator
        assert {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)} == entities
        assert {d.id for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)} == devices
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("source,old,new", [
    ("album", {"album_id": "a"}, {"album_id": "b"}),
    ("smart", {"smart_query": "beach"}, {"smart_query": "mountains"}),
    ("memories", {"memory_window_days": 2, "fallback_to_all": False}, {"memory_window_days": 5, "fallback_to_all": True}),
])
async def test_source_shortcuts_edit_saved_settings(hass, source, old, new):
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
            result = await submit(hass, result, **result["data_schema"]({}))
            await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
    assert result["type"] == "create_entry"
    assert all(entry.data[k] == v for k, v in new.items())
    assert entry.data["source"] == source
    assert "navigation" not in entry.data


async def test_cancel_discards_changes_and_back_preserves_draft(hass):
    entry = frame(hass, "smart", smart_query="beach")
    before = dict(entry.data)
    result = await open_settings(hass, entry, "smart")
    result = await submit(hass, result, smart_query="mountains")
    result = await submit(hass, result, interval=120, navigation="back")
    assert result["step_id"] == "smart"
    assert result["data_schema"]({})["smart_query"] == "mountains"
    hass.config_entries.options.async_abort(result["flow_id"])
    assert dict(entry.data) == before


async def test_change_source_clears_old_filters_and_validates_name(hass):
    entry = frame(hass, album_id="a")
    frame(hass, "all", title="Bedroom")
    result = await open_settings(hass, entry, "source")
    assert result["data_schema"]({})["source"] == "Album"
    result = await submit(hass, result, source="Smart Search")
    result = await submit(hass, result, smart_query=" ")
    assert result["errors"] == {"base": "smart_query_required"}
    result = await submit(hass, result, smart_query="beach")
    result = await submit(hass, result, frame_name="Bedroom")
    assert result["errors"] == {"frame_name": "name_in_use"}
    assert entry.data["source"] == "album"
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await submit(hass, result, frame_name="Living room")
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.title == "Living room"
    assert entry.unique_id == "http://immich.test|Living room"
    assert entry.data["smart_query"] == "beach"
    assert entry.data["source"] == "smart"
    assert "album_id" not in entry.data
