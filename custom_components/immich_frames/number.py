from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_INTERVAL
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([IntervalNumber(hass.data["immich_frames"][entry.entry_id])])


class IntervalNumber(ImmichFrameEntity, NumberEntity):
    _attr_name = "Slide interval"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 10
    _attr_native_max_value = 86400
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "interval")

    @property
    def native_value(self):
        return self.coordinator.options.get(CONF_INTERVAL, 30)

    async def async_set_native_value(self, value: float) -> None:
        interval = max(10, min(86400, int(value)))
        self.coordinator.options[CONF_INTERVAL] = interval
        self.coordinator.update_interval = timedelta(seconds=interval)
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry,
            data={**self.coordinator.entry.data, CONF_INTERVAL: interval},
        )
        self.async_write_ha_state()
