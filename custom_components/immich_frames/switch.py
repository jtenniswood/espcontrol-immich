from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from homeassistant.helpers.entity import EntityCategory

from .const import CONF_PAIRS_ONLY, DOMAIN
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SlideshowSwitch(coordinator), PairsOnlySwitch(coordinator)])


class SlideshowSwitch(ImmichFrameEntity, SwitchEntity):
    _attr_name = "Slideshow"

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


class PairsOnlySwitch(ImmichFrameEntity, SwitchEntity):
    _attr_translation_key = "pairs_only"
    _attr_icon = "mdi:image-multiple"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, CONF_PAIRS_ONLY)

    @property
    def is_on(self):
        return self.coordinator.entry.data.get(CONF_PAIRS_ONLY, False)

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.async_update_settings({CONF_PAIRS_ONLY: True})

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.async_update_settings({CONF_PAIRS_ONLY: False})
