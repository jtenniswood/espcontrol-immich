from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import ImmichApi, ImmichApiError, selected_album_ids
from .const import (
    CONF_ALBUM_ID, CONF_ALBUM_IDS, CONF_API_KEY, CONF_FALLBACK, CONF_FRAME_NAME, CONF_INTERVAL, CONF_MEMORY_WINDOW,
    CONF_MODE, CONF_ORIENTATION, CONF_ORIGINAL_ASPECT_RATIO, CONF_PHOTO_FIT, CONF_PAIRS_ONLY, CONF_PAIR_WINDOW, CONF_SMART_QUERY,
    CONF_SCREEN_SHAPE, CONF_SOURCE, CONF_URL, DEFAULT_INTERVAL, DEFAULT_SCREEN_SHAPE, DOMAIN,
    PHOTO_FIT_CROP, PHOTO_FIT_FULL, PHOTO_SELECTION_DEFAULTS, SCREEN_SHAPE_LABELS, photo_fit,
)

SOURCE_LABELS = {"all": "All photos", "album": "Albums", "memories": "Memories", "smart": "Keywords"}
MODE_LABELS = {"single": "Single image", "pairs": "Pair portrait photos"}
ORIENTATION_LABELS = {"any": "Mixed (landscapes and portraits)", "portrait": "Portrait photos only", "landscape": "Landscape photos only"}
SOURCE_FIELDS = {
    "album": (CONF_ALBUM_ID, CONF_ALBUM_IDS),
    "memories": (CONF_MEMORY_WINDOW, CONF_FALLBACK),
    "smart": (CONF_SMART_QUERY,),
}


def _navigation(back_label: str, *, save: bool = False, change_source: bool = False) -> dict:
    options = {"continue": "Save frame" if save else "Continue", "back": back_label}
    if change_source:
        options["source"] = "Change photo source"
    return {vol.Optional("navigation", default="continue"): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[{"value": value, "label": label} for value, label in options.items()],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )}


