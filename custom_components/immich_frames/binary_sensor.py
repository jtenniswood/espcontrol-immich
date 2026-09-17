from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data["immich_frames"][entry.entry_id]
    async_add_entities([ConnectionSensor(coordinator)])


class ConnectionSensor(ImmichFrameEntity, BinarySensorEntity):
    _attr_name = "Immich connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "immich_connected")

    @property
    def is_on(self):
        return bool(self.coordinator.data and self.coordinator.data.connected)
