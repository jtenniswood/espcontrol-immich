from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import logging

from .api import FrameSnapshot, ImmichApi, ImmichApiError
from .core.cache import SnapshotStore, connection_identity
from .core.session import FrameSession
from .core.settings import FrameSettings, SETTING_BY_KEY
from .const import CONF_PHOTO_FIT, photo_fit

LOGGER = logging.getLogger(__name__)


class FrameCoordinator(DataUpdateCoordinator[FrameSnapshot]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.api = ImmichApi(entry.data["url"], entry.data["api_key"])
        self.cache_path = Path(
            hass.config.path(".storage", f"immich_frames_{entry.entry_id}")
        )
        settings = FrameSettings.from_options(dict(entry.data))

        async def produce(settings, generation, recent_ids, **clock):
            return await self.api.snapshot(settings, generation, recent_ids, **clock)

        self.session = FrameSession(
            settings,
            connection_identity(self.api.base_url, self.api.api_key),
            SnapshotStore(self.cache_path.with_suffix(".json")),
            produce,
        )
        super().__init__(
            hass,
            logger=LOGGER,
            name=f"EspControl Immich Companion {entry.title}",
            update_interval=timedelta(seconds=settings.interval),
            config_entry=entry,
        )

    @property
    def options(self):
        """Read-only compatibility view for host entities and diagnostics."""
        return {**self.entry.data, **self.session.settings.options()}

    @property
    def history(self):
        return self.session.history

    @property
    def paused(self):
        return self.session.paused

    @paused.setter
    def paused(self, value):
        self.session.pause() if value else self.session.resume()

    @property
    def store(self):
        return self.session.store

    @property
    def connection_identity(self):
        return self.session.connection

    async def _async_setup(self) -> None:
        self.data = await self.session.restore()

    async def _async_update_data(self) -> FrameSnapshot:
        try:
            result = await self.session.refresh()
        except ImmichApiError as exc:
            if exc.status in (401, 403):
                raise ConfigEntryAuthFailed(str(exc)) from exc
            raise UpdateFailed(str(exc)) from exc
        if self.session.last_error and self.session.last_error.status in (401, 403):
            # Keep the compatible cached picture visible while HA prompts for a key.
            self.entry.async_start_reauth(self.hass)
        if result is None:
            # A settings save invalidated this coordinator while it was awaiting I/O.
            raise UpdateFailed("Frame settings changed; waiting for reload")
        return result

    @callback
    def async_update_settings(self, changes: dict[str, Any]) -> None:
        data = {
            **self.entry.data,
            CONF_PHOTO_FIT: photo_fit(self.entry.data),
            **changes,
        }
        settings = FrameSettings.from_options(data)
        if all(self.entry.data.get(key) == value for key, value in changes.items()):
            return
        timer_only = all(
            key in SETTING_BY_KEY and SETTING_BY_KEY[key].effect == "timer"
            for key in changes
        )
        self.session.configure(settings, self.connection_identity)
        if self.hass.config_entries.async_update_entry(self.entry, data=data):
            if timer_only:
                self.update_interval = timedelta(seconds=settings.interval)
            else:
                self.hass.config_entries.async_schedule_reload(self.entry.entry_id)

    async def async_next(self) -> None:
        self.session.resume()
        await self.async_refresh()

    async def async_previous(self) -> None:
        if (result := self.session.previous()) is not None:
            self.async_set_updated_data(result)

    async def async_clear_cache(self) -> None:
        await self.session.clear_cache()

    async def async_close(self) -> None:
        await self.session.close()
        await self.api.close()
