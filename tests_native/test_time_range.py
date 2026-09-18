"""Calendar ranges apply to all sources through the actual device control."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.translation import async_translate_state

from custom_components.immich_frames.api import ImmichApi, ImmichApiError, _with_time_range
from custom_components.immich_frames.const import DOMAIN
from tests_native.test_device_settings import frame, set_value

NOW = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)
CHOICES = [
    ("all_time", "All time", None),
    ("1_month", "Last 1 month", "2026-08-18"),
    ("3_months", "Last 3 months", "2026-06-18"),
    ("6_months", "Last 6 months", "2026-03-18"),
    ("1_year", "Last 1 year", "2025-09-18"),
    ("2_years", "Last 2 years", "2024-09-18"),
    ("3_years", "Last 3 years", "2023-09-18"),
    ("4_years", "Last 4 years", "2022-09-18"),
    ("5_years", "Last 5 years", "2021-09-18"),
    ("10_years", "Last 10 years", "2016-09-18"),
]


@pytest.mark.parametrize("option,label,start", CHOICES)
def test_calendar_ranges(option, label, start):
    query = {"type": {"eq": "IMAGE"}}
    result = _with_time_range(query, option, NOW)
    assert query == {"type": {"eq": "IMAGE"}}
    if start:
        assert result["takenAt"] == {"gte": f"{start}T12:00:00+00:00", "lte": NOW.isoformat()}
    else:
        assert result == query


@pytest.mark.parametrize("now,option,start", [
    ("2026-03-31", "1_month", "2026-02-28"),
    ("2024-03-31", "1_month", "2024-02-29"),
    ("2024-02-29", "1_year", "2023-02-28"),
    ("2024-02-29", "4_years", "2020-02-29"),
    ("2026-01-31", "3_months", "2025-10-31"),
])
def test_month_end_and_leap_years(now, option, start):
    result = _with_time_range({}, option, datetime.fromisoformat(now).replace(tzinfo=timezone.utc))
    assert result["takenAt"]["gte"] == f"{start}T00:00:00+00:00"


def test_existing_date_rules_are_intersected_without_mutation():
    query = {"takenAt": {"gte": "2026-09-01T00:00:00Z", "lte": "2026-09-10T00:00:00Z", "ne": "2026-09-05T00:00:00Z"},
             "or": [{"city": {"eq": "Bath"}}, {"isFavorite": {"eq": True}}]}
    before = deepcopy(query)
    result = _with_time_range(query, "1_month", NOW)
    assert result["takenAt"] == {"gte": "2026-09-01T00:00:00+00:00", "lte": "2026-09-10T00:00:00+00:00", "ne": "2026-09-05T00:00:00Z"}
    assert result["or"] == before["or"]
    assert query == before


@pytest.mark.parametrize("source", ["all", "album", "smart", "memories"])
@pytest.mark.parametrize("paired", [False, True])
async def test_each_source_sends_range_before_selection(asset, jpeg, source, paired):
    calls = []
    async def request(_api, method, path, **kwargs):
        if path == "/api/memories":
            return [{"assets": [{"id": asset["id"]}, {"id": "second"}]}]
        if path.startswith("/api/search/"):
            query = kwargs["json"]["filter"]
            calls.append(query)
            assert query["takenAt"] == {"gte": "2026-08-18T12:00:00+00:00", "lte": NOW.isoformat()}
            if source == "album":
                assert query["albumIds"] == {"any": ["album-a", "album-b"]}
            if source == "smart":
                assert kwargs["json"]["query"] == "beach"
            if source == "memories":
                assert query["or"] == [{"id": {"eq": asset["id"]}}, {"id": {"eq": "second"}}]
            photos = [asset, {**asset, "id": "second"}]
            return photos if path.endswith("random") else {"assets": {"items": photos}}
        return jpeg

    with patch.object(ImmichApi, "_request", request), patch("custom_components.immich_frames.core.engine.datetime") as clock:
        clock.now.return_value = NOW
        clock.fromisoformat = datetime.fromisoformat
        snapshot = await ImmichApi("http://immich.test", "key").snapshot({
            "source": source, "album_ids": ["album-a", "album-b"], "smart_query": "beach",
            "memory_window_days": 0, "time_range": "1_month", "mode": "pairs" if paired else "single",
        }, 1, set())
    assert len(calls) == 1
    assert len(snapshot.photos) == (2 if paired else 1)


async def test_empty_memories_fallback_keeps_range_and_does_not_widen():
    calls = []
    async def request(_api, method, path, **kwargs):
        calls.append(path)
        if path == "/api/search/random":
            assert "takenAt" in kwargs["json"]["filter"]
        return []

    with patch.object(ImmichApi, "_request", request):
        with pytest.raises(ImmichApiError, match="No photos match"):
            await ImmichApi("http://immich.test", "key").snapshot({
                "source": "memories", "memory_window_days": 0, "fallback_to_all": True, "time_range": "1_month",
            }, 1, set())
    assert calls == ["/api/memories", "/api/search/random"]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_control_labels_persistence_reload_and_filtering(hass, asset, jpeg):
    entry = frame(hass)
    requests = []
    async def request(_api, method, path, **kwargs):
        if path == "/api/search/random":
            query = kwargs["json"]["filter"]
            requests.append(query)
            # Simulate Immich applying the capture-date bounds, including the boundary.
            assets = [{**asset, "id": "older", "localDateTime": "2010-01-01T12:00:00Z"}, asset]
            return [photo for photo in assets if "takenAt" not in query or
                    datetime.fromisoformat(query["takenAt"]["gte"]) <= datetime.fromisoformat(photo["localDateTime"]) <= datetime.fromisoformat(query["takenAt"]["lte"])]
        return jpeg

    with patch.object(ImmichApi, "_request", request), patch("custom_components.immich_frames.core.engine.datetime") as clock:
        clock.now.return_value = NOW
        clock.fromisoformat = datetime.fromisoformat
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_time_range")
        entity = er.async_get(hass).async_get(entity_id)
        assert entity.entity_category == EntityCategory.CONFIG
        assert entity.original_name == "Time range"
        assert hass.states.get(entity_id).state == "all_time"
        assert hass.states.get(entity_id).attributes["options"] == [choice[0] for choice in CHOICES]
        assert hass.data[DOMAIN][entry.entry_id].data.primary["id"] == "older"
        for option, label, start in CHOICES[1:] + CHOICES[:1]:
            assert async_translate_state(hass, option, "select", DOMAIN, "time_range", None) == label
            await set_value(hass, entry, "select", "time_range", option)
            assert entry.data["time_range"] == option
            assert hass.states.get(entity_id).state == option
            coordinator = hass.data[DOMAIN][entry.entry_id]
            assert len(coordinator.history) == 1
            assert coordinator.data.primary["id"] == (asset["id"] if start else "older")
            if start:
                assert requests[-1]["takenAt"]["gte"] == f"{start}T12:00:00+00:00"
            else:
                assert "takenAt" not in requests[-1]
        await set_value(hass, entry, "select", "time_range", "3_months")
        previous = hass.data[DOMAIN][entry.entry_id]
        await set_value(hass, entry, "select", "time_range", "3_months")
        assert hass.data[DOMAIN][entry.entry_id] is previous
        assert await hass.config_entries.async_unload(entry.entry_id)

    with patch.object(ImmichApi, "_request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "3_months"
        assert hass.data[DOMAIN][entry.entry_id].data.using_cache
        assert await hass.config_entries.async_unload(entry.entry_id)


def test_range_moves_forward_on_later_refreshes():
    first = _with_time_range({}, "1_month", NOW)
    later = _with_time_range({}, "1_month", NOW + timedelta(days=1))
    assert first["takenAt"]["gte"] == "2026-08-18T12:00:00+00:00"
    assert later["takenAt"]["gte"] == "2026-08-19T12:00:00+00:00"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("option,restores", [("all_time", True), ("1_month", False)])
async def test_old_cache_defaults_to_all_time(hass, asset, jpeg, option, restores):
    import json
    entry = frame(hass)
    async def request(_api, method, path, **kwargs):
        return [asset] if path == "/api/search/random" else jpeg

    with patch.object(ImmichApi, "_request", request):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        state_path = hass.data[DOMAIN][entry.entry_id].cache_path.with_suffix(".json")
        assert await hass.config_entries.async_unload(entry.entry_id)
    state = json.loads(state_path.read_text())
    state["photo_settings"].pop("time_range")
    state_path.write_text(json.dumps(state))
    hass.config_entries.async_update_entry(entry, data={**entry.data, "time_range": option})
    with patch.object(ImmichApi, "_request", side_effect=ImmichApiError("Offline")):
        assert await hass.config_entries.async_setup(entry.entry_id) is restores
        await hass.async_block_till_done()
        if restores:
            assert hass.data[DOMAIN][entry.entry_id].data.using_cache
            assert await hass.config_entries.async_unload(entry.entry_id)
        else:
            assert entry.entry_id not in hass.data[DOMAIN]
