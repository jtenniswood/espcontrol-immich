from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_MODE, CONF_ORIENTATION, CONF_PHOTO_FIT, CONF_SCREEN_SHAPE,
    DEFAULT_SCREEN_SHAPE, DOMAIN, PHOTO_FIT_CROP, PHOTO_FIT_FULL, SCREEN_SIZES, photo_fit,
)
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        FrameSettingSelect(coordinator, "output_size", list(SCREEN_SIZES), DEFAULT_SCREEN_SHAPE,
                           "mdi:aspect-ratio", config_key=CONF_SCREEN_SHAPE),
        FrameSettingSelect(coordinator, CONF_PHOTO_FIT, [PHOTO_FIT_CROP, PHOTO_FIT_FULL], PHOTO_FIT_FULL,
                           "mdi:image-size-select-large"),
        FrameSettingSelect(coordinator, CONF_MODE, ["single", "pairs"], "single", "mdi:image-multiple"),
        FrameSettingSelect(coordinator, CONF_ORIENTATION, ["any", "portrait", "landscape"], "any",
                           "mdi:image-filter-center-focus"),
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
