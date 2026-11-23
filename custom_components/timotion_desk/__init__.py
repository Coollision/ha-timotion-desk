"""TiMotion Desk: height and control of sit-stand desks with a TiMotion TWD1 Bluetooth module."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import TimotionDesk

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

type TimotionDeskConfigEntry = ConfigEntry[TimotionDesk]


async def async_setup_entry(hass: HomeAssistant, entry: TimotionDeskConfigEntry) -> bool:
    """Set up a desk from a config entry."""
    desk = TimotionDesk(hass, entry)
    entry.runtime_data = desk
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await desk.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TimotionDeskConfigEntry) -> bool:
    """Unload a desk."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unloaded
