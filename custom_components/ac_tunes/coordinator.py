"""Hourly playback coordinator for Animal Crossing Tunes."""
from __future__ import annotations

import logging
import random
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import (
    AUDIO_LOCAL,
    CONF_AUDIO_SOURCE,
    CONF_GAME,
    CONF_KK_SCHEDULE,
    CONF_KK_VERSION,
    CONF_LOCAL_PATH,
    CONF_MEDIA_PLAYER,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_MODE,
    DEFAULT_GAME,
    DEFAULT_KK_SCHEDULE,
    DEFAULT_KK_VERSION,
    DEFAULT_WEATHER_MODE,
    DOMAIN,
    GAME_RANDOM,
    GAMES,
    GAME_WEATHER_VARIANTS,
    KK_AIRCHECK,
    KK_ALWAYS,
    KK_LIVE,
    KK_SATURDAYS,
    WEATHER_LIVE,
    WEATHER_RANDOM,
    WEATHER_SUNNY,
)
from .music_data import (
    get_available_weathers,
    get_hourly_url,
    get_hourly_url_local,
    get_kk_url,
    get_kk_url_local,
    get_random_kk_song,
    map_weather_state,
)

_LOGGER = logging.getLogger(__name__)


class ACTunesCoordinator:
    """Coordinate hourly music playback."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.enabled = False
        self._unsub_hourly: CALLBACK_TYPE | None = None

    @property
    def config(self) -> dict:
        """Return merged config (entry data + options)."""
        return {**self.entry.data, **self.entry.options}

    def start(self) -> None:
        """Start hourly tracking."""
        if self._unsub_hourly is not None:
            return
        self.enabled = True
        self._unsub_hourly = async_track_time_change(
            self.hass, self._on_hour_change, minute=0, second=0
        )
        _LOGGER.debug("AC Tunes hourly coordinator started")

    def stop(self) -> None:
        """Stop hourly tracking."""
        self.enabled = False
        if self._unsub_hourly is not None:
            self._unsub_hourly()
            self._unsub_hourly = None
        _LOGGER.debug("AC Tunes hourly coordinator stopped")

    @callback
    def _on_hour_change(self, now: datetime) -> None:
        """Handle the hour changing."""
        if not self.enabled:
            return
        self.hass.async_create_task(self._play_for_hour(now))

    async def _play_for_hour(self, now: datetime) -> None:
        """Determine and play the appropriate track for the current hour."""
        cfg = self.config
        entity_id = cfg.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            _LOGGER.warning("No media player configured, skipping hourly play")
            return

        hour = now.hour

        # Check if we should play K.K. Slider instead
        if self._should_play_kk(cfg, now):
            await self._play_kk(cfg, entity_id)
            return

        # Resolve game
        game = cfg.get(CONF_GAME, DEFAULT_GAME)
        if game == GAME_RANDOM:
            game = random.choice(list(GAMES.keys()))  # noqa: S311

        # Resolve weather
        weather = self._resolve_weather(cfg, game)

        # Build URL
        url = self._build_hourly_url(cfg, game, weather, hour)

        _LOGGER.info("Playing %s/%s hour %d on %s", game, weather, hour, entity_id)
        await self._call_play_media(entity_id, url)

    def _should_play_kk(self, cfg: dict, now: datetime) -> bool:
        """Check if K.K. Slider should play based on schedule."""
        schedule = cfg.get(CONF_KK_SCHEDULE, DEFAULT_KK_SCHEDULE)
        if schedule == KK_ALWAYS:
            return True
        if schedule == KK_SATURDAYS:
            # Saturday = 5 in weekday(), 8pm-midnight
            return now.weekday() == 5 and now.hour >= 20
        return False

    async def _play_kk(self, cfg: dict, entity_id: str) -> None:
        """Play a random K.K. Slider song."""
        song = get_random_kk_song()
        version = cfg.get(CONF_KK_VERSION, DEFAULT_KK_VERSION)

        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            local_path = cfg.get(CONF_LOCAL_PATH, "")
            url = get_kk_url_local(song, version, local_path)
        else:
            url = get_kk_url(song, version)

        _LOGGER.info("Playing K.K. Slider: %s (%s) on %s", song, version, entity_id)
        await self._call_play_media(entity_id, url)

    def _resolve_weather(self, cfg: dict, game: str) -> str:
        """Resolve the weather variant to use."""
        mode = cfg.get(CONF_WEATHER_MODE, DEFAULT_WEATHER_MODE)
        available = get_available_weathers(game)

        if mode == WEATHER_LIVE:
            weather_entity = cfg.get(CONF_WEATHER_ENTITY)
            if weather_entity:
                state = self.hass.states.get(weather_entity)
                if state:
                    mapped = map_weather_state(state.state)
                    if mapped in available:
                        return mapped
            # Fallback to sunny if live weather unavailable
            return WEATHER_SUNNY

        if mode == WEATHER_RANDOM:
            return random.choice(available)  # noqa: S311

        # Static weather mode - ensure it's available for this game
        if mode in available:
            return mode
        return available[0]

    def _build_hourly_url(
        self, cfg: dict, game: str, weather: str, hour: int
    ) -> str:
        """Build the URL for the hourly track."""
        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            local_path = cfg.get(CONF_LOCAL_PATH, "")
            return get_hourly_url_local(game, weather, hour, local_path)
        return get_hourly_url(game, weather, hour)

    async def _call_play_media(self, entity_id: str, url: str) -> None:
        """Call the media_player.play_media service."""
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_id": url,
                "media_content_type": "music",
            },
            blocking=True,
        )
