"""One frame's playback and publication rules, independent of its host."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .cache import SnapshotStore, finish_write, signature
from .errors import ImmichApiError, NoMatchingPhotos
from .history import SlideHistory
from .models import FrameSnapshot
from .settings import FrameSettings

LOGGER = logging.getLogger(__name__)


class FrameSession:
    """Serialize refreshes and reject results superseded by settings or navigation.

    Hosts own scheduling and connection lifetimes. A session owns all displayed
    state. The settings/connection revision changes synchronously, so an old
    download cannot publish while a host is waiting for a reload.
    """

    def __init__(
        self,
        settings: FrameSettings,
        connection: str,
        store: SnapshotStore,
        produce: Callable[..., Awaitable[FrameSnapshot]],
        *,
        clock=None,
    ):
        self.settings = settings
        self.connection = connection
        self.store = store
        self.produce = produce
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.current: FrameSnapshot | None = None
        self.history = SlideHistory()
        self.generation = 0
        self.paused = False
        self.last_error: ImmichApiError | None = None
        self._revision = 0
        self._lock = asyncio.Lock()
        self._closed = False

    def configure(self, settings: FrameSettings, connection: str) -> None:
        today = self.clock().astimezone().date()
        changed = signature(settings, connection, today=today) != signature(
            self.settings, self.connection, today=today
        )
        self.settings, self.connection = settings, connection
        if changed:
            self._revision += 1
            self.current = None
            self.history = SlideHistory()
            self.paused = False
            self.last_error = None

    def invalidate(self) -> None:
        """Retire in-flight work before a host reload/unload."""
        self._revision += 1
        self._closed = True

    async def restore(self) -> FrameSnapshot | None:
        revision = self._revision
        now = self.clock()
        result = await asyncio.to_thread(
            self.store.read,
            self.settings,
            self.connection,
            now=now,
            today=now.astimezone().date(),
        )
        if not self._closed and revision == self._revision:
            self.current = result
            self.generation = result.generation if result else 0
            self.history = SlideHistory([result] if result else [])
        return self.current

    def pause(self) -> None:
        self.paused = True
        self._revision += 1

    def resume(self) -> None:
        self.paused = False

    def previous(self) -> FrameSnapshot | None:
        if len(self.history) > 1:
            self._revision += 1
            self.current = self.history.previous()
        return self.current

    async def next(self) -> FrameSnapshot | None:
        self.resume()
        return await self.refresh()

    async def refresh(self, *, force: bool = False) -> FrameSnapshot | None:
        # Capture before acquiring the lock: queued commands belong to the
        # revision at which they were requested, not whichever happens to win.
        revision = self._revision
        async with self._lock:
            if self._closed or revision != self._revision:
                return self.current
            if self.paused and self.current and not force:
                return self.current
            settings, connection = self.settings, self.connection
            self.last_error = None
            now = self.clock()
            today = now.astimezone().date()
            try:
                result = await self.produce(
                    settings,
                    self.generation + 1,
                    self.history.recent_ids,
                    now=now,
                    today=today,
                )
            except ImmichApiError as exc:
                if self._closed or revision != self._revision:
                    return self.current
                self.last_error = exc
                if self.current is None:
                    raise
                status = (
                    "no_matching_photos"
                    if isinstance(exc, NoMatchingPhotos)
                    else "invalid_api_key"
                    if exc.status in (401, 403)
                    else "upstream_unavailable"
                )
                self.current = replace(
                    self.current,
                    connected=isinstance(exc, NoMatchingPhotos),
                    using_cache=True,
                    status=status,
                )
                return self.current
            if self._closed or revision != self._revision:
                return self.current
            try:
                await finish_write(
                    asyncio.to_thread(
                        self.store.write, result, settings, connection, today=today
                    )
                )
            except OSError:
                LOGGER.warning("Could not save the frame cache", exc_info=True)
            # Settings or Previous can change while the atomic write finishes.
            # Its signature prevents restoration under a different source.
            if self._closed or revision != self._revision:
                return self.current
            self.generation = result.generation
            self.current = result
            self.history.append(result)
            return result

    async def clear_cache(self) -> None:
        # Finish any accepted write first, so clear cannot be undone by it.
        async with self._lock:
            await asyncio.to_thread(self.store.clear)

    async def close(self) -> None:
        self.invalidate()
        async with self._lock:
            pass
