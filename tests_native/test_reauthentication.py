from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError
from custom_components.immich_frames.const import DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("cached", [False, True])
async def test_expired_key_recovers_same_frame(hass, asset, jpeg, cached):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hall",
        version=2,
        unique_id="frame-identity",
        data={
            "url": "http://immich.test",
            "api_key": "old-key",
            "mode": "pairs",
            "photo_fit": "show_full",
        },
    )
    entry.add_to_hass(hass)

    async def request(_api, method, path, **kwargs):
        return [asset] if "/search/" in path else jpeg

    with patch.object(ImmichApi, "_request", request):
        if cached:
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            before = hass.data[DOMAIN][entry.entry_id].data
    with patch.object(
        ImmichApi, "snapshot", side_effect=ImmichApiError("Expired", 401)
    ):
        if cached:
            await hass.data[DOMAIN][entry.entry_id].async_refresh()
            assert hass.data[DOMAIN][entry.entry_id].data.image == before.image
        else:
            assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    flow = next(
        f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN
    )
    assert flow["step_id"] == "reauth_confirm"
    registry = er.async_get(hass)
    identities = {
        (e.entity_id, e.unique_id)
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    with patch.object(
        ImmichApi, "validate_connection", side_effect=ImmichApiError("Bad key", 401)
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"api_key": "bad"}
        )
        assert result["errors"] == {"base": "invalid_auth"}
        assert entry.data["api_key"] == "old-key"
    with (
        patch.object(ImmichApi, "validate_connection"),
        patch.object(ImmichApi, "_request", request),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"api_key": "new-key"}
        )
        assert result["reason"] == "reauth_successful"
        await hass.async_block_till_done()
    assert entry.unique_id == "frame-identity"
    assert entry.data["mode"] == "pairs"
    assert entry.data["api_key"] == "new-key"
    if cached:
        assert identities == {
            (e.entity_id, e.unique_id)
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
    assert await hass.config_entries.async_unload(entry.entry_id)
