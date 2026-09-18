from __future__ import annotations

from typing import Any

ALLOWED_VISIBILITY = ["timeline", "archive", "hidden"]


def safe_filter(user_filter: dict[str, Any]) -> dict[str, Any]:
    """Apply the frame's non-negotiable safety constraints to an Immich filter."""
    result = dict(user_filter)
    result["type"] = {"eq": "IMAGE"}
    result["trashedAt"] = {"eq": None}
    requested_visibility = result.get("visibility")
    if requested_visibility is None:
        result["visibility"] = {"eq": "timeline"}
    else:
        # Never permit a user rule to widen the query to locked assets.
        if "in" in requested_visibility:
            visible = [item for item in requested_visibility["in"] if item in ALLOWED_VISIBILITY]
            result["visibility"] = {"in": visible or ["timeline"]}
        elif requested_visibility.get("eq") not in ALLOWED_VISIBILITY:
            result["visibility"] = {"eq": "timeline"}
    return result




FILTER_FIELDS = {
    "albumIds", "checksum", "city", "country", "createdAt", "description", "fileSizeInBytes",
    "hasAlbums", "hasPeople", "hasTags", "id", "isEncoded", "isFavorite", "isMotion", "isOffline",
    "lensModel", "libraryId", "make", "model", "ocr", "originalFileName", "originalPath", "personIds",
    "rating", "state", "tagIds", "takenAt", "trashedAt", "type", "updatedAt", "visibility",
}
ID_FIELDS = {"albumIds", "personIds", "tagIds"}
BOOL_FIELDS = {"hasAlbums", "hasPeople", "hasTags", "isEncoded", "isFavorite", "isMotion", "isOffline"}
DATE_FIELDS = {"createdAt", "takenAt", "trashedAt", "updatedAt"}
NUMBER_FIELDS = {"fileSizeInBytes", "rating"}
STRING_FIELDS = FILTER_FIELDS - ID_FIELDS - BOOL_FIELDS - DATE_FIELDS - NUMBER_FIELDS - {"type", "or"}
COMMON_OPERATORS = {"eq", "ne", "in", "notIn"}


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
        operators = COMMON_OPERATORS
        if field in ID_FIELDS:
            operators = {"any", "all", "none"}
        elif field in {"id", "libraryId"}:
            operators = {"eq", "ne"}
            if not condition:
                raise FilterValidationError(f"{path}.{field} requires eq or ne")
        elif field in BOOL_FIELDS:
            operators = {"eq"}
        elif field in DATE_FIELDS:
            operators = {"eq", "ne", "gt", "gte", "lt", "lte"}
        elif field in NUMBER_FIELDS:
            operators = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "notIn"}
        elif field in STRING_FIELDS:
            operators = COMMON_OPERATORS | {"startsWith", "endsWith", "like", "notLike"}
        elif field == "type":
            operators = COMMON_OPERATORS
        unknown = set(condition) - operators
        if unknown:
            raise FilterValidationError(f"{path}.{field} has unsupported operators: {', '.join(sorted(unknown))}")
    return value


def compile_filter(value: dict[str, Any]) -> dict[str, Any]:
    """Validate user rules and add frame-wide safety constraints."""
    return safe_filter(validate_filter(value))
