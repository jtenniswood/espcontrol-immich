from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_SCREEN_SHAPE, DEFAULT_SCREEN_SHAPE, DOMAIN, SCREEN_SIZES
from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MetadataRoleSelect(coordinator), OutputSizeSelect(coordinator)])


class OutputSizeSelect(ImmichFrameEntity, SelectEntity):
    _attr_translation_key = "output_size"
    _attr_icon = "mdi:aspect-ratio"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(SCREEN_SIZES)

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "output_size")

    @property
    def current_option(self):
        return self.coordinator.entry.data.get(CONF_SCREEN_SHAPE, DEFAULT_SCREEN_SHAPE)

    async def async_select_option(self, option: str) -> None:
        if option == self.current_option:
            return
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SCREEN_SHAPE: option},
        )
        # Use the same reload path as Configure: discard old-size history and
        # reject incompatible cached JPEGs before rendering the new frame.
        self.hass.config_entries.async_schedule_reload(entry.entry_id)


class MetadataRoleSelect(ImmichFrameEntity, SelectEntity):
    _attr_translation_key = "metadata_role"
    _attr_icon = "mdi:image-text"
    # Keep service values stable for existing automations; translate UI labels.
    _attr_options = ["primary", "secondary"]
    _attr_extra_state_attributes = {
        "description": (
            "Chooses which photo supplies the Photo date, location, filename, people, "
            "tags, rating and camera sensors. For a pair, choose the left or right "
            "photo. When only one photo is shown, its details are always used."
        ),
    }

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "metadata_role")

    @property
    def current_option(self):
        return self.coordinator.metadata_role

    async def async_select_option(self, option: str) -> None:
        self.coordinator.metadata_role = option
        self.coordinator.async_update_listeners()
