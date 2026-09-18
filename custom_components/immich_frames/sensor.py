from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorEntity

from .entity import ImmichFrameEntity


def _friendly_date(value: str | None) -> str | None:
    """Show the photo's recorded calendar date without converting its timezone."""
    if not value:
        return None
    try:
        captured = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return f"{captured.day} {captured:%B}, {captured.year}"


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data["immich_frames"][entry.entry_id]
    async_add_entities([PhotoSensor(coordinator, key, name, value) for key, name, value in (
        ("photo_date", "Date", lambda p, d: _friendly_date(p.get("captured"))),
        ("photo_location", "Location", lambda p, d: ", ".join(x for x in (p.get("exif", {}).get("city"), p.get("exif", {}).get("state"), p.get("exif", {}).get("country")) if x) or None),
        ("photo_people", "People", lambda p, d: ", ".join(p.get("people", [])) or None),
        ("photo_tags", "Tags", lambda p, d: ", ".join(p.get("tags", [])) or None),
        ("photo_rating", "Rating", lambda p, d: p.get("rating")),
        ("photo_camera", "Camera", lambda p, d: p.get("exif", {}).get("model")),
    )])


class PhotoSensor(ImmichFrameEntity, SensorEntity):
    def __init__(self, coordinator, key, name, value) -> None:
        ImmichFrameEntity.__init__(self, coordinator, key)
        self._attr_name = name
        self._value = value

    @property
    def native_value(self):
        data = self.coordinator.data
        return self._value(self.selected_photo, data) if data else None
