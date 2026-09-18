from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FrameSnapshot, ImmichApi, ImmichApiError
from .const import CONF_INTERVAL, DOMAIN, OUTPUT_SIZE

LOGGER = logging.getLogger(__name__)


class FrameCoordinator(DataUpdateCoordinator[FrameSnapshot]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.options = dict(entry.data)
        self.api = ImmichApi(self.options["url"], self.options["api_key"])
        self.paused = False
        self.metadata_role = "primary"
        self.generation = 0
        self.history: list[FrameSnapshot] = []
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
        image_path = self.cache_path.with_suffix(".jpg")
        state_path = self.cache_path.with_suffix(".json")
        if not image_path.exists() or not state_path.exists():
            return
        try:
            state = json.loads(state_path.read_text())
            if not isinstance(state, dict) or not isinstance(state.get("photos"), list):
                return
            # Validate the JPEG itself, including caches written by older versions.
            image_data = image_path.read_bytes()
            with Image.open(BytesIO(image_data)) as image:
                if image.size != OUTPUT_SIZE:
                    return
            photos = tuple(state["photos"])
            if not photos or any(not isinstance(photo, dict) or not photo.get("id") for photo in photos):
                return
            self.generation = int(state["generation"])
            self.data = FrameSnapshot(image_data, self.generation, photos, state.get("layout", "single"), datetime.fromisoformat(state["created_at"]), int(state.get("matching_assets", 0)), connected=False, using_cache=True, status="cached")
            self.history = [self.data]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return

    async def _async_update_data(self) -> FrameSnapshot:
        if self.paused and self.data:
            return self.data
        try:
            snapshot = await self.api.snapshot(self.options, self.generation + 1, {photo["id"] for item in self.history[-10:] for photo in item.photos})
        except ImmichApiError as exc:
            if self.data:
                status = "invalid_api_key" if exc.status in (401, 403) else "upstream_unavailable"
                return replace(self.data, connected=False, using_cache=True, status=status)
            raise UpdateFailed(str(exc)) from exc
        self.generation = snapshot.generation
        self.history.append(snapshot)
        self.history = self.history[-20:]
        await self._save_cache(snapshot)
        return snapshot

    async def _save_cache(self, snapshot: FrameSnapshot) -> None:
        try:
            await self.hass.async_add_executor_job(self._write_cache, snapshot)
        except OSError:
            LOGGER.warning("Could not save the frame cache", exc_info=True)

    def _write_cache(self, snapshot: FrameSnapshot) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "generation": snapshot.generation, "layout": snapshot.layout,
            "created_at": snapshot.created_at.isoformat(), "matching_assets": snapshot.matching_assets,
            "photos": [{key: value for key, value in photo.items() if key != "capture_dt"} for photo in snapshot.photos],
        }
        self.cache_path.with_suffix(".jpg").write_bytes(snapshot.image)
        self.cache_path.with_suffix(".json").write_text(json.dumps(state))

    async def async_refresh_now(self) -> None:
        await self.async_refresh()

    async def async_next(self) -> None:
        self.paused = False
        await self.async_refresh()

    async def async_previous(self) -> None:
        if len(self.history) > 1:
            self.history.pop()
            self.async_set_updated_data(self.history[-1])

    async def async_clear_cache(self) -> None:
        await self.hass.async_add_executor_job(self._clear_cache)

    def _clear_cache(self) -> None:
        self.cache_path.with_suffix(".jpg").unlink(missing_ok=True)
        self.cache_path.with_suffix(".json").unlink(missing_ok=True)

    async def async_close(self) -> None:
        await self.api.close()
