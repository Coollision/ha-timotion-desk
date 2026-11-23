"""Number: drive the desk to any height."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TimotionDeskConfigEntry
from .coordinator import TimotionDesk
from .entity import TimotionDeskEntity
from .protocol import HEIGHT_MAX_CM, HEIGHT_MIN_CM


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TimotionDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TargetHeight(entry.runtime_data)])


class TargetHeight(TimotionDeskEntity, NumberEntity):
    """Shows the target while moving, otherwise the current height."""

    _attr_device_class = NumberDeviceClass.DISTANCE
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_native_min_value = HEIGHT_MIN_CM
    _attr_native_max_value = HEIGHT_MAX_CM
    _attr_native_step = 1

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "target_height")

    @property
    def native_value(self) -> float | None:
        if self.desk.target_cm is not None:
            return self.desk.target_cm
        return self.desk.status.height_cm if self.desk.status else None

    async def async_set_native_value(self, value: float) -> None:
        await self.desk.async_move_to(round(value))
