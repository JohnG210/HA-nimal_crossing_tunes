"""HA-nimal Crossing Tunes - Home Assistant integration."""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime

import voluptuous as vol

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service as service_helper

# Home Assistant moved target resolution from `helpers.service` to
# `helpers.target` and dropped the old name in 2026.8. Support both so the
# integration keeps working across the HA versions we claim to support.
try:
    from homeassistant.helpers import target as _target_helper
except ImportError:  # pragma: no cover - Home Assistant before the move
    _target_helper = None

_EXTRACT_REFERENCED = getattr(
    _target_helper, "async_extract_referenced_entity_ids", None
)
_TARGET_SELECTION = getattr(_target_helper, "TargetSelection", None) or getattr(
    _target_helper, "TargetSelectorData", None
)

from . import player
from .const import (
    CONF_GAME,
    CONF_GAMES,
    CONF_MUSIC_VOLUME,
    CONF_TOWN_TUNE,
    CONF_TOWN_TUNE_PLAYER,
    CONF_TOWN_TUNE_VOLUME,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_MODE,
    DEFAULT_GAMES,
    DEFAULT_WEATHER_MODE,
    DOMAIN,
    GAME_RANDOM,
    GAMES,
    KK_LIVE,
    WEATHER_LIVE,
    WEATHER_RANDOM,
    WEATHER_SUNNY,
)
from .coordinator import TOWN_TUNE_DURATION, ACTunesCoordinator
from .helpers import get_config as _get_config
from .music_data import get_available_weathers, map_weather_state
from .vaca_clock import async_revert_clock_on_stop, async_show_clock_after_playback

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["switch"]

SERVICE_PLAY_HOURLY = "play_hourly"
SERVICE_PLAY_KK = "play_kk"
SERVICE_PLAY_TOWN_TUNE = "play_town_tune"
SERVICE_SET_TOWN_TUNE = "set_town_tune"
SERVICE_STOP = "stop"

# Services accept the standard Home Assistant target selector, so a call can
# name an entity, a device or an area. The legacy `entity_id` field keeps
# working because targets are merged into the call data.
PLAY_HOURLY_SCHEMA = vol.Schema(
    {
        **cv.TARGET_SERVICE_FIELDS,
        vol.Optional("game"): cv.string,
        vol.Optional("weather"): cv.string,
    }
)

PLAY_KK_SCHEMA = vol.Schema(
    {
        **cv.TARGET_SERVICE_FIELDS,
        vol.Required("song_name"): cv.string,
        vol.Optional("version", default=KK_LIVE): cv.string,
    }
)

SET_TOWN_TUNE_SCHEMA = vol.Schema(
    {
        vol.Required("notes"): vol.All(
            cv.ensure_list, [cv.string], vol.Length(min=16, max=16)
        ),
    }
)

STOP_SCHEMA = vol.Schema({**cv.TARGET_SERVICE_FIELDS})


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry to a new version."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new_data = {**config_entry.data}
        new_options = {**config_entry.options}

        for d in (new_data, new_options):
            old_game = d.pop(CONF_GAME, None)
            if old_game is not None:
                if old_game == GAME_RANDOM:
                    d[CONF_GAMES] = list(GAMES.keys())
                else:
                    d[CONF_GAMES] = [old_game]

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options=new_options, version=2
        )
        _LOGGER.info("Migration to version 2 successful")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA-nimal Crossing Tunes from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Generate the town tune WAV only if one doesn't exist yet
    cfg = {**entry.data, **entry.options}
    town_tune_notes = cfg.get(CONF_TOWN_TUNE)
    wav_path = Path(hass.config.path("www", "ac_tunes", "town_tune.wav"))
    if not wav_path.exists():
        await hass.async_add_executor_job(_generate_town_tune, hass, town_tune_notes)

    # Serve the frontend cards (town tune editor + AC clock)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/ac_tunes", str(Path(__file__).parent / "www"), cache_headers=False
            )
        ]
    )

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


