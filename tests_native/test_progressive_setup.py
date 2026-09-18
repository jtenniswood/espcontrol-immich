"""Keep setup compact and defer writes until the last relevant step."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def start(hass, route):
    if route == "setup":
        manager = hass.config_entries.flow
        with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
            result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
                "url": "http://immich.test", "api_key": "key",
            })
        entry = None
    else:
        entry = MockConfigEntry(domain=DOMAIN, title="Frame", unique_id="http://immich.test|Frame", data={
            "url": "http://immich.test", "api_key": "key", "frame_name": "Frame", "source": "all",
            "mode": "single", "interval": 30,
        })
        entry.add_to_hass(hass)
        if route == "options":
            manager = hass.config_entries.options
            result = await manager.async_init(entry.entry_id)
        else:
            manager = hass.config_entries.flow
            result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    return manager, result, entry


def check_form(result, step, fields, final, route):
    assert result["step_id"] == step
    expected_fields = set(fields)
    assert set(result["data_schema"].schema) == expected_fields
    assert result["last_step"] is final
    # Catch untranslated raw identifiers in both setup and Configure forms.
    section = "options" if route == "options" else "config"
    component = Path(__file__).parents[1] / "custom_components" / DOMAIN
    for filename in ("strings.json", "translations/en.json"):
        labels = json.loads((component / filename).read_text())[section]["step"][step]["data"]
        for key in expected_fields:
            assert labels[key] and labels[key] != key


@pytest.mark.parametrize("route", ["options", "reconfigure"])
@pytest.mark.parametrize("pairs", [False, True])
@pytest.mark.parametrize("source", ["All photos", "Albums", "Memories", "Keywords"])
async def test_source_edits_save_directly_and_keep_device_settings(hass, route, pairs, source):
    manager, result, entry = await start(hass, route)
    # Simulate device controls being changed while the source dialog is open.
    display_settings = {
        "mode": "pairs" if pairs else "single", "screen_shape": "portrait",
        "photo_fit": "crop", "orientation": "landscape", "interval": 75,
        "pair_window_days": 4, "time_range": "6_months",
    }
    hass.config_entries.async_update_entry(entry, data={**entry.data, **display_settings})
    before = dict(entry.data)
    check_form(result, "source", {"source"}, None, route)
    assert dict(entry.data) == before
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=[{"id": "a", "albumName": "Family"}]), patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await manager.async_configure(result["flow_id"], {"source": source})
        if source in ("Albums", "Keywords"):
            step, values = {
                "Albums": ("album", {"album_ids": ["a"]}),
                "Keywords": ("smart", {"smart_query": "beach"}),
            }[source]
            check_form(result, step, set(values), True, route)
            assert dict(entry.data) == before
            result = await manager.async_configure(result["flow_id"], values)
        await hass.async_block_till_done()
    assert result["type"] == ("abort" if route == "reconfigure" else "create_entry")
    if source == "All photos" and route == "options":
        reload.assert_not_awaited()  # Saving unchanged settings needs no reload.
    else:
        reload.assert_awaited_once_with(entry.entry_id)
    assert entry.data["source"] == {"All photos": "all", "Albums": "album", "Memories": "memories", "Keywords": "smart"}[source]
    assert all(entry.data[key] == value for key, value in display_settings.items())
    assert "navigation" not in entry.data
    assert entry.title == entry.data["frame_name"] == "Frame"
    assert entry.unique_id == "http://immich.test|Frame"


@pytest.mark.parametrize("route", ["options", "reconfigure"])
async def test_cancel_preserves_entry(hass, route):
    manager, result, entry = await start(hass, route)
    before = dict(entry.data)
    result = await manager.async_configure(result["flow_id"], {"source": "Keywords"})
    check_form(result, "smart", {"smart_query"}, True, route)
    manager.async_abort(result["flow_id"])
    assert dict(entry.data) == before


async def test_new_frame_still_validates_duplicate_names(hass):
    manager, result, _ = await start(hass, "setup")
    result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    other = MockConfigEntry(domain=DOMAIN, title="Kitchen", unique_id="http://immich.test|Kitchen", data={})
    other.add_to_hass(hass)
    result = await manager.async_configure(result["flow_id"], {"frame_name": "Kitchen"})
    assert result["step_id"] == "display"
    assert result["errors"] == {"frame_name": "name_in_use"}
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True):
        result = await manager.async_configure(result["flow_id"], {"frame_name": "Bedroom"})
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["title"] == "Bedroom"


@pytest.mark.parametrize("source,extra", [
    ("All photos", None), ("Albums", {"album_ids": ["a"]}),
    ("Memories", None), ("Keywords", {"smart_query": "beach"}),
])
async def test_new_setup_finishes_after_name_with_defaults(hass, source, extra):
    manager = hass.config_entries.flow
    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"), patch(
        "custom_components.immich_frames.api.ImmichApi.albums", return_value=[{"id": "a", "albumName": "Family"}],
    ):
        result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER}, data={
            "url": "http://immich.test", "api_key": "key",
        })
        result = await manager.async_configure(result["flow_id"], {"source": source})
        if extra:
            result = await manager.async_configure(result["flow_id"], extra)
    check_form(result, "display", {"frame_name"}, True, "setup")
    assert not hass.config_entries.async_entries(DOMAIN)
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True):
        result = await manager.async_configure(result["flow_id"], {"frame_name": "Kitchen"})
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    for key, value in {
        "mode": "single", "photo_fit": "show_full", "orientation": "any",
        "interval": 30, "pair_window_days": 2, "screen_shape": "landscape",
    }.items():
        assert result["data"][key] == value

    if source == "Memories":
        assert result["data"]["memory_window_days"] == 2
        assert result["data"]["fallback_to_all"] is False


@pytest.mark.parametrize("route", ["options", "reconfigure"])
@pytest.mark.parametrize("saved", [{}, {"memory_window_days": 5, "fallback_to_all": True}])
async def test_memories_matches_setup_and_preserves_existing_preferences(hass, route, saved):
    manager, result, entry = await start(hass, route)
    # Start a new edit after saving the existing Memories preferences.
    manager.async_abort(result["flow_id"])
    hass.config_entries.async_update_entry(entry, data={**entry.data, "source": "memories", **saved})
    if route == "options":
        result = await manager.async_init(entry.entry_id)
    else:
        result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await manager.async_configure(result["flow_id"], {"source": "Memories"})
        await hass.async_block_till_done()
    assert result["type"] == ("abort" if route == "reconfigure" else "create_entry")
    assert entry.data["memory_window_days"] == saved.get("memory_window_days", 2)
    assert entry.data["fallback_to_all"] == saved.get("fallback_to_all", False)