class FrameSettingsFlow:
    """Shared source and display forms for setup and later edits."""

    def _navigation(self, back_label: str, *, save: bool = False, change_source: bool = False) -> dict:
        # New frames advance with the form button; existing frames retain back/edit actions.
        if self._settings_entry is None:
            return {}
        return _navigation(back_label, save=save, change_source=change_source)

    def _remember(self, user_input: dict[str, Any]) -> None:
        self._data.update({key: value for key, value in user_input.items() if key != "navigation"})

    async def async_step_source(self, user_input: dict[str, Any] | None = None, *, errors: dict[str, str] | None = None):
        if user_input:
            source = {
                "All photos": "all",
                "Albums": "album",
                "Memories": "memories",
                "Keywords": "smart",
            }.get(user_input[CONF_SOURCE], user_input[CONF_SOURCE])
            self._data[CONF_SOURCE] = source
            if source == "album":
                return await self.async_step_album()
            if source == "memories":
                if self._settings_entry is None:
                    self._data.setdefault(CONF_MEMORY_WINDOW, 2)
                    self._data.setdefault(CONF_FALLBACK, False)
                    return await self.async_step_display()
                return await self.async_step_memories()
            if source == "smart":
                return await self.async_step_smart()
            return await self.async_step_display()
        return self.async_show_form(step_id="source", data_schema=vol.Schema({
            vol.Required(CONF_SOURCE, default=SOURCE_LABELS.get(self._data.get(CONF_SOURCE), "All photos")): vol.In(list(SOURCE_LABELS.values())),
        }), errors=errors or {})

    async def async_step_album(self, user_input: dict[str, Any] | None = None):
        if user_input is not None and user_input.get("navigation") == "back":
            self._remember(user_input)
            return await self.async_step_source()
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
            album_ids = selected_album_ids(user_input)
            if not album_ids:
                errors["base"] = "album_required"
            elif any(album_id not in names for album_id in album_ids):
                errors["base"] = "album_unavailable"
            else:
                self._data[CONF_ALBUM_IDS] = album_ids
                self._data.pop(CONF_ALBUM_ID, None)
                return await self.async_step_display()
        saved_albums = [album_id for album_id in selected_album_ids(user_input if user_input is not None else self._data) if album_id in names]
        album_field = vol.Optional(CONF_ALBUM_IDS, default=saved_albums)
        return self.async_show_form(step_id="album", data_schema=vol.Schema({
            album_field: selector.SelectSelector(selector.SelectSelectorConfig(
                options=options, mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=False, multiple=True,
            )),
            **self._navigation("Back to photo source"),
        }), errors=errors)

    async def async_step_memories(self, user_input: dict[str, Any] | None = None):
        if user_input:
            self._remember(user_input)
            if user_input.get("navigation") == "back":
                return await self.async_step_source()
            return await self.async_step_display()
        return self.async_show_form(step_id="memories", data_schema=vol.Schema({
            vol.Required(CONF_MEMORY_WINDOW, default=self._data.get(CONF_MEMORY_WINDOW, 2)): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_FALLBACK, default=self._data.get(CONF_FALLBACK, False)): bool,
            **self._navigation("Back to photo source"),
        }))

    async def async_step_smart(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            self._remember(user_input)
            if user_input.get("navigation") == "back":
                return await self.async_step_source()
            if not str(user_input.get(CONF_SMART_QUERY, "")).strip():
                errors["base"] = "smart_query_required"
            else:
                return await self.async_step_display()
        return self.async_show_form(step_id="smart", data_schema=vol.Schema({
            vol.Optional(CONF_SMART_QUERY, default=self._data.get(CONF_SMART_QUERY, "")): str,
            **self._navigation("Back to photo source"),
        }), errors=errors)

    async def async_step_display(self, user_input: dict[str, Any] | None = None, *, errors: dict[str, str] | None = None):
        errors = errors or {}
        initial_setup = self._settings_entry is None
        source_step = self._data.get(CONF_SOURCE)
        if initial_setup and source_step == "memories":
            source_step = None
        if user_input and not initial_setup:
            user_input[CONF_MODE] = {
                "Single image": "single",
                "Pair portrait photos": "pairs",
            }.get(user_input[CONF_MODE], user_input[CONF_MODE])
            user_input[CONF_SCREEN_SHAPE] = {label: value for value, label in SCREEN_SHAPE_LABELS.items()}.get(user_input[CONF_SCREEN_SHAPE], user_input[CONF_SCREEN_SHAPE])
        if user_input:
            self._remember(user_input)
            if user_input.get("navigation") == "source":
                return await self.async_step_source()
            if user_input.get("navigation") == "back":
                if source_step in SOURCE_FIELDS:
                    return await getattr(self, f"async_step_{source_step}")()
                return await self.async_step_source()
            errors = self._name_errors()
            if not errors:
                if initial_setup:
                    return await self._async_finish_settings()
                return await self.async_step_photos()
        names = {
            entry.title for entry in self.hass.config_entries.async_entries(DOMAIN)
            if str(entry.data.get(CONF_URL, "")).rstrip("/") == self._data[CONF_URL].rstrip("/")
        }
        name = "Immich Frame"
        suffix = 2
        while name in names:
            name = f"Immich Frame {suffix}"
            suffix += 1
        fields = {vol.Required(CONF_FRAME_NAME, default=self._data.get(CONF_FRAME_NAME, name)): str}
        if not initial_setup:
            fields.update({
                vol.Required(CONF_SCREEN_SHAPE, default=SCREEN_SHAPE_LABELS.get(self._data.get(CONF_SCREEN_SHAPE), SCREEN_SHAPE_LABELS[DEFAULT_SCREEN_SHAPE])): vol.In(list(SCREEN_SHAPE_LABELS.values())),
                vol.Required(CONF_MODE, default=MODE_LABELS.get(self._data.get(CONF_MODE), "Single image")): vol.In(list(MODE_LABELS.values())),
            })
        fields.update(self._navigation(
            {"album": "Back to album selection", "memories": "Back to memory settings", "smart": "Back to Keywords"}.get(source_step, "Back to photo source"),
            change_source=source_step in SOURCE_FIELDS, save=initial_setup,
        ))
        return self.async_show_form(step_id="display", data_schema=vol.Schema(fields), errors=errors, last_step=initial_setup)


    async def async_step_photos(self, user_input: dict[str, Any] | None = None):
        pairs = self._data.get(CONF_MODE) == "pairs"
        if user_input:
            user_input[CONF_ORIENTATION] = {label: value for value, label in ORIENTATION_LABELS.items()}.get(user_input[CONF_ORIENTATION], user_input[CONF_ORIENTATION])
            self._remember(user_input)
            if user_input.get("navigation") == "back":
                return await self.async_step_display()
            if pairs:
                return await self.async_step_pairing()
            return await self._async_finish_settings()
        return self.async_show_form(step_id="photos", data_schema=vol.Schema({
            vol.Required(CONF_PHOTO_FIT, default=photo_fit(self._data)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    {"value": PHOTO_FIT_CROP, "label": "Crop to fit"},
                    {"value": PHOTO_FIT_FULL, "label": "Show full image"},
                ], mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_ORIENTATION, default=ORIENTATION_LABELS.get(self._data.get(CONF_ORIENTATION), "Mixed (landscapes and portraits)")): vol.In(list(ORIENTATION_LABELS.values())),
            vol.Required(CONF_INTERVAL, default=self._data.get(CONF_INTERVAL, DEFAULT_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=10, max=86400)),
            **self._navigation("Back to frame setup", save=not pairs),
        }), last_step=not pairs)

    async def async_step_pairing(self, user_input: dict[str, Any] | None = None):
        if user_input:
            self._remember(user_input)
            if user_input.get("navigation") == "back":
                return await self.async_step_photos()
            return await self._async_finish_settings()
        return self.async_show_form(step_id="pairing", data_schema=vol.Schema({
            vol.Required(CONF_PAIR_WINDOW, default=self._data.get(CONF_PAIR_WINDOW, 0)): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_PAIRS_ONLY, default=self._data.get(CONF_PAIRS_ONLY, False)): bool,
            **self._navigation("Back to photo display", save=True),
        }), last_step=True)

    def _name_errors(self) -> dict[str, str]:
        name = self._data[CONF_FRAME_NAME].strip()
        if not name:
            return {CONF_FRAME_NAME: "name_required"}
        unique_id = f"{self._data[CONF_URL]}|{name}"
        if any(other.unique_id == unique_id and other is not self._settings_entry for other in self.hass.config_entries.async_entries(DOMAIN)):
            return {CONF_FRAME_NAME: "name_in_use"}
        return {}

    async def _async_finish_settings(self):
        # Recheck in case another flow claimed this name while these steps were open.
        if errors := self._name_errors():
            return await self.async_step_display(errors=errors)
        data = {**PHOTO_SELECTION_DEFAULTS, CONF_INTERVAL: DEFAULT_INTERVAL,
                CONF_SCREEN_SHAPE: DEFAULT_SCREEN_SHAPE, **self._data}
        data[CONF_PHOTO_FIT] = photo_fit(data)
        name = data[CONF_FRAME_NAME] = data[CONF_FRAME_NAME].strip()
        unique_id = f"{data[CONF_URL]}|{name}"
        # Keep drafts while navigating, but save only the active source's filters.
        for source, fields in SOURCE_FIELDS.items():
            if source != data.get(CONF_SOURCE):
                for field in fields:
                    data.pop(field, None)
        data.pop("filter", None)
        data.pop(CONF_ORIGINAL_ASPECT_RATIO, None)
        return await self._async_save_settings(data, name, unique_id)


