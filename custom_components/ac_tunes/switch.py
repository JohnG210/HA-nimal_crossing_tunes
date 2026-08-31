"""Switch platform for Animal Crossing Tunes auto-play toggle."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.start import async_at_started

from .const import CONF_TOWN_TUNE, DOMAIN
from .town_tune import DEFAULT_TOWN_TUNE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AC Tunes auto-play switch."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ACTunesAutoPlaySwitch(coordinator, entry)])


class ACTunesAutoPlaySwitch(SwitchEntity, RestoreEntity):
    """Switch to toggle continuous hourly auto-play."""

    _attr_has_entity_name = True
    _attr_name = "Auto-Play"
    _attr_icon = "mdi:music-note"
    _attr_should_poll = False

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

    async def async_turn_off(self, **kwargs) -> None:
        """Disable auto-play — stops the media player."""
        await self._coordinator.async_stop()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register listeners and restore the previous auto-play state."""
        await super().async_added_to_hass()
        self._coordinator.register_state_listener(self.async_write_ha_state)

        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state != STATE_ON:
            return

        async def _resume(_hass: HomeAssistant) -> None:
            """Resume playback once Home Assistant has finished starting.

            Deferred so the configured media player exists by the time we
            try to play to it — otherwise a restart or an options change
            would silently leave auto-play switched off.
            """
            try:
                await self._coordinator.async_start()
            except HomeAssistantError as err:
                _LOGGER.warning("Could not resume AC Tunes auto-play: %s", err)
            self.async_write_ha_state()

        self.async_on_remove(async_at_started(self.hass, _resume))

    @property
    def extra_state_attributes(self) -> dict:
        """Expose playback state and town tune for Lovelace cards."""
        cfg = self._coordinator.config
        return {
            "town_tune": cfg.get(CONF_TOWN_TUNE, DEFAULT_TOWN_TUNE),
            "current_game": self._coordinator.current_game,
            "current_weather": self._coordinator.current_weather,
            "is_playing": self._coordinator.enabled,
        }
