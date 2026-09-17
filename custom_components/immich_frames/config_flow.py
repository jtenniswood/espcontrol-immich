from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries

from .api import ImmichApi, ImmichApiError, parse_filter
from .const import (
    CONF_API_KEY, CONF_FALLBACK, CONF_FILTER, CONF_FRAME_NAME, CONF_INTERVAL, CONF_MEMORY_WINDOW,
    CONF_MODE, CONF_ORIENTATION, CONF_PAIRS_ONLY, CONF_PAIR_WINDOW, CONF_SMART_QUERY,
    CONF_SOURCE, CONF_URL, DEFAULT_INTERVAL, DOMAIN,
)


class ImmichFramesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            try:
                user_input[CONF_SOURCE] = {
                    "All photos": "all",
                    "Structured filter": "filter",
                    "On This Day memories": "memories",
                    "Smart Search": "smart",
                }.get(user_input[CONF_SOURCE], user_input[CONF_SOURCE])
                user_input[CONF_MODE] = {
                    "Single image": "single",
                    "Matching portrait pairs": "pairs",
                }.get(user_input[CONF_MODE], user_input[CONF_MODE])
                url = str(user_input[CONF_URL]).strip()
                if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
                    raise ValueError("invalid_url")
                user_input[CONF_FILTER] = parse_filter(user_input.get(CONF_FILTER, "{}"))
                api = ImmichApi(url, str(user_input[CONF_API_KEY]))
                await api.version()
                await api.close()
            except ValueError:
                errors["base"] = "invalid_filter_or_url"
            except (ImmichApiError, OSError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{url}|{user_input[CONF_FRAME_NAME].strip()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_FRAME_NAME].strip(), data=user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_URL): str,
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_FRAME_NAME, default="Immich Frame"): str,
            vol.Required(CONF_SOURCE, default="All photos"): vol.In(["All photos", "Structured filter", "On This Day memories", "Smart Search"]),
            vol.Optional(CONF_SMART_QUERY, default=""): str,
            vol.Required(CONF_MODE, default="Single image"): vol.In(["Single image", "Matching portrait pairs"]),
            vol.Required(CONF_ORIENTATION, default="any"): vol.In(["any", "portrait", "landscape", "square"]),
            vol.Required(CONF_PAIR_WINDOW, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_PAIRS_ONLY, default=False): bool,
            vol.Required(CONF_MEMORY_WINDOW, default=2): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
            vol.Required(CONF_FALLBACK, default=False): bool,
            vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=10, max=86400)),
            vol.Required(CONF_FILTER, default="{}"): str,
        }), errors=errors)
