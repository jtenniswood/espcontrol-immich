"""Deterministic clock and cancellation rules for the shared runtime."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from custom_components.immich_frames.core.cache import SnapshotStore
from custom_components.immich_frames.core.models import FrameSnapshot
from custom_components.immich_frames.core.session import FrameSession
from custom_components.immich_frames.core.settings import FrameSettings


def slide(now, generation=1):
    raw = BytesIO()
    Image.new("RGB", (1280, 800), "blue").save(raw, "JPEG")
    return FrameSnapshot(
        raw.getvalue(),
        generation,
        ({"id": "a", "captured": now.isoformat()},),
        "single",
        now,
        1,
    )


async def test_clock_controls_memories_and_offline_cache_expiry(tmp_path):
    now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    settings = FrameSettings(source="memories")
    produce = AsyncMock(return_value=slide(now))
    store = SnapshotStore(tmp_path / "frame.json")
    session = FrameSession(settings, "account", store, produce, clock=lambda: now)
    await session.refresh()
    assert produce.call_args.kwargs["now"] == now
    assert produce.call_args.kwargs["today"] == now.astimezone().date()
    restored = FrameSession(settings, "account", store, produce, clock=lambda: now)
    assert await restored.restore() is not None
    now += timedelta(days=1)
    assert await restored.restore() is None


async def test_connection_change_discards_inflight_result_and_old_cache(tmp_path):
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    began, release = asyncio.Event(), asyncio.Event()

    async def produce(*args, **kwargs):
        began.set()
        await release.wait()
        return slide(now)

    session = FrameSession(
        FrameSettings(), "old", SnapshotStore(tmp_path / "frame.json"), produce
    )
    pending = asyncio.create_task(session.refresh())
    await began.wait()
    session.configure(FrameSettings(), "new")
    release.set()
    assert await pending is None
    assert not session.store.path.exists()


async def test_cancelled_refresh_cannot_publish_late_completion(tmp_path):
    began = asyncio.Event()

    async def produce(*args, **kwargs):
        began.set()
        await asyncio.Event().wait()

    session = FrameSession(
        FrameSettings(), "account", SnapshotStore(tmp_path / "frame.json"), produce
    )
    pending = asyncio.create_task(session.refresh())
    await began.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert session.current is None
    assert not session.store.path.exists()
    session.produce = AsyncMock(return_value=slide(datetime.now(timezone.utc)))
    assert (await session.refresh()).generation == 1


async def test_timer_edit_preserves_pause_history_and_cache(tmp_path):
    settings = FrameSettings()
    session = FrameSession(
        settings,
        "account",
        SnapshotStore(tmp_path / "frame.json"),
        AsyncMock(return_value=slide(datetime.now(timezone.utc))),
    )
    await session.refresh()
    cached = session.store.path.read_bytes()
    session.pause()
    session.configure(replace(settings, interval=90), "account")
    assert session.paused
    assert len(session.history) == 1
    assert session.store.path.read_bytes() == cached
