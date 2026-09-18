from unittest.mock import patch

import pytest
from homeassistant import config_entries

from custom_components.immich_frames.api import ImmichApiError
from custom_components.immich_frames.const import DOMAIN
from tests_native.flow_helpers import finish_settings


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("status", [None, 401, 403])
async def test_connection_checks_authenticated_search(hass, status):
    async def request(_api, method, path, **kwargs):
        if path == "/api/server/version":
            return {"major": 3, "minor": 2, "patch": 0}
        assert path == "/api/search/metadata"
        assert kwargs["json"]["size"] == 1
        if status:
            raise ImmichApiError("Access denied", status)
        return {"assets": {"items": []}}

    with patch("custom_components.immich_frames.api.ImmichApi._request", request), patch(
        "custom_components.immich_frames.api.ImmichApi.close"
    ) as close:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER},
            data={"url": "http://immich.test", "api_key": "test-key"},
        )
        close.assert_awaited_once()
    if status:
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "invalid_auth"}
    else:
        assert result["step_id"] == "source"
        with patch("custom_components.immich_frames.api.ImmichApi.albums", return_value=[{"id": "album-id", "albumName": "Holidays"}]):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "Albums"})
            assert result["step_id"] == "album"
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"album_ids": ["album-id"]})
        assert result["step_id"] == "display"
        with patch("custom_components.immich_frames.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {
                "frame_name": "Test Frame", "mode": "Single image",
            })
            result = await finish_settings(hass.config_entries.flow, result)
            await hass.async_block_till_done()
        assert result["type"] == "create_entry"
        assert result["data"]["source"] == "album"
        assert result["data"]["album_ids"] == ["album-id"]
