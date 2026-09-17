from __future__ import annotations

from typing import Any

from .selection import safe_filter

FILTER_FIELDS = {
    "albumIds", "checksum", "city", "country", "createdAt", "description", "fileSizeInBytes",
    "hasAlbums", "hasPeople", "hasTags", "id", "isEncoded", "isFavorite", "isMotion", "isOffline",
    "lensModel", "libraryId", "make", "model", "ocr", "originalFileName", "originalPath", "personIds",
    "rating", "state", "tagIds", "takenAt", "trashedAt", "type", "updatedAt", "visibility",
}


class FilterValidationError(ValueError):
    pass


def validate_filter(value: Any, path: str = "filter") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FilterValidationError(f"{path} must be an object")
    for field, condition in value.items():
        if field == "or":
            if not isinstance(condition, list) or not condition:
                raise FilterValidationError(f"{path}.or must be a non-empty list")
            for index, branch in enumerate(condition):
                validate_filter(branch, f"{path}.or[{index}]")
            continue
        if field not in FILTER_FIELDS:
            raise FilterValidationError(f"{path}.{field} is not supported by Immich 3.2")
        if not isinstance(condition, dict):
            raise FilterValidationError(f"{path}.{field} must be an operator object")
    return value


def compile_filter(value: dict[str, Any]) -> dict[str, Any]:
    """Validate user rules and add frame-wide safety constraints."""
    return safe_filter(validate_filter(value))
