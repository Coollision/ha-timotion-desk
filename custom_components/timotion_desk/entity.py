"""Shared base entity."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import TimotionDesk


class TimotionDeskEntity(Entity):
    """Push entity: state comes from the desk's notifications, never polled."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, desk: TimotionDesk, key: str) -> None:
        self.desk = desk
        self._attr_unique_id = f"{desk.address}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, desk.address)},
            connections={(CONNECTION_BLUETOOTH, desk.address)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=desk.name,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.desk.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
