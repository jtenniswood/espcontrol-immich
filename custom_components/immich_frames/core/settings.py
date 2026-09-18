from __future__ import annotations


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
    return {
        key: options.get(key, default)
        for key, default in PHOTO_SELECTION_DEFAULTS.items()
    }


def photo_fit(options: dict) -> str:
    """Use the explicit choice, or preserve the closest legacy display behavior."""
    if options.get(CONF_PHOTO_FIT) in (PHOTO_FIT_CROP, PHOTO_FIT_FULL):
        return options[CONF_PHOTO_FIT]
    if options.get(CONF_ORIGINAL_ASPECT_RATIO) or options.get(CONF_MODE) not in (
        "pairs",
        "pairs_only",
    ):
        return PHOTO_FIT_FULL
    return PHOTO_FIT_CROP


def slide_photo_fit(options: dict, photos: list[dict] | tuple[dict, ...]) -> str:
    """Keep an unmatched portrait whole when falling back from paired mode."""
    if (
        options.get(CONF_MODE) == "pairs"
        and len(photos) == 1
        and photos[0].get("orientation") == "portrait"
    ):
        return PHOTO_FIT_FULL
    return photo_fit(options)


# Storage version is independent of either installation package's release version.
SETTINGS_VERSION = 2

from dataclasses import dataclass, field, asdict
from copy import deepcopy
from typing import Any


