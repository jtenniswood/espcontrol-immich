from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([MetadataRoleSelect(hass.data["immich_frames"][entry.entry_id])])


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
