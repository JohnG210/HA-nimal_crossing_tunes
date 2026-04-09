"""Continuous playback coordinator for Animal Crossing Tunes.

Behaves like the original AC Music Extension:
  1. When enabled, immediately starts playing the current hour's track.
  2. Loops the track continuously by re-triggering when it ends.
  3. At the top of each hour, plays the town tune then transitions
     to the new hour's track.
  4. On Saturday nights (8pm-midnight), plays K.K. Slider instead.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_IDLE, STATE_OFF, STATE_PAUSED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.network import get_url

from .const import (
    AUDIO_LOCAL,
    CONF_AUDIO_SOURCE,
    CONF_GAME,
    CONF_KK_SCHEDULE,
    CONF_KK_VERSION,
    CONF_LOCAL_PATH,
    CONF_MEDIA_PLAYER,
    CONF_TOWN_TUNE_PLAYER,
    CONF_MUSIC_VOLUME,
    CONF_TOWN_TUNE_VOLUME,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_MODE,
    DEFAULT_GAME,
    DEFAULT_KK_SCHEDULE,
    DEFAULT_KK_VERSION,
    DEFAULT_WEATHER_MODE,
    DOMAIN,
    GAME_RANDOM,
    GAMES,
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

# How long to wait after player goes idle before re-triggering (seconds).
# This avoids fighting with brief state transitions during playback start.
RELOOP_DELAY = 2.0

# How long the town tune plays before we start the hourly track (seconds).
TOWN_TUNE_DURATION = 6.0


class ACTunesCoordinator:
    """Coordinate continuous hourly music playback."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.enabled = False

        # Currently playing URL so we know what to re-loop
        self._current_url: str | None = None
        # Flag to suppress re-loop when we intentionally stop
        self._intentional_stop = False
        # Flag to suppress re-loop during hour transition
        self._transitioning = False

        self._unsub_hourly: CALLBACK_TYPE | None = None
        self._unsub_state: CALLBACK_TYPE | None = None
        self._reloop_task: asyncio.Task | None = None

    @property
    def config(self) -> dict:
        """Return merged config (entry data + options)."""
        return {**self.entry.data, **self.entry.options}

    async def async_start(self) -> None:
        """Start continuous playback."""
        if self.enabled:
            return
        self.enabled = True

        # Listen for hour changes
        self._unsub_hourly = async_track_time_change(
            self.hass, self._on_hour_change, minute=0, second=0
        )

        # Watch the media player state for looping
        entity_id = self.config.get(CONF_MEDIA_PLAYER)
        if entity_id:
            self._unsub_state = async_track_state_change_event(
                self.hass, [entity_id], self._on_player_state_change
            )

        # Immediately play the current hour's track
        await self._play_current_hour()

        _LOGGER.info("AC Tunes continuous playback started")

    async def async_stop(self) -> None:
        """Stop continuous playback and stop the media player."""
        self.enabled = False
        self._intentional_stop = True
        self._current_url = None

        # Cancel pending re-loop
        if self._reloop_task and not self._reloop_task.done():
            self._reloop_task.cancel()
            self._reloop_task = None

        # Unsubscribe listeners
        if self._unsub_hourly:
            self._unsub_hourly()
            self._unsub_hourly = None
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None

        # Stop the media player
        entity_id = self.config.get(CONF_MEDIA_PLAYER)
        if entity_id:
            try:
                await self.hass.services.async_call(
                    "media_player",
                    "media_stop",
                    {"entity_id": entity_id},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not stop media player on disable")

        _LOGGER.info("AC Tunes continuous playback stopped")

    # ── Hour change handling ───────────────────────────────────────

    @callback
    def _on_hour_change(self, now: datetime) -> None:
        """Handle the hour changing — play town tune then new track."""
        if not self.enabled:
            return
        self.hass.async_create_task(self._transition_to_new_hour(now))

    async def _transition_to_new_hour(self, now: datetime) -> None:
        """Play the town tune, then start the new hour's track."""
        cfg = self.config
        entity_id = cfg.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            return

        self._transitioning = True

        # Play town tune
        town_tune_url = self._get_town_tune_url()
        if town_tune_url:
            _LOGGER.info("Playing town tune before hour transition")
            try:
                tune_player = cfg.get(CONF_TOWN_TUNE_PLAYER) or entity_id
                await self._set_volume(tune_player, cfg.get(CONF_TOWN_TUNE_VOLUME))
                await self._play_town_tune(entity_id, town_tune_url)
                # Wait for the town tune to finish
                await asyncio.sleep(TOWN_TUNE_DURATION)
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Failed to play town tune, skipping")

        self._transitioning = False

        # Now play the new hour's track (retry once if MA is still settling)
        try:
            await self._play_current_hour()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("First attempt to play hourly track failed, retrying")
            await asyncio.sleep(2.0)
            await self._play_current_hour()

    # ── Playback ───────────────────────────────────────────────────

    async def _play_current_hour(self) -> None:
        """Play the appropriate track for the current hour."""
        cfg = self.config
        entity_id = cfg.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            _LOGGER.warning("No media player configured")
            return

        now = datetime.now()

        # K.K. Slider check
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
        url = self._build_hourly_url(cfg, game, weather, now.hour)

        self._intentional_stop = False
        self._current_url = url

        await self._set_volume(entity_id, cfg.get(CONF_MUSIC_VOLUME))

        _LOGGER.info(
            "Playing %s/%s hour %d on %s", game, weather, now.hour, entity_id
        )
        await self._call_play_media(entity_id, url)

        # Try to set repeat mode for players that support it
        await self._try_set_repeat(entity_id)

    async def _play_kk(self, cfg: dict, entity_id: str) -> None:
        """Play a random K.K. Slider song."""
        song = get_random_kk_song()
        version = cfg.get(CONF_KK_VERSION, DEFAULT_KK_VERSION)

        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            url = get_kk_url_local(song, version, cfg.get(CONF_LOCAL_PATH, ""))
        else:
            url = get_kk_url(song, version)

        self._intentional_stop = False
        self._current_url = url

        await self._set_volume(entity_id, cfg.get(CONF_MUSIC_VOLUME))

        _LOGGER.info("Playing K.K. Slider: %s (%s) on %s", song, version, entity_id)
        await self._call_play_media(entity_id, url)

    # ── Looping via state monitoring ───────────────────────────────

    @callback
    def _on_player_state_change(self, event: Event) -> None:
        """Handle media player state changes for looping."""
        if not self.enabled or self._intentional_stop or self._transitioning:
            return

        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        _LOGGER.debug(
            "Player state change: %s -> %s (url=%s)",
            old_state.state,
            new_state.state,
            self._current_url,
        )

        # If the player went from playing to idle/off/paused, the track ended
        if (
            old_state.state == "playing"
            and new_state.state in (STATE_IDLE, STATE_OFF, STATE_PAUSED)
            and self._current_url
        ):
            # Schedule a re-loop with a small delay to avoid rapid cycling
            if self._reloop_task and not self._reloop_task.done():
                self._reloop_task.cancel()
            self._reloop_task = self.hass.async_create_task(
                self._reloop_after_delay()
            )

    async def _reloop_after_delay(self) -> None:
        """Wait briefly then re-trigger the current track."""
        await asyncio.sleep(RELOOP_DELAY)

        if not self.enabled or self._intentional_stop or not self._current_url:
            return

        entity_id = self.config.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            return

        # Check the player is still idle (not playing something else)
        state = self.hass.states.get(entity_id)
        if state and state.state in (STATE_IDLE, STATE_OFF, STATE_PAUSED):
            _LOGGER.debug("Re-looping track: %s", self._current_url)
            await self._call_play_media(entity_id, self._current_url)

    # ── Helpers ────────────────────────────────────────────────────

    async def _set_volume(self, entity_id: str, volume_pct: int | None) -> None:
        """Set volume on the media player if a value is configured."""
        if volume_pct is None:
            return
        volume = max(0.0, min(1.0, volume_pct / 100.0))
        try:
            await self.hass.services.async_call(
                "media_player",
                "volume_set",
                {"entity_id": entity_id, "volume_level": volume},
                blocking=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not set volume on %s", entity_id)

    async def _play_town_tune(self, entity_id: str, url: str) -> None:
        """Play the town tune on the configured player.

        If a separate town_tune_player is configured (e.g. the underlying
        Apple TV when using Music Assistant), use that instead.
        """
        cfg = self.config
        tune_player = cfg.get(CONF_TOWN_TUNE_PLAYER) or entity_id
        _LOGGER.debug("Playing town tune on %s", tune_player)
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": tune_player,
                "media_content_id": url,
                "media_content_type": "music",
            },
            blocking=False,
        )

    async def _try_set_repeat(self, entity_id: str) -> None:
        """Try to set repeat mode to 'one' on the media player."""
        try:
            state = self.hass.states.get(entity_id)
            if state and "repeat" in (
                state.attributes.get("supported_features_names", [])
            ):
                await self.hass.services.async_call(
                    "media_player",
                    "repeat_set",
                    {"entity_id": entity_id, "repeat": "one"},
                    blocking=False,
                )
        except Exception:  # noqa: BLE001
            # Not all players support repeat — that's fine, we loop via state
            pass

    def _should_play_kk(self, cfg: dict, now: datetime) -> bool:
        """Check if K.K. Slider should play based on schedule."""
        schedule = cfg.get(CONF_KK_SCHEDULE, DEFAULT_KK_SCHEDULE)
        if schedule == KK_ALWAYS:
            return True
        if schedule == KK_SATURDAYS:
            return now.weekday() == 5 and now.hour >= 20
        return False

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
            return WEATHER_SUNNY

        if mode == WEATHER_RANDOM:
            return random.choice(available)  # noqa: S311

        if mode in available:
            return mode
        return available[0]

    def _build_hourly_url(
        self, cfg: dict, game: str, weather: str, hour: int
    ) -> str:
        """Build the URL for the hourly track."""
        if cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL:
            return get_hourly_url_local(
                game, weather, hour, cfg.get(CONF_LOCAL_PATH, "")
            )
        return get_hourly_url(game, weather, hour)

    def _get_town_tune_url(self) -> str | None:
        """Get the full URL for the town tune WAV file.

        Uses the full http:// URL so it works with all media players
        including those behind Music Assistant.
        """
        wav_path = self.hass.config.path("www", "ac_tunes", "town_tune.wav")
        if not os.path.isfile(wav_path):
            return None
        # Build full URL from HA's internal/external URL
        try:
            base = get_url(self.hass)
        except Exception:  # noqa: BLE001
            base = "http://homeassistant.local:8123"
        return f"{base}/local/ac_tunes/town_tune.wav"

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
