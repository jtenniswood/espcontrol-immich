from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import ImmichFrameEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = hass.data["immich_frames"][entry.entry_id]
    async_add_entities([FrameButton(coordinator, key, name, action) for key, name, action in (
        ("next", "Next", coordinator.async_next),
        ("previous", "Previous", coordinator.async_previous),
        ("clear_cache", "Clear cache", coordinator.async_clear_cache),
    )])


class FrameButton(ImmichFrameEntity, ButtonEntity):
    def __init__(self, coordinator, key, name, action) -> None:
        ImmichFrameEntity.__init__(self, coordinator, key)
        self._attr_name = name
        self._action = action

    async def async_press(self) -> None:
        await self._action()
