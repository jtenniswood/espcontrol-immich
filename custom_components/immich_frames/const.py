from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "immich_frames"
CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_FRAME_NAME = "frame_name"
CONF_SOURCE = "source"
CONF_ALBUM_ID = "album_id"
CONF_ALBUM_IDS = "album_ids"
CONF_MODE = "mode"
CONF_FILTER = "filter"
CONF_SMART_QUERY = "smart_query"
CONF_PAIR_WINDOW = "pair_window_days"
CONF_PAIRS_ONLY = "pairs_only"
CONF_ORIENTATION = "orientation"
OUTPUT_SIZE = (1280, 800)
CONF_INTERVAL = "interval"
CONF_MEMORY_WINDOW = "memory_window_days"
CONF_FALLBACK = "fallback_to_all"
DEFAULT_INTERVAL = 30
PLATFORMS: list[Platform] = [Platform.IMAGE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON, Platform.NUMBER, Platform.SELECT]
