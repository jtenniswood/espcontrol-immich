from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities([SlideshowSwitch(coordinator)])


class SlideshowSwitch(ImmichFrameEntity, SwitchEntity):
    _attr_translation_key = "slideshow"

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "slideshow")

    @property
    def is_on(self):
        return not self.coordinator.paused

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.paused = False
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.paused = True
        self.async_write_ha_state()
