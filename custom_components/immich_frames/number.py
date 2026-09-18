from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_INTERVAL, CONF_PAIR_WINDOW, DEFAULT_PAIR_WINDOW, DOMAIN
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IntervalNumber(coordinator), PairWindowNumber(coordinator)])


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


class PairWindowNumber(ImmichFrameEntity, NumberEntity):
    _attr_translation_key = "pair_window_days"
    _attr_icon = "mdi:calendar-range"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 7
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "d"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, CONF_PAIR_WINDOW)

    @property
    def native_value(self):
        return self.coordinator.entry.data.get(CONF_PAIR_WINDOW, DEFAULT_PAIR_WINDOW)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.async_update_settings({CONF_PAIR_WINDOW: int(value)})