class ImmichFramesConfigFlow(FrameSettingsFlow, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return ImmichFramesOptionsFlow()

    @property
    def _settings_entry(self):
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self._get_reconfigure_entry()
        return None

    async def _async_save_settings(self, data, name, unique_id):
        if (entry := self._settings_entry) is not None:
            return self.async_update_reload_and_abort(entry, title=name, unique_id=unique_id, data=data)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=name, data=data)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Edit a copy; the running frame changes only when the user saves."""
        entry = self._get_reconfigure_entry()
        self._data = dict(entry.data)
        self._data.setdefault(CONF_FRAME_NAME, entry.title)
        return await self.async_step_source()

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


class ImmichFramesOptionsFlow(FrameSettingsFlow, config_entries.OptionsFlow):
    """Edit an existing frame through Home Assistant's Configure button."""

    @property
    def _settings_entry(self):
        return self.config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        self._data = dict(self.config_entry.data)
        self._data.setdefault(CONF_FRAME_NAME, self.config_entry.title)
        steps = ["source"]
        if (source := self._data.get(CONF_SOURCE)) in SOURCE_FIELDS:
            steps.append(source)
        steps.append("display")
        return self.async_show_menu(step_id="init", menu_options=steps)

    async def _async_save_settings(self, data, name, unique_id):
        # Runtime controls and existing installations store settings in entry.data.
        # Keep that single source of truth; only apply the draft on Save frame.
        entry = self.config_entry
        if self.hass.config_entries.async_update_entry(entry, title=name, unique_id=unique_id, data=data):
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(title="", data=dict(entry.options))
