"""Select: pick a named height preset and the desk drives there."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TimotionDeskConfigEntry
from .const import PRESET_MATCH_TOLERANCE_CM
from .coordinator import TimotionDesk
from .entity import TimotionDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TimotionDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([PresetSelect(entry.runtime_data)])


class PresetSelect(TimotionDeskEntity, SelectEntity):
    """Presets live in the integration options, so there is no fixed number of them.

    Changing them reloads the entry, which rebuilds this list.
    """

    def __init__(self, desk: TimotionDesk) -> None:
        super().__init__(desk, "preset")

    @property
    def options(self) -> list[str]:
        return [preset.name for preset in self.desk.presets]

    @property
    def current_option(self) -> str | None:
        """The preset whose height the desk is at (None between presets)."""
        status = self.desk.status
        if status is None or status.height_cm is None or status.moving:
            return None
        for preset in self.desk.presets:
            if abs(preset.height - status.height_cm) <= PRESET_MATCH_TOLERANCE_CM:
                return preset.name
        return None

    async def async_select_option(self, option: str) -> None:
        for preset in self.desk.presets:
            if preset.name == option:
                await self.desk.async_move_to(preset.height)
                return
        raise ServiceValidationError(f"Unknown preset: {option}")
