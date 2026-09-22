"""Native saved-entry compatibility, outside the canonical product model."""

from copy import deepcopy

from .core.settings import (
    FrameSettings,
    SETTINGS_VERSION,
    CONF_ALBUM_IDS,
    CONF_ALBUM_ID,
    CONF_SCREEN_SHAPE,
    CONF_PHOTO_FIT,
    CONF_ORIGINAL_ASPECT_RATIO,
    CONF_SOURCE,
    screen_shape,
    photo_fit,
)


def native_settings(options: dict) -> FrameSettings:
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
    if CONF_PHOTO_FIT in data and data[CONF_PHOTO_FIT] not in ("crop", "show_full"):
        raise ValueError("Invalid photo_fit")
    data[CONF_PHOTO_FIT] = photo_fit(data)
    return FrameSettings(
        **{
            key: value
            for key, value in data.items()
            if key in FrameSettings.__dataclass_fields__
        }
    )


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
