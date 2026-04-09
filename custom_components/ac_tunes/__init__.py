"""Animal Crossing Tunes - Home Assistant integration."""
from __future__ import annotations

import logging
import random
from datetime import datetime

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    AUDIO_LOCAL,
    CONF_AUDIO_SOURCE,
    CONF_GAME,
    CONF_KK_VERSION,
    CONF_LOCAL_PATH,
    CONF_WEATHER_MODE,
    DEFAULT_GAME,
    DEFAULT_KK_VERSION,
    DEFAULT_WEATHER_MODE,
    DOMAIN,
    GAME_RANDOM,
    GAMES,
    KK_LIVE,
)
from .coordinator import ACTunesCoordinator
from .music_data import (
    get_hourly_url,
    get_hourly_url_local,
    get_kk_url,
    get_kk_url_local,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch"]

SERVICE_PLAY_HOURLY = "play_hourly"
SERVICE_PLAY_KK = "play_kk"
SERVICE_STOP = "stop"

PLAY_HOURLY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("game"): cv.string,
        vol.Optional("weather"): cv.string,
    }
)

PLAY_KK_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("song_name"): cv.string,
        vol.Optional("version", default=KK_LIVE): cv.string,
    }
)

STOP_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Animal Crossing Tunes from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = ACTunesCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Start the hourly coordinator
    coordinator.start()

    # Forward to switch platform for the auto-play toggle
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_PLAY_HOURLY):
        _register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        data["coordinator"].stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove services if no entries remain
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_PLAY_HOURLY)
        hass.services.async_remove(DOMAIN, SERVICE_PLAY_KK)
        hass.services.async_remove(DOMAIN, SERVICE_STOP)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_play_hourly(call: ServiceCall) -> None:
        """Handle the play_hourly service call."""
        entity_id = call.data["entity_id"]
        now = datetime.now()

        # Get config from first entry if available
        cfg = _get_config(hass)

        game = call.data.get("game") or cfg.get(CONF_GAME, DEFAULT_GAME)
        if game == GAME_RANDOM:
            game = random.choice(list(GAMES.keys()))  # noqa: S311

        weather = call.data.get("weather") or cfg.get(
            CONF_WEATHER_MODE, DEFAULT_WEATHER_MODE
        )

        hour = now.hour

        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            url = get_hourly_url_local(
                game, weather, hour, cfg.get(CONF_LOCAL_PATH, "")
            )
        else:
            url = get_hourly_url(game, weather, hour)

        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_id": url,
                "media_content_type": "music",
            },
            blocking=True,
        )

    async def handle_play_kk(call: ServiceCall) -> None:
        """Handle the play_kk service call."""
        entity_id = call.data["entity_id"]
        song_name = call.data["song_name"]
        version = call.data.get("version", KK_LIVE)

        cfg = _get_config(hass)

        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            url = get_kk_url_local(
                song_name, version, cfg.get(CONF_LOCAL_PATH, "")
            )
        else:
            url = get_kk_url(song_name, version)

        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_id": url,
                "media_content_type": "music",
            },
            blocking=True,
        )

    async def handle_stop(call: ServiceCall) -> None:
        """Handle the stop service call."""
        entity_id = call.data["entity_id"]
        await hass.services.async_call(
            "media_player",
            "media_stop",
            {"entity_id": entity_id},
            blocking=True,
        )

    hass.services.async_register(
        DOMAIN, SERVICE_PLAY_HOURLY, handle_play_hourly, schema=PLAY_HOURLY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PLAY_KK, handle_play_kk, schema=PLAY_KK_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_STOP, handle_stop, schema=STOP_SCHEMA
    )


def _get_config(hass: HomeAssistant) -> dict:
    """Get the merged config from the first config entry."""
    entries = hass.data.get(DOMAIN, {})
    for entry_data in entries.values():
        coordinator = entry_data.get("coordinator")
        if coordinator:
            return coordinator.config
    return {}
