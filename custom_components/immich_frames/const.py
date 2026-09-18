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
CONF_SCREEN_SHAPE = "screen_shape"
CONF_ORIGINAL_ASPECT_RATIO = "original_aspect_ratio"  # Legacy saved setting.
CONF_PHOTO_FIT = "photo_fit"
PHOTO_FIT_CROP = "crop"
PHOTO_FIT_FULL = "show_full"
DEFAULT_SCREEN_SHAPE = "landscape"
# Keep the original shape keys and dimensions for saved frames and automations.
# New choices identify the matching EspControl display rather than only its shape.
SCREEN_SIZES = {
    "landscape": (1280, 800),
    "jc1060p470": (1024, 600),
    "jc4880p443": (480, 800),
    "square": (720, 720),
    "4848s040": (480, 480),
    "portrait": (800, 1280),
}
SCREEN_SHAPE_LABELS = {
    "landscape": "10.1-inch Guition JC8012P4A1 (1280 × 800, landscape)",
    "jc1060p470": "7-inch Guition JC1060P470 (1024 × 600, landscape)",
    "jc4880p443": "4.3-inch Guition JC4880P443 (480 × 800, portrait)",
    "square": "4-inch ESP32-P4 86 Panel (720 × 720, square)",
    "4848s040": "4-inch Guition 4848S040 (480 × 480, square)",
    "portrait": "10.1-inch Guition JC8012P4A1 (800 × 1280, portrait)",
}
CONF_INTERVAL = "interval"
CONF_MEMORY_WINDOW = "memory_window_days"
CONF_FALLBACK = "fallback_to_all"
DEFAULT_INTERVAL = 30
PLATFORMS: list[Platform] = [Platform.IMAGE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON, Platform.NUMBER, Platform.SELECT]
PHOTO_SELECTION_DEFAULTS = {
    CONF_MODE: "single",
    CONF_ORIENTATION: "any",
    CONF_PAIR_WINDOW: 0,
    CONF_PAIRS_ONLY: False,
}


def photo_selection_settings(options: dict) -> dict:
    """Settings that determine which photos and pairings may appear in a cache."""
    return {key: options.get(key, default) for key, default in PHOTO_SELECTION_DEFAULTS.items()}


def photo_fit(options: dict) -> str:
    """Use the explicit choice, or preserve the closest legacy display behavior."""
    if options.get(CONF_PHOTO_FIT) in (PHOTO_FIT_CROP, PHOTO_FIT_FULL):
        return options[CONF_PHOTO_FIT]
    if options.get(CONF_ORIGINAL_ASPECT_RATIO) or options.get(CONF_MODE) != "pairs":
        return PHOTO_FIT_FULL
    return PHOTO_FIT_CROP
