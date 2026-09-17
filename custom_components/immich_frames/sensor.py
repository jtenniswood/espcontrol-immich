from __future__ import annotations

from homeassistant.components.sensor import SensorEntity

from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data["immich_frames"][entry.entry_id]
    async_add_entities([PhotoSensor(coordinator, key, name, value) for key, name, value in (
        ("photo_date", "Photo date", lambda p, d: p.get("captured")),
        ("photo_location", "Photo location", lambda p, d: ", ".join(x for x in (p.get("exif", {}).get("city"), p.get("exif", {}).get("state"), p.get("exif", {}).get("country")) if x) or None),
        ("photo_filename", "Photo filename", lambda p, d: p.get("filename")),
        ("photo_people", "Photo people", lambda p, d: ", ".join(p.get("people", [])) or None),
        ("photo_tags", "Photo tags", lambda p, d: ", ".join(p.get("tags", [])) or None),
        ("photo_rating", "Photo rating", lambda p, d: p.get("rating")),
        ("photo_camera", "Photo camera", lambda p, d: p.get("exif", {}).get("model")),
        ("status", "Status", lambda p, d: d.status if d else None),
        ("slide", "Slide", lambda p, d: d.generation if d else None),
        ("matching_assets", "Matching assets", lambda p, d: d.matching_assets if d else None),
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
