from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_PHOTO_FIT, photo_fit
from .core.settings import SETTINGS
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        FrameSettingSelect(coordinator, spec.entity_key or spec.key,
                           list(dict(spec.choices)), spec.default, spec.icon, config_key=spec.key)
        for spec in SETTINGS if spec.choices
    ])


class FrameSettingSelect(ImmichFrameEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key, options, default, icon, *, config_key=None) -> None:
        ImmichFrameEntity.__init__(self, coordinator, key)
        self._config_key = config_key or key
        self._default = default
        self._attr_translation_key = key
        self._attr_options = options
        self._attr_icon = icon

    @property
    def current_option(self):
        if self._config_key == CONF_PHOTO_FIT:
            return photo_fit(self.coordinator.entry.data)
        return self.coordinator.entry.data.get(self._config_key, self._default)

    async def async_select_option(self, option: str) -> None:
        if option != self.current_option:
            self.coordinator.async_update_settings({self._config_key: option})
