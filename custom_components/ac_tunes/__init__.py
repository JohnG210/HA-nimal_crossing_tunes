"""Animal Crossing Tunes - Home Assistant integration."""
from __future__ import annotations

import logging
import random
from datetime import datetime

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.network import get_url

from .const import (
    AUDIO_LOCAL,
    CONF_AUDIO_SOURCE,
    CONF_GAME,
    CONF_KK_VERSION,
    CONF_LOCAL_PATH,
    CONF_MEDIA_PLAYER,
    CONF_MUSIC_VOLUME,
    CONF_TOWN_TUNE_PLAYER,
    CONF_TOWN_TUNE_VOLUME,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_MODE,
    DEFAULT_GAME,
    DEFAULT_KK_VERSION,
    DEFAULT_WEATHER_MODE,
    DOMAIN,
    GAME_RANDOM,
    GAMES,
    KK_LIVE,
    WEATHER_LIVE,
    WEATHER_RANDOM,
    WEATHER_SUNNY,
)
from .coordinator import ACTunesCoordinator
from .music_data import (
    get_available_weathers,
    get_hourly_url,
    get_hourly_url_local,
    get_kk_url,
    get_kk_url_local,
    map_weather_state,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch"]

SERVICE_PLAY_HOURLY = "play_hourly"
SERVICE_PLAY_KK = "play_kk"
SERVICE_PLAY_TOWN_TUNE = "play_town_tune"
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

    # Generate the town tune WAV file so it's ready for playback
    await hass.async_add_executor_job(_generate_town_tune, hass)

    coordinator = ACTunesCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Forward to switch platform for the auto-play toggle
    # (playback doesn't start until the user turns the switch on)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once — check for the newest service to detect stale registrations)
    if not hass.services.has_service(DOMAIN, SERVICE_PLAY_TOWN_TUNE):
        _register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _generate_town_tune(hass: HomeAssistant) -> None:
    """Generate the town tune WAV in the www directory (runs in executor)."""
    from .town_tune import generate_town_tune_wav

    wav_path = hass.config.path("www", "ac_tunes", "town_tune.wav")
    generate_town_tune_wav(output_path=wav_path)
    _LOGGER.info("Town tune WAV generated at %s", wav_path)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        await data["coordinator"].async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove services if no entries remain
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_PLAY_HOURLY)
        hass.services.async_remove(DOMAIN, SERVICE_PLAY_KK)
        hass.services.async_remove(DOMAIN, SERVICE_PLAY_TOWN_TUNE)
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

        weather = _resolve_weather(
            hass, cfg, game, call.data.get("weather")
        )

        hour = now.hour

        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            url = get_hourly_url_local(
                game, weather, hour, cfg.get(CONF_LOCAL_PATH, "")
            )
        else:
            url = get_hourly_url(game, weather, hour)

        await _set_volume(hass, entity_id, cfg.get(CONF_MUSIC_VOLUME))

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

        await _set_volume(hass, entity_id, cfg.get(CONF_MUSIC_VOLUME))

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

    async def handle_play_town_tune(call: ServiceCall) -> None:
        """Play the town tune, then start the current hour's track."""
        import asyncio

        entity_id = call.data["entity_id"]
        cfg = _get_config(hass)

        # Play the town tune WAV
        try:
            base = get_url(hass)
        except Exception:  # noqa: BLE001
            base = "http://homeassistant.local:8123"
        town_tune_url = f"{base}/local/ac_tunes/town_tune.wav"

        # Use the dedicated town tune player if configured (e.g. underlying
        # Apple TV when main player is Music Assistant)
        tune_player = cfg.get(CONF_TOWN_TUNE_PLAYER) or entity_id
        # Use a separate player for the tune when configured (MA workaround)
        uses_separate_player = tune_player != entity_id

        try:
            await _set_volume(hass, tune_player, cfg.get(CONF_TOWN_TUNE_VOLUME))
            await hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": tune_player,
                    "media_content_id": town_tune_url,
                    "media_content_type": "music",
                },
                blocking=not uses_separate_player,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to play town tune")

        # Wait for town tune to finish (~5.2s + buffer)
        await asyncio.sleep(7.0)

        # Now play the current hour's track on the main player
        now = datetime.now()
        game = call.data.get("game") or cfg.get(CONF_GAME, DEFAULT_GAME)
        if game == GAME_RANDOM:
            game = random.choice(list(GAMES.keys()))  # noqa: S311

        weather = _resolve_weather(
            hass, cfg, game, call.data.get("weather")
        )

        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            url = get_hourly_url_local(
                game, weather, now.hour, cfg.get(CONF_LOCAL_PATH, "")
            )
        else:
            url = get_hourly_url(game, weather, now.hour)

        _LOGGER.info("Playing hourly track: %s", url)
        try:
            await _set_volume(hass, entity_id, cfg.get(CONF_MUSIC_VOLUME))
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
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Failed to play hourly track after town tune")

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
        DOMAIN,
        SERVICE_PLAY_TOWN_TUNE,
        handle_play_town_tune,
        schema=PLAY_HOURLY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_STOP, handle_stop, schema=STOP_SCHEMA
    )


async def _set_volume(hass: HomeAssistant, entity_id: str, volume_pct: int | None) -> None:
    """Set volume on a media player if a value is configured."""
    if volume_pct is None:
        return
    volume = max(0.0, min(1.0, volume_pct / 100.0))
    try:
        await hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": entity_id, "volume_level": volume},
            blocking=True,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not set volume on %s", entity_id)


def _resolve_weather(hass: HomeAssistant, cfg: dict, game: str, override: str | None = None) -> str:
    """Resolve weather mode to an actual weather variant for URL building."""
    if override and override not in (WEATHER_LIVE, WEATHER_RANDOM):
        return override
    mode = override or cfg.get(CONF_WEATHER_MODE, DEFAULT_WEATHER_MODE)
    available = get_available_weathers(game)
    if mode == WEATHER_LIVE:
        weather_entity = cfg.get(CONF_WEATHER_ENTITY)
        if weather_entity:
            state = hass.states.get(weather_entity)
            if state:
                mapped = map_weather_state(state.state)
                if mapped in available:
                    return mapped
        return WEATHER_SUNNY
    if mode == WEATHER_RANDOM:
        return random.choice(available)  # noqa: S311
    if mode in available:
        return mode
    return available[0]


def _get_config(hass: HomeAssistant) -> dict:
    """Get the merged config from the first config entry."""
    entries = hass.data.get(DOMAIN, {})
    for entry_data in entries.values():
        coordinator = entry_data.get("coordinator")
        if coordinator:
            return coordinator.config
    return {}
