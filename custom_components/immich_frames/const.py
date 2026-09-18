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
CONF_ORIENTATION = "orientation"
CONF_TIME_RANGE = "time_range"
DEFAULT_TIME_RANGE = "all_time"
TIME_RANGE_MONTHS = {
    "all_time": 0,
    "1_month": 1,
    "3_months": 3,
    "6_months": 6,
    "1_year": 12,
    "2_years": 24,
    "3_years": 36,
    "4_years": 48,
    "5_years": 60,
    "10_years": 120,
}
CONF_SCREEN_SHAPE = "screen_shape"
CONF_ORIGINAL_ASPECT_RATIO = "original_aspect_ratio"  # Legacy saved setting.
CONF_PHOTO_FIT = "photo_fit"
PHOTO_FIT_CROP = "crop"
PHOTO_FIT_FULL = "show_full"
DEFAULT_SCREEN_SHAPE = "landscape"
SCREEN_SIZES = {
    "landscape": (1280, 800),
    "portrait": (800, 1280),
    "square": (720, 720),
}
SCREEN_SHAPE_LABELS = {
    "landscape": "Landscape (1280 × 800)",
    "portrait": "Portrait (800 × 1280)",
    "square": "Square (720 × 720)",
}
LEGACY_SCREEN_SHAPES = {
    "jc1060p470": "landscape",
    "jc4880p443": "portrait",
    "4848s040": "square",
}

CONF_INTERVAL = "interval"
CONF_MEMORY_WINDOW = "memory_window_days"
CONF_FALLBACK = "fallback_to_all"
DEFAULT_INTERVAL = 30
DEFAULT_PAIR_WINDOW = 2
PLATFORMS: list[Platform] = [Platform.IMAGE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON, Platform.NUMBER, Platform.SELECT]
PHOTO_SELECTION_DEFAULTS = {
    CONF_MODE: "single",
    CONF_ORIENTATION: "any",
    CONF_TIME_RANGE: DEFAULT_TIME_RANGE,
    CONF_PAIR_WINDOW: DEFAULT_PAIR_WINDOW,
}


def screen_shape(value: str | None) -> str:
    """Map saved device presets to their corresponding output shape."""
    value = LEGACY_SCREEN_SHAPES.get(value, value)
    return value if value in SCREEN_SIZES else DEFAULT_SCREEN_SHAPE


def photo_selection_settings(options: dict) -> dict:
    """Settings that determine which photos and pairings may appear in a cache."""
    return {key: options.get(key, default) for key, default in PHOTO_SELECTION_DEFAULTS.items()}


def photo_fit(options: dict) -> str:
    """Use the explicit choice, or preserve the closest legacy display behavior."""
    if options.get(CONF_PHOTO_FIT) in (PHOTO_FIT_CROP, PHOTO_FIT_FULL):
        return options[CONF_PHOTO_FIT]
    if options.get(CONF_ORIGINAL_ASPECT_RATIO) or options.get(CONF_MODE) not in ("pairs", "pairs_only"):
        return PHOTO_FIT_FULL
    return PHOTO_FIT_CROP


def slide_photo_fit(options: dict, photos: list[dict] | tuple[dict, ...]) -> str:
    """Keep an unmatched portrait whole when falling back from paired mode."""
    if options.get(CONF_MODE) == "pairs" and len(photos) == 1 and photos[0].get("orientation") == "portrait":
        return PHOTO_FIT_FULL
    return photo_fit(options)
