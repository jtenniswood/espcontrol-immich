from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FrameCoordinator
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FrameImage(hass, hass.data["immich_frames"][entry.entry_id])])


class FrameImage(ImmichFrameEntity, ImageEntity):
    _attr_name = "Image"
    _attr_content_type = "image/jpeg"

    def __init__(self, hass, coordinator: FrameCoordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "image")
        ImageEntity.__init__(self, hass)

    @property
    def image_last_updated(self) -> datetime | None:
        return self.coordinator.data.created_at if self.coordinator.data else None

    async def async_image(self) -> bytes | None:
        return self.coordinator.data.image if self.coordinator.data else None
