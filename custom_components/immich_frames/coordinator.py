from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any


from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FrameSnapshot, ImmichApi, ImmichApiError, NoMatchingPhotos
from .core.cache import SnapshotStore, connection_identity, finish_write
from .core.settings import FrameSettings
from .core.history import SlideHistory
from .const import CONF_INTERVAL, CONF_PHOTO_FIT, photo_fit

LOGGER = logging.getLogger(__name__)


class FrameCoordinator(DataUpdateCoordinator[FrameSnapshot]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.options = {**entry.data, **FrameSettings.from_options(dict(entry.data)).options()}
        self.api = ImmichApi(self.options["url"], self.options["api_key"])
        self.paused = False
        self.generation = 0
        self.history = SlideHistory()
        self.cache_path = Path(hass.config.path(".storage", f"immich_frames_{entry.entry_id}"))
        super().__init__(
            hass,
            logger=LOGGER,
            name=f"EspControl Immich Companion {entry.title}",
            update_interval=timedelta(seconds=int(self.options.get(CONF_INTERVAL, 30))),
            config_entry=entry,
        )

    async def _async_setup(self) -> None:
        await self.hass.async_add_executor_job(self._load_cache)

    def _load_cache(self) -> None:
        self.data = self.store.read(self.options, self.connection_identity)
        if self.data:
            self.generation = self.data.generation
            self.history = SlideHistory([self.data])

    @property
    def store(self):
        return SnapshotStore(self.cache_path.with_suffix(".json"))

    @property
    def connection_identity(self):
        return connection_identity(self.options["url"], self.options["api_key"])

    async def _async_update_data(self) -> FrameSnapshot:
        if self.paused and self.data:
            return self.data
        try:
            snapshot = await self.api.snapshot(self.options, self.generation + 1, self.history.recent_ids)
        except ImmichApiError as exc:
            if self.data:
                status = "no_matching_photos" if isinstance(exc, NoMatchingPhotos) else "invalid_api_key" if exc.status in (401, 403) else "upstream_unavailable"
                return replace(self.data, connected=isinstance(exc, NoMatchingPhotos), using_cache=True, status=status)
            raise UpdateFailed(str(exc)) from exc
        self.generation = snapshot.generation
        self.history.append(snapshot)
        await self._save_cache(snapshot)
        return snapshot

    async def _save_cache(self, snapshot: FrameSnapshot) -> None:
        try:
            await finish_write(self.hass.async_add_executor_job(self._write_cache, snapshot))
        except OSError:
            LOGGER.warning("Could not save the frame cache", exc_info=True)

    def _write_cache(self, snapshot: FrameSnapshot) -> None:
        self.store.write(snapshot, self.options, self.connection_identity)

    @callback
    def async_update_settings(self, changes: dict[str, Any]) -> None:
        """Persist device settings together, then rebuild with compatible cache only."""
        if all(self.entry.data.get(key) == value for key, value in changes.items()):
            return
        # Preserve the displayed fit when changing mode on a legacy frame whose
        # fit was previously inferred from its mode rather than explicitly saved.
        data = {**self.entry.data, CONF_PHOTO_FIT: photo_fit(self.entry.data), **changes}
        FrameSettings.from_options(data)
        if self.hass.config_entries.async_update_entry(self.entry, data=data):
            self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    async def async_refresh_now(self) -> None:
        await self.async_refresh()

    async def async_next(self) -> None:
        self.paused = False
        await self.async_refresh()

    async def async_previous(self) -> None:
        if len(self.history) > 1:
            self.async_set_updated_data(self.history.previous())

    async def async_clear_cache(self) -> None:
        await self.hass.async_add_executor_job(self._clear_cache)

    def _clear_cache(self) -> None:
        self.store.clear()

    async def async_close(self) -> None:
        await self.api.close()
