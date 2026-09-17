from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries

from .api import ImmichApi, ImmichApiError
from .const import (
    CONF_ALBUM_ID, CONF_API_KEY, CONF_FALLBACK, CONF_FRAME_NAME, CONF_INTERVAL, CONF_MEMORY_WINDOW,
    CONF_MODE, CONF_ORIENTATION, CONF_PAIRS_ONLY, CONF_PAIR_WINDOW, CONF_SMART_QUERY,
    CONF_SOURCE, CONF_URL, DEFAULT_INTERVAL, DOMAIN,
)


class ImmichFramesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            try:
                url = str(user_input[CONF_URL]).strip()
                if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
                    raise ValueError("invalid_url")
                api = ImmichApi(url, str(user_input[CONF_API_KEY]))
                try:
                    await api.validate_connection()
                finally:
                    await api.close()
            except ValueError:
                errors["base"] = "invalid_url"
            except ImmichApiError as exc:
                errors["base"] = "invalid_auth" if exc.status in (401, 403) else "cannot_connect"
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                self._data = {CONF_URL: url, CONF_API_KEY: str(user_input[CONF_API_KEY])}
                return await self.async_step_source()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_URL): str,
            vol.Required(CONF_API_KEY): str,
        }), errors=errors)

    async def async_step_source(self, user_input: dict[str, Any] | None = None):
        if user_input:
            source = {
                "All photos": "all",
                "Album by ID": "album",
                "On This Day memories": "memories",
                "Smart Search": "smart",
            }.get(user_input[CONF_SOURCE], user_input[CONF_SOURCE])
            self._data[CONF_SOURCE] = source
            if source == "album":
                return await self.async_step_album()
            if source == "memories":
                return await self.async_step_memories()
            if source == "smart":
                return await self.async_step_smart()
            return await self.async_step_display()
        return self.async_show_form(step_id="source", data_schema=vol.Schema({
            vol.Required(CONF_SOURCE, default="All photos"): vol.In(["All photos", "Album by ID", "On This Day memories", "Smart Search"]),
        }))

    async def async_step_album(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            album_id = str(user_input.get(CONF_ALBUM_ID, "")).strip()
            if not album_id:
                errors["base"] = "album_required"
            else:
                self._data[CONF_ALBUM_ID] = album_id
                return await self.async_step_display()
        return self.async_show_form(step_id="album", data_schema=vol.Schema({
            vol.Required(CONF_ALBUM_ID): str,
        }), errors=errors)

    async def async_step_memories(self, user_input: dict[str, Any] | None = None):
        if user_input:
            self._data.update(user_input)
            return await self.async_step_display()
        return self.async_show_form(step_id="memories", data_schema=vol.Schema({
            vol.Required(CONF_MEMORY_WINDOW, default=2): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_FALLBACK, default=False): bool,
        }))

    async def async_step_smart(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            if not str(user_input.get(CONF_SMART_QUERY, "")).strip():
                errors["base"] = "smart_query_required"
            else:
                self._data.update(user_input)
                return await self.async_step_display()
        return self.async_show_form(step_id="smart", data_schema=vol.Schema({
            vol.Required(CONF_SMART_QUERY): str,
        }), errors=errors)

    async def async_step_display(self, user_input: dict[str, Any] | None = None):
        if user_input:
            user_input[CONF_MODE] = {
                "Single image": "single",
                "Matching portrait pairs": "pairs",
            }.get(user_input[CONF_MODE], user_input[CONF_MODE])
            user_input[CONF_ORIENTATION] = {
                "Any orientation": "any",
                "Portrait photos only": "portrait",
                "Landscape photos only": "landscape",
                "Square photos only": "square",
            }.get(user_input[CONF_ORIENTATION], user_input[CONF_ORIENTATION])
            self._data.update(user_input)
            await self.async_set_unique_id(f"{self._data[CONF_URL]}|{self._data[CONF_FRAME_NAME].strip()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._data[CONF_FRAME_NAME].strip(), data=self._data)
        return self.async_show_form(step_id="display", data_schema=vol.Schema({
            vol.Required(CONF_FRAME_NAME, default="Immich Frame"): str,
            vol.Required(CONF_MODE, default="Single image"): vol.In(["Single image", "Matching portrait pairs"]),
            vol.Required(CONF_ORIENTATION, default="Any orientation"): vol.In(["Any orientation", "Portrait photos only", "Landscape photos only", "Square photos only"]),
            vol.Required(CONF_PAIR_WINDOW, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_PAIRS_ONLY, default=False): bool,
            vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=10, max=86400)),
        }))
