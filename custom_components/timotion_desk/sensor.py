"""Sensors: height and state."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TimotionDeskConfigEntry
from .coordinator import TimotionDesk
from .entity import TimotionDeskEntity

STATES = ["idle", "moving_up", "moving_down", "reset_mode"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TimotionDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    desk = entry.runtime_data
    async_add_entities([HeightSensor(desk), StateSensor(desk)])


class HeightSensor(TimotionDeskEntity, SensorEntity):
    """Current desk height."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_suggested_display_precision = 0

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "height")

    @property
    def native_value(self) -> int | None:
        # None while the control box is in reset mode (it reports a sentinel).
        return self.desk.status.height_cm if self.desk.status else None


class StateSensor(TimotionDeskEntity, SensorEntity):
    """What the desk is doing right now."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "state")

    @property
    def native_value(self) -> str | None:
        status = self.desk.status
        if status is None:
            return None
        if status.reset_mode:
            return "reset_mode"
        return f"moving_{status.direction}" if status.moving else "idle"
