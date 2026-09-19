from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from homeassistant.components.image import ImageEntity

from .coordinator import FrameCoordinator
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FrameImage(hass, entry.runtime_data)])


class FrameImage(ImmichFrameEntity, ImageEntity):
    _attr_name = "Image"
    _attr_translation_key = "image"
    _attr_content_type = "image/jpeg"

    def __init__(self, hass, coordinator: FrameCoordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "image")
        ImageEntity.__init__(self, hass)

    @property
    def image_last_updated(self) -> datetime | None:
        return self.coordinator.data.created_at if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Link to the original photos from the displayed snapshot."""
        snapshot = self.coordinator.data
        if snapshot is None:
            return {}
        base_url = self.coordinator.api.base_url
        return {
            key: f"{base_url}/photos/{quote(photo['id'], safe='')}"
            for key, photo in zip(
                ("open_in_immich", "open_second_photo_in_immich"), snapshot.photos
            )
            if photo.get("id")
        }

    @property
    def entity_picture(self) -> str | None:
        """Refresh entity-row thumbnails whenever the displayed frame changes."""
        url = super().entity_picture
        updated = self.image_last_updated
        if url is None or updated is None:
            return url
        # Entity rows use this URL directly, without watching the image timestamp.
        return f"{url}&v={updated.timestamp()}"

    async def async_image(self) -> bytes | None:
        return self.coordinator.data.image if self.coordinator.data else None
