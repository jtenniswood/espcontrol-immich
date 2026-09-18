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
            result = await manager.async_configure(result["flow_id"], {"next_step_id": "display"})
            return manager, result, entry
        manager = hass.config_entries.flow
        result = await manager.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    result = await manager.async_configure(result["flow_id"], {"source": "All photos"})
    return manager, result, entry


def check_form(result, step, fields, final, route):
    assert result["step_id"] == step
    assert set(result["data_schema"].schema) == {*fields, "navigation"}
    assert result["last_step"] is final
    navigation = result["data_schema"].schema["navigation"]
    assert navigation.config["mode"] == "dropdown"
    assert navigation.config["options"][0]["label"] == ("Save frame" if final else "Continue")
    # Catch untranslated raw identifiers in both setup and Configure forms.
    section = "options" if route == "options" else "config"
    component = Path(__file__).parents[1] / "custom_components" / DOMAIN
    for filename in ("strings.json", "translations/en.json"):
        labels = json.loads((component / filename).read_text())[section]["step"][step]["data"]
        for key in (*fields, "navigation"):
            assert labels[key] and labels[key] != key


@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
@pytest.mark.parametrize("pairs", [False, True])
async def test_short_steps_save_only_at_end(hass, route, pairs):
    manager, result, entry = await start(hass, route)
    before = dict(entry.data) if entry else None
    check_form(result, "display", {"frame_name", "screen_shape", "mode"}, False, route)
    result = await manager.async_configure(result["flow_id"], {"mode": "Pair portrait photos" if pairs else "Single image"})
    check_form(result, "photos", {"photo_fit", "orientation", "interval"}, not pairs, route)
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True), patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        if pairs:
            result = await manager.async_configure(result["flow_id"], {"interval": 75, "photo_fit": "show_full"})
            check_form(result, "pairing", {"pair_window_days", "pairs_only"}, True, route)
            assert dict(entry.data) == before if entry else not hass.config_entries.async_entries(DOMAIN)
            reload.assert_not_called()
            result = await manager.async_configure(result["flow_id"], {"pair_window_days": 4, "pairs_only": True})
        else:
            assert dict(entry.data) == before if entry else not hass.config_entries.async_entries(DOMAIN)
            result = await manager.async_configure(result["flow_id"], {"interval": 75, "photo_fit": "show_full"})
        await hass.async_block_till_done()
    assert result["type"] == ("abort" if route == "reconfigure" else "create_entry")
    saved = entry.data if entry else result["data"]
    assert saved["mode"] == ("pairs" if pairs else "single")
    assert saved["interval"] == 75
    assert saved["photo_fit"] == "show_full"
    if pairs:
        assert saved["pair_window_days"] == 4
        assert saved["pairs_only"] is True
    assert "navigation" not in saved


@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
async def test_switching_to_single_skips_pairing_and_cancel_preserves_entry(hass, route):
    manager, result, entry = await start(hass, route)
    before = dict(entry.data) if entry else None
    result = await manager.async_configure(result["flow_id"], {"mode": "Pair portrait photos"})
    result = await manager.async_configure(result["flow_id"], {"interval": 120})
    result = await manager.async_configure(result["flow_id"], {"pair_window_days": 5, "pairs_only": True, "navigation": "back"})
    result = await manager.async_configure(result["flow_id"], {"navigation": "back"})
    result = await manager.async_configure(result["flow_id"], {"mode": "Single image"})
    check_form(result, "photos", {"photo_fit", "orientation", "interval"}, True, route)
    assert result["data_schema"]({})["interval"] == 120
    # Changing back to pairs restores the pairing draft.
    result = await manager.async_configure(result["flow_id"], {"navigation": "back"})
    result = await manager.async_configure(result["flow_id"], {"mode": "Pair portrait photos"})
    result = await manager.async_configure(result["flow_id"], {})
    assert result["data_schema"]({})["pair_window_days"] == 5
    assert result["data_schema"]({})["pairs_only"] is True
    manager.async_abort(result["flow_id"])
    assert dict(entry.data) == before if entry else not hass.config_entries.async_entries(DOMAIN)


async def test_name_claimed_during_later_step_returns_to_frame_without_losing_draft(hass):
    manager, result, entry = await start(hass, "options")
    result = await manager.async_configure(result["flow_id"], {"frame_name": "Kitchen"})
    other = MockConfigEntry(domain=DOMAIN, title="Kitchen", unique_id="http://immich.test|Kitchen", data={})
    other.add_to_hass(hass)
    result = await manager.async_configure(result["flow_id"], {"interval": 120})
    assert result["step_id"] == "display"
    assert result["errors"] == {"frame_name": "name_in_use"}
    assert entry.title == "Frame"
    result = await manager.async_configure(result["flow_id"], {"frame_name": "Bedroom"})
    assert result["data_schema"]({})["interval"] == 120


@pytest.mark.parametrize("route", ["setup", "options", "reconfigure"])
@pytest.mark.parametrize("label,value", [("Mixed (landscapes and portraits)", "any"), ("Landscape photos only", "landscape"), ("Portrait photos only", "portrait")])
async def test_orientation_and_portrait_pair_requirement_save_independently(hass, route, label, value):
    manager, result, entry = await start(hass, route)
    result = await manager.async_configure(result["flow_id"], {"mode": "Pair portrait photos"})
    assert result["data_schema"]({})["orientation"] == "Mixed (landscapes and portraits)"
    result = await manager.async_configure(result["flow_id"], {"orientation": label})
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True), patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await manager.async_configure(result["flow_id"], {"pairs_only": True})
        await hass.async_block_till_done()
    saved = entry.data if entry else result["data"]
    assert saved["orientation"] == value
    assert saved["mode"] == "pairs"
    assert saved["pairs_only"] is True
