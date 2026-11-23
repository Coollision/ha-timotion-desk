"""Buttons: stop, and the diagnostic height reset."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TimotionDeskConfigEntry
from .coordinator import TimotionDesk
from .entity import TimotionDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TimotionDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    desk = entry.runtime_data
    async_add_entities([StopButton(desk), ResetButton(desk)])


class StopButton(TimotionDeskEntity, ButtonEntity):
    """Stop whatever the desk is doing."""

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "stop")

    async def async_press(self) -> None:
        await self.desk.async_stop()


class ResetButton(TimotionDeskEntity, ButtonEntity):
    """Run the control box's height reset.

    The desk drives to its lowest point and re-measures its height, like holding
    both handset arrows. Harmless but disruptive, so it is off until you enable it.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "reset")

    async def async_press(self) -> None:
        await self.desk.async_reset()
