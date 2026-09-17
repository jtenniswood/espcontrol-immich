from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError
from custom_components.immich_frames.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def source_step(hass, *, reuse=False):
    if reuse:
        entry = MockConfigEntry(domain=DOMAIN, title="First frame", data={
            "url": "http://immich.test", "api_key": "test-key",
        })
        entry.add_to_hass(hass)
    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection"):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        data = {"connection_id": entry.entry_id} if reuse else {"url": "http://immich.test", "api_key": "test-key"}
        return await hass.config_entries.flow.async_configure(result["flow_id"], data)


def options(result):
    return next(iter(result["data_schema"].schema.values())).config["options"]


@pytest.mark.parametrize("reuse", [False, True])
async def test_album_picker_uses_connected_account_and_stores_id(hass, reuse):
    result = await source_step(hass, reuse=reuse)
    calls = []

    async def request(api, method, path, **kwargs):
        calls.append((api.base_url, api.api_key, method, path, kwargs))
        return [{"id": "shared-id", "albumName": "Weekend", "shared": True},
                {"id": "owned-id", "albumName": "Family"}]

    with patch("custom_components.immich_frames.api.ImmichApi._request", request), patch(
        "custom_components.immich_frames.api.ImmichApi.close"
    ) as close:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Album"})
        assert result["step_id"] == "album"
        assert options(result) == [{"value": "owned-id", "label": "Family"}, {"value": "shared-id", "label": "Weekend"}]
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"album_id": "shared-id"})
        assert result["step_id"] == "display"
        assert close.await_count == 2
    assert calls == [("http://immich.test", "test-key", "GET", "/api/albums", {})] * 2
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], result["data_schema"]({}))
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"]["source"] == "album"
    assert result["data"]["album_id"] == "shared-id"


async def test_duplicate_and_unnamed_albums(hass):
    result = await source_step(hass)
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=[
        {"id": "b", "albumName": "Trips"}, {"id": "a", "albumName": "Trips"}, {"id": "empty", "albumName": ""},
    ]):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Album"})
    assert options(result) == [{"value": "a", "label": "Trips (a)"}, {"value": "b", "label": "Trips (b)"},
                               {"value": "empty", "label": "Untitled album"}]


@pytest.mark.parametrize("response,error", [
    ([], "no_albums"),
    (ImmichApiError("Unauthorized", 401), "album_access_denied"),
    (ImmichApiError("Forbidden", 403), "album_access_denied"),
    (ImmichApiError("Offline", 503), "albums_unavailable"),
    (OSError("Disconnected"), "albums_unavailable"),
    ({"unexpected": []}, "albums_unavailable"),
])
async def test_album_failures_allow_retry_and_other_sources(hass, response, error):
    result = await source_step(hass)
    with patch("custom_components.immich_frames.api.ImmichApi._request", side_effect=[response]), patch(
        "custom_components.immich_frames.api.ImmichApi.close"
    ) as close:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Album"})
        close.assert_awaited_once()
    assert result["step_id"] == "source"
    assert result["errors"] == {"base": error}
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=[{"id": "new", "albumName": "New album"}]):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Album"})
    assert result["step_id"] == "album"


async def test_no_albums_can_switch_to_all_photos(hass):
    result = await source_step(hass)
    with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=[]) as albums:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Album"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "All photos"})
        albums.assert_awaited_once()
    assert result["step_id"] == "display"


async def test_deleted_album_refreshes_picker(hass):
    result = await source_step(hass)
    with patch("custom_components.immich_frames.api.ImmichApi.albums", side_effect=[
        [{"id": "old", "albumName": "Old"}], [{"id": "new", "albumName": "New"}],
    ]):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Album"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"album_id": "old"})
    assert result["step_id"] == "album"
    assert result["errors"] == {"base": "album_unavailable"}
    assert options(result) == [{"value": "new", "label": "New"}]


@pytest.mark.parametrize("payload", [None, {}, [None], [{"id": "a"}], [{"id": "", "albumName": "A"}], [{"id": "a", "albumName": None}]])
async def test_invalid_album_list_has_controlled_error(payload):
    api = ImmichApi("http://immich.test", "key")
    api._request = AsyncMock(return_value=payload)
    with pytest.raises(ImmichApiError, match="invalid album list"):
        await api.albums()
