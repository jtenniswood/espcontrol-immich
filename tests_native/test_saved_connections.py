from unittest.mock import patch

import pytest
from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApiError
from custom_components.immich_frames.const import DOMAIN
from tests_native.flow_helpers import finish_settings

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def saved_frame(hass, *, title="Immich Frame", url="http://immich.test", key="saved-secret"):
    entry = MockConfigEntry(domain=DOMAIN, title=title, unique_id=f"{url}|{title}", data={
        "url": url, "api_key": key, "frame_name": title, "source": "album",
        "album_id": "old-album", "mode": "pairs", "interval": 100,
    })
    entry.add_to_hass(hass)
    return entry


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


def choices(form):
    return next(iter(form["data_schema"].schema.values())).container


async def test_first_frame_still_asks_for_credentials(hass):
    result = await start(hass)
    assert result["step_id"] == "user"
    assert set(result["data_schema"].schema) == {"url", "api_key"}


async def test_saved_connection_creates_independent_second_frame(hass):
    original = saved_frame(hass)
    original_data = dict(original.data)
    result = await start(hass)
    assert result["step_id"] == "connection"
    assert original.entry_id in choices(result)
    assert "http://immich.test" in choices(result)[original.entry_id]
    assert "saved-secret" not in repr(result)
    used = []

    async def validate(api):
        used.append((api.base_url, api.api_key))

    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection", validate), patch(
        "custom_components.immich_frames.api.ImmichApi.close"
    ) as close:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"connection_id": original.entry_id})
        close.assert_awaited_once()
    assert used == [("http://immich.test", "saved-secret")]
    assert result["step_id"] == "source"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source": "All photos"})
    assert result["step_id"] == "display"
    defaults = result["data_schema"]({})
    assert defaults["frame_name"] == "Immich Frame 2"
    with patch("custom_components.immich_frames.async_setup_entry", return_value=True):
        result = await finish_settings(hass.config_entries.flow, result)
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"]["url"] == original.data["url"]
    assert result["data"]["api_key"] == original.data["api_key"]
    assert result["data"]["source"] == "all"
    assert result["data"]["mode"] == "single"
    assert result["data"]["interval"] == 30
    assert "album_id" not in result["data"]
    assert "connection_id" not in result["data"]
    assert dict(original.data) == original_data
    await hass.config_entries.async_remove(original.entry_id)
    assert result["result"].data["api_key"] == "saved-secret"


async def test_connections_deduplicate_same_credentials_but_keep_other_accounts(hass):
    first = saved_frame(hass)
    duplicate = saved_frame(hass, title="Kitchen", url="http://immich.test/")
    account = saved_frame(hass, title="Other account", key="another-secret")
    server = saved_frame(hass, title="Second server", url="http://other.test")
    options = choices(await start(hass))
    assert set(options) == {first.entry_id, account.entry_id, server.entry_id, "new"}
    assert duplicate.entry_id not in options
    assert "Other account" in options[account.entry_id]
    assert "saved-secret" not in repr(options)
    assert "another-secret" not in repr(options)


async def test_choose_new_connection_does_not_prefill_saved_key(hass):
    saved_frame(hass)
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"connection_id": "new"})
    assert result["step_id"] == "new_connection"
    assert "saved-secret" not in repr(result)
    used = []

    async def validate(api):
        used.append((api.base_url, api.api_key))

    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection", validate):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "url": "http://another.test", "api_key": "new-secret",
        })
    assert result["step_id"] == "source"
    assert used == [("http://another.test", "new-secret")]


@pytest.mark.parametrize("status,error", [(401, "invalid_auth"), (403, "invalid_auth"), (503, "cannot_connect")])
async def test_saved_connection_failure_stays_in_picker(hass, status, error):
    original = saved_frame(hass)
    result = await start(hass)
    with patch("custom_components.immich_frames.api.ImmichApi.validate_connection", side_effect=ImmichApiError("Error", status)), patch(
        "custom_components.immich_frames.api.ImmichApi.close"
    ) as close:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"connection_id": original.entry_id})
        close.assert_awaited_once()
    assert result["step_id"] == "connection"
    assert result["errors"] == {"base": error}
    assert "saved-secret" not in repr(result)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"connection_id": "new"})
    assert result["step_id"] == "new_connection"


async def test_deleted_saved_connection_is_handled(hass):
    original = saved_frame(hass)
    result = await start(hass)
    await hass.config_entries.async_remove(original.entry_id)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"connection_id": original.entry_id})
    assert result["step_id"] == "connection"
    assert result["errors"] == {"base": "connection_unavailable"}
    assert set(choices(result)) == {"new"}