def _generate_town_tune(hass: HomeAssistant, notes: list[str] | None = None) -> None:
    """Generate the town tune WAV in the www directory (runs in executor)."""
    from .town_tune import generate_town_tune_wav

    wav_path = hass.config.path("www", "ac_tunes", "town_tune.wav")
    generate_town_tune_wav(notes=notes, output_path=wav_path)
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
        hass.services.async_remove(DOMAIN, SERVICE_SET_TOWN_TUNE)
        hass.services.async_remove(DOMAIN, SERVICE_STOP)

    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _target_players(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Resolve a service call target to media player entity ids.

    Handles entity, device and area targets alike, which is what lets an
    automation point at a satellite's device instead of hand-resolving its
    media player attribute.
    """
    if _EXTRACT_REFERENCED is not None and _TARGET_SELECTION is not None:
        selected = _EXTRACT_REFERENCED(hass, _TARGET_SELECTION(call.data))
    else:
        selected = service_helper.async_extract_referenced_entity_ids(hass, call)

    entity_ids = [
        entity_id
        for entity_id in (*selected.referenced, *selected.indirectly_referenced)
        if entity_id.startswith(f"{MEDIA_PLAYER_DOMAIN}.")
    ]

    if not entity_ids:
        raise ServiceValidationError(
            "No media player was targeted. Pick an entity, device or area "
            "that contains a media player."
        )

    # Deduplicate while keeping a stable order.
    return list(dict.fromkeys(entity_ids))


def _town_tune_media_id(hass: HomeAssistant) -> str | None:
    """Return the town tune media source id, if the WAV has been generated."""
    if not os.path.isfile(hass.config.path("www", "ac_tunes", "town_tune.wav")):
        _LOGGER.warning("No town tune has been generated yet")
        return None
    return player.build_town_tune_media_id()


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_play_hourly(call: ServiceCall) -> None:
        """Handle the play_hourly service call."""
        cfg = _get_config(hass)
        now = datetime.now()

        games = cfg.get(CONF_GAMES, DEFAULT_GAMES) or DEFAULT_GAMES
        game = call.data.get("game") or random.choice(games)  # noqa: S311
        weather = _resolve_weather(hass, cfg, game, call.data.get("weather"))

        media_id = player.build_hourly_media_id(game, weather, now.hour)

        for entity_id in _target_players(hass, call):
            await player.async_set_volume(
                hass, entity_id, cfg.get(CONF_MUSIC_VOLUME)
            )
            await player.async_play(hass, entity_id, media_id)
            await async_show_clock_after_playback(hass, cfg, entity_id)

    async def handle_play_kk(call: ServiceCall) -> None:
        """Handle the play_kk service call."""
        cfg = _get_config(hass)
        song_name = call.data["song_name"]
        version = call.data.get("version", KK_LIVE)

        media_id = player.build_kk_media_id(song_name, version)

        for entity_id in _target_players(hass, call):
            await player.async_set_volume(
                hass, entity_id, cfg.get(CONF_MUSIC_VOLUME)
            )
            await player.async_play(hass, entity_id, media_id)
            await async_show_clock_after_playback(hass, cfg, entity_id)

    async def handle_play_town_tune(call: ServiceCall) -> None:
        """Play the town tune, then start the current hour's track."""
        cfg = _get_config(hass)
        now = datetime.now()

        games = cfg.get(CONF_GAMES, DEFAULT_GAMES) or DEFAULT_GAMES
        game = call.data.get("game") or random.choice(games)  # noqa: S311
        weather = _resolve_weather(hass, cfg, game, call.data.get("weather"))

        hourly_id = player.build_hourly_media_id(game, weather, now.hour)
        tune_id = _town_tune_media_id(hass)

        for entity_id in _target_players(hass, call):
            # A separate tune player can be configured to route the chime to
            # the underlying device when the main player can't announce.
            tune_player = cfg.get(CONF_TOWN_TUNE_PLAYER) or entity_id
            announced = None

            if tune_id:
                try:
                    await player.async_set_volume(
                        hass, tune_player, cfg.get(CONF_TOWN_TUNE_VOLUME)
                    )
                    announced = await player.async_play(
                        hass, tune_player, tune_id, announce=True
                    )
                    if tune_player != entity_id:
                        # Playing elsewhere never interrupts the music.
                        announced = True
                    else:
                        # Do not trust the announce flag as proof of real
                        # ducking when playing on the same device as the
                        # music — see the matching note in coordinator.py's
                        # _play_town_tune for why.
                        announced = False
                except HomeAssistantError:
                    _LOGGER.warning(
                        "Failed to play town tune on %s", tune_player, exc_info=True
                    )

            if announced is False:
                # The player can't duck and resume, so wait the tune out
                # before replacing what it's playing.
                await asyncio.sleep(TOWN_TUNE_DURATION)

            _LOGGER.info("Playing %s/%s hour %d on %s", game, weather, now.hour, entity_id)
            try:
                await player.async_set_volume(
                    hass, entity_id, cfg.get(CONF_MUSIC_VOLUME)
                )
                await player.async_play(hass, entity_id, hourly_id)
                await async_show_clock_after_playback(hass, cfg, entity_id)
            except HomeAssistantError:
                _LOGGER.warning(
                    "Failed to play hourly track after town tune on %s",
                    entity_id,
                    exc_info=True,
                )

    async def handle_set_town_tune(call: ServiceCall) -> None:
        """Save a new town tune and regenerate the WAV."""
        from .town_tune import validate_town_tune

        notes = call.data["notes"]
        if not validate_town_tune(notes):
            _LOGGER.error("Invalid town tune notes: %s", notes)
            return

        # Save to the first config entry's options
        entries = hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry = entries[0]
            new_options = {**entry.options, CONF_TOWN_TUNE: notes}
            hass.config_entries.async_update_entry(entry, options=new_options)

        # Regenerate the WAV
        await hass.async_add_executor_job(_generate_town_tune, hass, notes)
        _LOGGER.info("Town tune updated: %s", notes)

    async def handle_stop(call: ServiceCall) -> None:
        """Handle the stop service call."""
        cfg = _get_config(hass)
        for entity_id in _target_players(hass, call):
            await player.async_stop(hass, entity_id)
            await async_revert_clock_on_stop(hass, cfg, entity_id)

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
        DOMAIN,
        SERVICE_SET_TOWN_TUNE,
        handle_set_town_tune,
        schema=SET_TOWN_TUNE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_STOP, handle_stop, schema=STOP_SCHEMA
    )


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
