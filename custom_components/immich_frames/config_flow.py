from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .api import ImmichApi, ImmichApiError
from .const import (
    CONF_ALBUM_ID, CONF_API_KEY, CONF_FALLBACK, CONF_FRAME_NAME, CONF_INTERVAL, CONF_MEMORY_WINDOW,
    CONF_MODE, CONF_ORIENTATION, CONF_PAIRS_ONLY, CONF_PAIR_WINDOW, CONF_SMART_QUERY,
    CONF_SOURCE, CONF_URL, DEFAULT_INTERVAL, DOMAIN,
)


class ImmichFramesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is None and self._saved_connections():
            return await self.async_step_connection()
        return await self._async_connection_form("user", user_input)

    def _saved_connections(self) -> dict[str, config_entries.ConfigEntry]:
        """Offer each server/key combination once, using entry IDs as form values."""
        connections = {}
        seen = set()
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            url = entry.data.get(CONF_URL)
            api_key = entry.data.get(CONF_API_KEY)
            if not isinstance(url, str) or not isinstance(api_key, str) or not url.strip() or not api_key.strip():
                continue
            identity = (url.strip().rstrip("/"), api_key)
            if identity not in seen:
                connections[entry.entry_id] = entry
                seen.add(identity)
        return connections

    async def async_step_connection(self, user_input: dict[str, Any] | None = None):
        connections = self._saved_connections()
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input["connection_id"]
            if selected == "new":
                return await self.async_step_new_connection()
            entry = connections.get(selected)
            if entry is None:
                errors["base"] = "connection_unavailable"
            else:
                errors = await self._async_check_connection(entry.data)
                if not errors:
                    return await self.async_step_source()
        # Credentials stay on the server; the form only contains entry IDs and labels.
        options = {
            entry_id: f"{entry.data[CONF_URL]} ({entry.title})"
            for entry_id, entry in connections.items()
        }
        options["new"] = "Connect to another Immich server"
        return self.async_show_form(step_id="connection", data_schema=vol.Schema({
            vol.Required("connection_id", default=next(iter(options))): vol.In(options),
        }), errors=errors)

    async def async_step_new_connection(self, user_input: dict[str, Any] | None = None):
        return await self._async_connection_form("new_connection", user_input)

    async def _async_check_connection(self, data) -> dict[str, str]:
        """Verify credentials and copy only connection details into the new frame."""
        errors: dict[str, str] = {}
        try:
            url = str(data[CONF_URL]).strip()
            if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
                raise ValueError("invalid_url")
            api_key = str(data[CONF_API_KEY])
            api = ImmichApi(url, api_key)
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
            self._data = {CONF_URL: url, CONF_API_KEY: api_key}
        return errors

    async def _async_connection_form(self, step_id, user_input):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_check_connection(user_input)
            if not errors:
                return await self.async_step_source()
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema({
            vol.Required(CONF_URL): str,
            vol.Required(CONF_API_KEY): str,
        }), errors=errors)

    async def async_step_source(self, user_input: dict[str, Any] | None = None, *, errors: dict[str, str] | None = None):
        if user_input:
            source = {
                "All photos": "all",
                "Album": "album",
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
            vol.Required(CONF_SOURCE, default="All photos"): vol.In(["All photos", "Album", "On This Day memories", "Smart Search"]),
        }), errors=errors or {})

    async def async_step_album(self, user_input: dict[str, Any] | None = None):
        api = ImmichApi(self._data[CONF_URL], self._data[CONF_API_KEY])
        try:
            albums = await api.albums()
        except ImmichApiError as exc:
            error = "album_access_denied" if exc.status in (401, 403) else "albums_unavailable"
            return await self.async_step_source(errors={"base": error})
        except OSError:
            return await self.async_step_source(errors={"base": "albums_unavailable"})
        finally:
            await api.close()
        if not albums:
            return await self.async_step_source(errors={"base": "no_albums"})
        names = {album["id"]: album["albumName"].strip() or "Untitled album" for album in albums}
        counts = Counter(name.casefold() for name in names.values())
        options = [
            {"value": album_id, "label": f"{name} ({album_id})" if counts[name.casefold()] > 1 else name}
            for album_id, name in sorted(names.items(), key=lambda item: (item[1].casefold(), item[0]))
        ]
        errors: dict[str, str] = {}
        if user_input:
            album_id = str(user_input.get(CONF_ALBUM_ID, "")).strip()
            if album_id not in names:
                errors["base"] = "album_unavailable"
            else:
                self._data[CONF_ALBUM_ID] = album_id
                return await self.async_step_display()
        return self.async_show_form(step_id="album", data_schema=vol.Schema({
            vol.Required(CONF_ALBUM_ID): selector.SelectSelector(selector.SelectSelectorConfig(
                options=options, mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=False,
            )),
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
        names = {
            entry.title for entry in self.hass.config_entries.async_entries(DOMAIN)
            if str(entry.data.get(CONF_URL, "")).rstrip("/") == self._data[CONF_URL].rstrip("/")
        }
        name = "Immich Frame"
        suffix = 2
        while name in names:
            name = f"Immich Frame {suffix}"
            suffix += 1
        return self.async_show_form(step_id="display", data_schema=vol.Schema({
            vol.Required(CONF_FRAME_NAME, default=name): str,
            vol.Required(CONF_MODE, default="Single image"): vol.In(["Single image", "Matching portrait pairs"]),
            vol.Required(CONF_ORIENTATION, default="Any orientation"): vol.In(["Any orientation", "Portrait photos only", "Landscape photos only", "Square photos only"]),
            vol.Required(CONF_PAIR_WINDOW, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_PAIRS_ONLY, default=False): bool,
            vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=10, max=86400)),
        }))
