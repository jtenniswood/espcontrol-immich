from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FrameCoordinator


class ImmichFrameEntity(CoordinatorEntity[FrameCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FrameCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="EspControl",
            model="Immich Companion photo frame",
        )

    @property
    def selected_photo(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        if self.coordinator.metadata_role == "secondary" and data.secondary:
            return data.secondary
        return data.primary
