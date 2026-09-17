from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([MetadataRoleSelect(hass.data["immich_frames"][entry.entry_id])])


class MetadataRoleSelect(ImmichFrameEntity, SelectEntity):
    _attr_name = "Metadata photo"
    _attr_options = ["primary", "secondary"]

    def __init__(self, coordinator) -> None:
        ImmichFrameEntity.__init__(self, coordinator, "metadata_role")

    @property
    def current_option(self):
        return self.coordinator.metadata_role

    async def async_select_option(self, option: str) -> None:
        self.coordinator.metadata_role = option
        self.coordinator.async_update_listeners()
