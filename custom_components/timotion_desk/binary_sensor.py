"""Binary sensors: moving, collision, connected."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    async_add_entities([MovingSensor(desk), CollisionSensor(desk), ConnectedSensor(desk)])


class MovingSensor(TimotionDeskEntity, BinarySensorEntity):
    """On while the motors run, whoever started the move (handset, app or HA)."""

    _attr_device_class = BinarySensorDeviceClass.MOVING

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "moving")

    @property
    def is_on(self) -> bool | None:
        return self.desk.status.moving if self.desk.status else None


class CollisionSensor(TimotionDeskEntity, BinarySensorEntity):
    """On while the anti-collision sensor has tripped and the desk is reversing."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "collision")

    @property
    def is_on(self) -> bool | None:
        return self.desk.status.collision if self.desk.status else None


class ConnectedSensor(TimotionDeskEntity, BinarySensorEntity):
    """Whether we currently hold the desk's single Bluetooth connection."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "connected")

    @property
    def is_on(self) -> bool:
        return self.desk.connected
