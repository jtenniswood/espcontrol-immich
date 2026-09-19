"""Keep the entity-row thumbnail in sync with the full frame image."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
from urllib.parse import quote

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import FrameSnapshot
from custom_components.immich_frames.const import DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("action", ["automatic", "next", "refresh"])
async def test_thumbnail_follows_frame_and_previous(hass, hass_client_no_auth, asset, action):
    """A new frame changes the public thumbnail URL and serves matching bytes."""
    snapshots = []
    created_at = datetime(2026, 9, 18, 12, 0, 0, 100000, tzinfo=timezone.utc)
    for index, colour in enumerate(("red", "blue")):
        output = BytesIO()
        Image.new("RGB", (1280, 800), colour).save(output, "JPEG")
        photos = (asset, {**asset, "id": "portrait-b"}) if index == 0 else (
            {**asset, "id": "photo with /?#"},
        )
        snapshots.append(FrameSnapshot(
            output.getvalue(), index + 1, photos, "pair" if index == 0 else "single",
            created_at + timedelta(microseconds=index), 1,
        ))

    entry = MockConfigEntry(domain=DOMAIN, title="Frame", data={
        "url": "http://immich.test/library/", "api_key": "test-key",
    })
    entry.add_to_hass(hass)
    with patch("custom_components.immich_frames.api.ImmichApi.snapshot", side_effect=snapshots):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        client = await hass_client_no_auth()
        coordinator = entry.runtime_data

        async def thumbnail_url(snapshot):
            state = hass.states.get("image.frame_image")
            assert state.state == snapshot.created_at.isoformat()
            assert state.attributes["open_in_immich"] == (
                f"http://immich.test/library/photos/{quote(snapshot.primary['id'], safe='')}"
            )
            if snapshot.secondary:
                assert state.attributes["open_second_photo_in_immich"] == (
                    f"http://immich.test/library/photos/{snapshot.secondary['id']}"
                )
            else:
                assert "open_second_photo_in_immich" not in state.attributes
            assert "test-key" not in str(state.attributes)
            url = state.attributes["entity_picture"]
            response = await client.get(url)
            assert response.status == 200
            assert response.content_type == "image/jpeg"
            assert await response.read() == snapshot.image
            return url

        first_url = await thumbnail_url(snapshots[0])
        if action == "automatic":
            await coordinator.async_refresh()
        else:
            await hass.services.async_call("button", "press", {
                "entity_id": f"button.frame_{action}",
            }, blocking=True)
        second_url = await thumbnail_url(snapshots[1])
        assert second_url != first_url

        # Connection/status changes keep the cached frame and its thumbnail URL.
        coordinator.async_set_updated_data(replace(
            snapshots[1], connected=False, using_cache=True, status="upstream_unavailable",
        ))
        assert await thumbnail_url(snapshots[1]) == second_url

        await hass.services.async_call("button", "press", {
            "entity_id": "button.frame_previous",
        }, blocking=True)
        assert await thumbnail_url(snapshots[0]) == first_url
        assert await hass.config_entries.async_unload(entry.entry_id)