@dataclass(frozen=True)
class Setting:
    key: str
    default: Any
    label: str
    choices: tuple[tuple[str, str], ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    icon: str | None = None
    entity_key: str | None = None


SETTINGS = (
    Setting(
        CONF_TIME_RANGE,
        DEFAULT_TIME_RANGE,
        "Time range",
        tuple(
            zip(
                TIME_RANGE_MONTHS,
                (
                    "All time",
                    "Last 1 month",
                    "Last 3 months",
                    "Last 6 months",
                    "Last 1 year",
                    "Last 2 years",
                    "Last 3 years",
                    "Last 4 years",
                    "Last 5 years",
                    "Last 10 years",
                ),
            )
        ),
        icon="mdi:calendar-range",
    ),
    Setting(
        CONF_SCREEN_SHAPE,
        DEFAULT_SCREEN_SHAPE,
        "Screen shape",
        tuple(SCREEN_SHAPE_LABELS.items()),
        icon="mdi:aspect-ratio",
        entity_key="output_size",
    ),
    Setting(
        CONF_PHOTO_FIT,
        PHOTO_FIT_FULL,
        "Photo fit",
        ((PHOTO_FIT_CROP, "Crop to fit"), (PHOTO_FIT_FULL, "Show full image")),
        icon="mdi:image-size-select-large",
    ),
    Setting(
        CONF_MODE,
        "single",
        "Portrait images",
        (
            ("single", "Single portrait photos only"),
            ("pairs", "Single and Paired portrait photos"),
            ("pairs_only", "Paired portrait photos only"),
        ),
        icon="mdi:image-multiple",
    ),
    Setting(
        CONF_ORIENTATION,
        "any",
        "Photo orientation",
        (
            ("any", "Mixed (landscapes and portraits)"),
            ("portrait", "Portrait photos only"),
            ("landscape", "Landscape photos only"),
        ),
        icon="mdi:image-filter-center-focus",
    ),
    Setting(
        CONF_PAIR_WINDOW,
        DEFAULT_PAIR_WINDOW,
        "Pairing window",
        minimum=0,
        maximum=7,
        icon="mdi:calendar-range",
    ),
    Setting(CONF_INTERVAL, DEFAULT_INTERVAL, "Photo timer", minimum=10, maximum=86400),
)
SETTING_BY_KEY = {setting.key: setting for setting in SETTINGS}


@dataclass(frozen=True)
class FrameSettings:
    """Canonical product settings. Host identity and credentials stay outside."""

    source: str = "all"
    album_ids: tuple[str, ...] = ()
    smart_query: str = ""
    memory_window_days: int = 2
    fallback_to_all: bool = False
    mode: str = "single"
    orientation: str = "any"
    time_range: str = DEFAULT_TIME_RANGE
    pair_window_days: int = DEFAULT_PAIR_WINDOW
    screen_shape: str = DEFAULT_SCREEN_SHAPE
    photo_fit: str = PHOTO_FIT_FULL
    interval: int = DEFAULT_INTERVAL
    filter: dict = field(default_factory=dict)
    order_field: str = "fileCreatedAt"
    order_direction: str = "random"
    smart_reference_asset_id: str | None = None

    @classmethod
    def from_options(cls, options: dict) -> FrameSettings:
        data = deepcopy(options)
        albums = data.get(
            CONF_ALBUM_IDS, [data[CONF_ALBUM_ID]] if data.get(CONF_ALBUM_ID) else []
        )
        if not isinstance(albums, (list, tuple)) or any(
            not isinstance(x, str) or not x.strip() for x in albums
        ):
            raise ValueError("album_ids must contain album IDs")
        data[CONF_ALBUM_IDS] = tuple(dict.fromkeys(x.strip() for x in albums))
        data[CONF_SCREEN_SHAPE] = screen_shape(data.get(CONF_SCREEN_SHAPE))
        data[CONF_PHOTO_FIT] = photo_fit(data)
        values = {
            key: value for key, value in data.items() if key in cls.__dataclass_fields__
        }
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self) -> None:
        for spec in SETTINGS:
            value = getattr(self, spec.key)
            # Preserve the saved square-only setting, without adding a new UI choice.
            if (
                spec.choices
                and value not in dict(spec.choices)
                and not (spec.key == CONF_ORIENTATION and value == "square")
            ):
                raise ValueError(f"Invalid {spec.key}: {value}")
            if spec.minimum is not None and (
                type(value) is not int or not spec.minimum <= value <= spec.maximum
            ):
                raise ValueError(
                    f"{spec.key} must be between {spec.minimum} and {spec.maximum}"
                )
        if self.source not in ("all", "album", "smart", "memories", "filter"):
            raise ValueError("Invalid source")
        if (
            type(self.memory_window_days) is not int
            or not 0 <= self.memory_window_days <= 7
        ):
            raise ValueError("memory_window_days must be between 0 and 7")
        if type(self.fallback_to_all) is not bool:
            raise ValueError("fallback_to_all must be a boolean")
        if not isinstance(self.smart_query, str) or not isinstance(self.filter, dict):
            raise ValueError("Invalid photo source settings")
        if self.order_direction not in ("random", "asc", "desc"):
            raise ValueError("Invalid order_direction")
        if self.order_field not in (
            "fileCreatedAt",
            "localDateTime",
            "fileSizeInBytes",
            "rating",
        ):
            raise ValueError("Invalid order_field")

    def options(self) -> dict:
        data = asdict(self)
        data[CONF_ALBUM_IDS] = list(self.album_ids)
        return data

    @property
    def output_size(self) -> tuple[int, int]:
        return SCREEN_SIZES[self.screen_shape]


def migrate_settings(data: dict, version: int = 1) -> dict:
    """Upgrade v1 frame dictionaries without modifying credentials or identity."""
    if version > SETTINGS_VERSION:
        raise ValueError("Settings were saved by a newer version")
    result = deepcopy(data)
    if version == 1:
        result[CONF_SCREEN_SHAPE] = screen_shape(result.get(CONF_SCREEN_SHAPE))
        result[CONF_PHOTO_FIT] = photo_fit(result)
        if CONF_ALBUM_ID in result and CONF_ALBUM_IDS not in result:
            result[CONF_ALBUM_IDS] = (
                [result[CONF_ALBUM_ID]] if result[CONF_ALBUM_ID] else []
            )
        result.pop(CONF_ALBUM_ID, None)
        result.pop(CONF_ORIGINAL_ASPECT_RATIO, None)
        result.pop("pairs_only", None)
        # Native v1 ignored custom filters for All photos/Albums and always
        # constrained visibility to timeline. Preserve that effective behavior.
        if result.get(CONF_SOURCE, "all") in ("all", "album"):
            result.pop("filter", None)
        elif result.get("filter"):
            result["filter"]["visibility"] = {"eq": "timeline"}
    FrameSettings.from_options(result)
    return result
