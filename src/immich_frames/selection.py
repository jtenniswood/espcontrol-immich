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

