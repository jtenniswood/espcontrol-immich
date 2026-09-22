"""The same user scenarios run through native and container host adapters."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.immich_frames.api import ImmichApi, ImmichApiError, FrameSnapshot
from custom_components.immich_frames.const import DOMAIN
from immich_frames.app import FrameApp
from immich_frames.models import FrameConfig

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)


class Producer:
    def __init__(self):
        self.offline = False
        self.began = asyncio.Event()
        self.release = asyncio.Event()
        self.delay = False

    async def __call__(self, settings, generation, recent_ids, **clock):
        if self.delay:
            self.began.set()
            await self.release.wait()
        if self.offline:
            raise ImmichApiError("Offline")
        source = settings.album_ids[0]
        raw = BytesIO()
        Image.new(
            "RGB", settings.output_size, "red" if generation % 2 else "blue"
        ).save(raw, "JPEG")
        photos = tuple(
            {
                "id": f"{source}-{generation}-{side}",
                "captured": NOW.isoformat(),
                "orientation": "portrait",
                "people": [side],
            }
            for side in ("left", "right")
        )
        return FrameSnapshot(
            raw.getvalue(), generation, photos, "side_by_side", NOW, 10
        )


class Host:
    def __init__(self, kind, hass, root, producer):
        self.kind, self.hass, self.root, self.producer = kind, hass, root, producer
        self.entry = None
        self.frame = FrameConfig(
            "frame", "Hall", source="album", album_ids=["old"], mode="pairs"
        )
        self.app = None

    async def start(self):
        if self.kind == "native":
            if self.entry is None:
                self.entry = MockConfigEntry(
                    domain=DOMAIN,
                    title="Hall",
                    version=2,
                    data={
                        "url": "http://immich.test",
                        "api_key": "key",
                        **self.frame.settings().options(),
                    },
                )
                self.entry.add_to_hass(self.hass)
            assert await self.hass.config_entries.async_setup(self.entry.entry_id)
            await self.hass.async_block_till_done()
        else:
            self.app = FrameApp({}, self.root)
            self.app.storage.save_connection(
                "default", "Home", "http://immich.test", "key"
            )
            self.app.clients["default"] = Mock(close=AsyncMock())
            self.app.storage.save_frame(self.frame)
            await self.session.restore()
            await self.app.refresh_frame(self.frame)

    @property
    def coordinator(self):
        return self.hass.data[DOMAIN][self.entry.entry_id]

    @property
    def session(self):
        return (
            self.coordinator.session
            if self.kind == "native"
            else self.app._session_for(self.frame)
        )

    @property
    def current(self):
        return self.coordinator.data if self.kind == "native" else self.session.current

    async def refresh(self):
        if self.kind == "native":
            await self.coordinator.async_refresh()
        else:
            await self.app.refresh_frame(self.frame)

    async def next(self):
        if self.kind == "native":
            await self.coordinator.async_next()
        else:
            await self.app.frame_command(
                Mock(match_info={"frame_id": "frame", "command": "next"})
            )

    async def previous(self):
        if self.kind == "native":
            await self.coordinator.async_previous()
        else:
            await self.app.frame_command(
                Mock(match_info={"frame_id": "frame", "command": "previous"})
            )

    def change_source(self):
        if self.kind == "native":
            self.coordinator.async_update_settings({"album_ids": ["new"]})
        else:
            self.frame = replace(self.frame, album_ids=["new"])
            self.app.storage.save_frame(self.frame)
            self.app.start_frame(self.frame)

    async def settled(self):
        if self.kind == "native":
            await self.hass.async_block_till_done()
        else:
            for _ in range(200):
                if self.current and self.current.primary["id"].startswith("new"):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("Replacement frame did not publish")

    async def close(self):
        if self.kind == "native":
            await self.hass.config_entries.async_unload(self.entry.entry_id)
        else:
            await self.app.shutdown(None)


@pytest.fixture(params=["native", "container"])
async def host(request, hass, tmp_path, monkeypatch, enable_custom_integrations):
    producer = Producer()

    async def native(_self, *args, **kwargs):
        return await producer(*args, **kwargs)

    async def container(_client, *args, **kwargs):
        return await producer(*args, **kwargs)

    monkeypatch.setattr(ImmichApi, "snapshot", native)
    monkeypatch.setattr("immich_frames.app.snapshot", container)
    host = Host(request.param, hass, tmp_path, producer)
    await host.start()
    yield host
    producer.release.set()
    await host.close()


async def test_pause_next_previous_and_offline_restart(host):
    first = host.current
    host.session.pause()
    await host.refresh()
    assert host.current.image == first.image
    await host.next()
    second = host.current
    assert not host.session.paused
    assert second.generation == first.generation + 1
    assert second.image != first.image
    await host.previous()
    assert host.current.image == first.image
    assert host.current.photos == first.photos
    if host.kind == "native":
        state = host.hass.states.get("image.hall_image")
        assert state.attributes["open_in_immich"].endswith(first.primary["id"])
        assert state.attributes["open_second_photo_in_immich"].endswith(
            first.secondary["id"]
        )
    host.producer.offline = True
    await host.close()
    await host.start()
    # Preserve the existing restart contract: last generated slide, not history.
    assert host.current.image == second.image
    assert host.current.photos == second.photos
    assert host.current.using_cache


async def test_source_change_beats_inflight_refresh(host):
    host.producer.delay = True
    old = asyncio.create_task(host.refresh())
    await host.producer.began.wait()
    host.change_source()
    host.producer.delay = False
    host.producer.release.set()
    await old
    await host.settled()
    assert host.current.primary["id"].startswith("new")
    assert all(item.primary["id"].startswith("new") for item in host.session.history)
    restored = host.session.store.read(host.session.settings, host.session.connection)
    assert restored.photos == host.current.photos


async def test_previous_beats_inflight_refresh(host):
    first = host.current
    await host.next()
    host.producer.delay = True
    pending = asyncio.create_task(host.refresh())
    await host.producer.began.wait()
    await host.previous()
    host.producer.release.set()
    await pending
    assert host.current.image == first.image
    assert host.current.photos == first.photos
