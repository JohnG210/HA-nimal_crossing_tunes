"""Switch platform for Animal Crossing Tunes auto-play toggle."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_TOWN_TUNE, DOMAIN
from .town_tune import DEFAULT_TOWN_TUNE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC Tunes auto-play switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ACTunesAutoPlaySwitch(coordinator, entry)])


class ACTunesAutoPlaySwitch(SwitchEntity):
    """Switch to toggle continuous hourly auto-play."""

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
        """Enable auto-play — starts continuous playback immediately."""
        await self._coordinator.async_start()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state listener when entity is added to HA."""
        self._coordinator.register_state_listener(self.async_write_ha_state)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose playback state and town tune for Lovelace cards."""
        cfg = self._coordinator.config
        return {
            "town_tune": cfg.get(CONF_TOWN_TUNE, DEFAULT_TOWN_TUNE),
            "current_game": self._coordinator._current_game,
            "current_weather": self._coordinator._current_weather,
            "is_playing": self._coordinator.enabled,
        }

    async def async_turn_off(self, **kwargs) -> None:
        """Disable auto-play — stops the media player."""
        await self._coordinator.async_stop()
        self.async_write_ha_state()
