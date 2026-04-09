"""Switch platform for Animal Crossing Tunes auto-play toggle."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC Tunes auto-play switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ACTunesAutoPlaySwitch(coordinator, entry)])


class ACTunesAutoPlaySwitch(SwitchEntity):
    """Switch to toggle hourly auto-play."""

    _attr_has_entity_name = True
    _attr_name = "Auto-Play"
    _attr_icon = "mdi:music-note"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_auto_play"
        self._attr_device_info = None

    @property
    def is_on(self) -> bool:
        """Return true if auto-play is enabled."""
        return self._coordinator.enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable auto-play."""
        self._coordinator.start()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable auto-play."""
        self._coordinator.stop()
        self.async_write_ha_state()
