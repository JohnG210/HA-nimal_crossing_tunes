"""Continuous playback coordinator for Animal Crossing Tunes.

Behaves like the original AC Music Extension:
  1. When enabled, immediately starts playing the current hour's track.
  2. Loops the track continuously by re-triggering when it ends.
  3. At the top of each hour, plays the town tune then transitions
     to the new hour's track.
  4. On Saturday nights (8pm-midnight), plays K.K. Slider instead.

All media player interaction goes through :mod:`.player`, and all tracks
are addressed with ``media-source://`` identifiers so Home Assistant core
resolves the URL and MIME type for whichever player is configured.
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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)

from . import player
from .const import (
    CONF_DURATION_TRACKING,
    CONF_GAMES,
    CONF_KK_SCHEDULE,
    CONF_KK_SHUFFLE_NO_REPEATS,
    CONF_KK_VERSION,
    CONF_MEDIA_PLAYER,
    CONF_MUSIC_VOLUME,
    CONF_SHUFFLES_PER_HOUR,
    CONF_SONG_DELAY,
    CONF_TOWN_TUNE_PLAYER,
    CONF_TOWN_TUNE_VOLUME,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_MODE,
    DEFAULT_GAMES,
    DEFAULT_KK_SCHEDULE,
    DEFAULT_KK_VERSION,
    DEFAULT_SHUFFLES_PER_HOUR,
    DEFAULT_SONG_DELAY,
    DEFAULT_WEATHER_MODE,
    KK_ALWAYS,
    KK_SATURDAYS,
    WEATHER_LIVE,
    WEATHER_RANDOM,
    WEATHER_SUNNY,
)
from .helpers import duration_key_hourly, duration_key_kk
from .music_data import (
    ALL_KK_SONGS,
    get_available_weathers,
    get_random_kk_song,
    map_weather_state,
)
from .track_durations import TRACK_DURATIONS
from .vaca_clock import async_show_clock_after_playback

_LOGGER = logging.getLogger(__name__)

# How long to wait after player goes idle before re-triggering (seconds).
# This avoids fighting with brief state transitions during playback start.
RELOOP_DELAY = 2.0

# How long the town tune plays before we start the hourly track (seconds).
# Only used when the player cannot announce, since an announcement blocks
# until it has finished on its own.
TOWN_TUNE_DURATION = 6.0

# Extra buffer before re-triggering to avoid cutting off the end (seconds).
DURATION_BUFFER = 3.0


class ACTunesCoordinator:
    """Coordinate continuous hourly music playback."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.enabled = False

        # Currently playing media source id so we know what to re-loop
        self._current_media_id: str | None = None
        # TRACK_DURATIONS key for the current track
        self._current_duration_key: str | None = None
        # Flag to suppress re-loop when we intentionally stop
        self._intentional_stop = False
        # Flag to suppress re-loop during hour transition
        self._transitioning = False

        self._unsub_hourly: CALLBACK_TYPE | None = None
        self._unsub_state: CALLBACK_TYPE | None = None
        self._reloop_task: asyncio.Task | None = None
        self._duration_timer_task: asyncio.Task | None = None
        self._shuffle_timers: list[asyncio.Task] = []
        self._current_game: str | None = None
        self._current_weather: str | None = None
        self._kk_played_songs: list[str] = []
        self._state_listeners: list = []

    @property
    def config(self) -> dict:
        """Return merged config (entry data + options)."""
        return {**self.entry.data, **self.entry.options}

    @property
    def current_game(self) -> str | None:
        """Return the game currently playing, if any."""
        return self._current_game

    @property
    def current_weather(self) -> str | None:
        """Return the weather variant currently playing, if any."""
        return self._current_weather

    def register_state_listener(self, listener) -> None:
        """Register a callback to be invoked when playback state changes."""
        self._state_listeners.append(listener)

    @callback
    def _notify_state_listeners(self) -> None:
        """Notify all registered listeners of a state change."""
        for listener in self._state_listeners:
            listener()

    async def async_start(self) -> None:
        """Start continuous playback."""
        if self.enabled:
            return

        entity_id = self.config.get(CONF_MEDIA_PLAYER)

        # Validate up front so a missing or renamed player raises instead of
        # leaving a switch that reads "on" while playing nothing.
        player.resolve_target(self.hass, entity_id)

        self.enabled = True
        self._intentional_stop = False

        # Listen for hour changes
        self._unsub_hourly = async_track_time_change(
            self.hass, self._on_hour_change, minute=0, second=0
        )

        # Watch the media player state for looping
        self._unsub_state = async_track_state_change_event(
            self.hass, [entity_id], self._on_player_state_change
        )

        # Immediately play the current hour's track
        try:
            await self._play_current_hour()
        except Exception:
            # Don't leave the coordinator half-started with listeners
            # registered and the switch reporting on.
            self._teardown()
            self.enabled = False
            self._notify_state_listeners()
            raise

        _LOGGER.info("AC Tunes continuous playback started on %s", entity_id)

    def _teardown(self) -> None:
        """Cancel pending work and unsubscribe listeners."""
        if self._reloop_task and not self._reloop_task.done():
            self._reloop_task.cancel()
        self._reloop_task = None

        if self._duration_timer_task and not self._duration_timer_task.done():
            self._duration_timer_task.cancel()
        self._duration_timer_task = None

        self._cancel_shuffle_timers()

        if self._unsub_hourly:
            self._unsub_hourly()
            self._unsub_hourly = None
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None

    async def async_stop(self) -> None:
        """Stop continuous playback and stop the media player."""
        self.enabled = False
        self._intentional_stop = True
        self._current_media_id = None
        self._current_duration_key = None
        self._current_game = None
        self._current_weather = None
        self._notify_state_listeners()

        self._teardown()

        await player.async_stop(self.hass, self.config.get(CONF_MEDIA_PLAYER))

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
        entity_id = self.config.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            return

        self._transitioning = True

        # Cancel any running duration timer and shuffle timers
        if self._duration_timer_task and not self._duration_timer_task.done():
            self._duration_timer_task.cancel()
            self._duration_timer_task = None
        self._cancel_shuffle_timers()

        try:
            try:
                announced = await self._play_town_tune(entity_id)
                if announced is not None and not announced:
                    # The player can't duck and resume on its own, so wait
                    # out the tune before replacing what it's playing.
                    await asyncio.sleep(TOWN_TUNE_DURATION)
            except HomeAssistantError:
                _LOGGER.warning("Failed to play town tune, skipping", exc_info=True)

            # Now play the new hour's track (retry once if MA is still settling)
            try:
                await self._play_current_hour()
            except HomeAssistantError:
                _LOGGER.warning(
                    "First attempt to play hourly track failed, retrying",
                    exc_info=True,
                )
                await asyncio.sleep(2.0)
                try:
                    await self._play_current_hour()
                except HomeAssistantError:
                    _LOGGER.error(
                        "Could not play the hourly track after the town tune",
                        exc_info=True,
                    )
        finally:
            # Cleared only once the new track is going, so the town tune
            # ending can't schedule a re-loop of the previous hour's track.
            self._transitioning = False

    # ── Playback ───────────────────────────────────────────────────

    async def _play_current_hour(self) -> None:
        """Play the appropriate track for the current hour."""
        cfg = self.config
        entity_id = cfg.get(CONF_MEDIA_PLAYER)

        now = datetime.now()

        # K.K. Slider check
        if self._should_play_kk(cfg, now):
            await self._play_kk(cfg, entity_id)
            return

        # Resolve game
        games = cfg.get(CONF_GAMES, DEFAULT_GAMES)
        if not games:
            games = DEFAULT_GAMES
        game = random.choice(games)  # noqa: S311

        # Resolve weather
        weather = self._resolve_weather(cfg, game)

        media_id = player.build_hourly_media_id(game, weather, now.hour)

        self._intentional_stop = False
        self._current_media_id = media_id
        self._current_duration_key = duration_key_hourly(game, weather, now.hour)
        self._current_game = game
        self._current_weather = weather
        self._notify_state_listeners()

        await player.async_set_volume(
            self.hass, entity_id, cfg.get(CONF_MUSIC_VOLUME)
        )

        _LOGGER.info(
            "Playing %s/%s hour %d on %s", game, weather, now.hour, entity_id
        )
        await self._play(entity_id, media_id)

        # Schedule shuffles for this hour
        self._schedule_shuffles(now)

    async def _play_kk(self, cfg: dict, entity_id: str) -> None:
        """Play a random K.K. Slider song."""
        song = self._pick_kk_song(cfg)
        version = cfg.get(CONF_KK_VERSION, DEFAULT_KK_VERSION)

        media_id = player.build_kk_media_id(song, version)

        self._intentional_stop = False
        self._current_media_id = media_id
        self._current_duration_key = duration_key_kk(song, version)
        self._current_game = None
        self._current_weather = None
        self._notify_state_listeners()

        await player.async_set_volume(
            self.hass, entity_id, cfg.get(CONF_MUSIC_VOLUME)
        )

        _LOGGER.info("Playing K.K. Slider: %s (%s) on %s", song, version, entity_id)
        await self._play(entity_id, media_id)

        # Schedule K.K. shuffles for this hour
        self._schedule_kk_shuffles(datetime.now())

    def _pick_kk_song(self, cfg: dict) -> str:
        """Pick a K.K. song, respecting no-repeats if enabled."""
        if not cfg.get(CONF_KK_SHUFFLE_NO_REPEATS):
            return get_random_kk_song()

        available = [s for s in ALL_KK_SONGS if s not in self._kk_played_songs]
        if not available:
            self._kk_played_songs.clear()
            available = list(ALL_KK_SONGS)
            _LOGGER.debug("K.K. no-repeats: pool exhausted, resetting")

        song = random.choice(available)  # noqa: S311
        self._kk_played_songs.append(song)
        return song

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
            "Player state change: %s -> %s (media_id=%s)",
            old_state.state,
            new_state.state,
            self._current_media_id,
        )

        # If the player went from playing to idle/off/paused, the track ended
        if (
            old_state.state == "playing"
            and new_state.state in (STATE_IDLE, STATE_OFF, STATE_PAUSED)
            and self._current_media_id
        ):
            # Schedule a re-loop with a small delay to avoid rapid cycling
            if self._reloop_task and not self._reloop_task.done():
                self._reloop_task.cancel()
            self._reloop_task = self.hass.async_create_task(
                self._reloop_after_delay()
            )

    async def _reloop_after_delay(self) -> None:
        """Wait briefly then re-trigger the current track."""
        song_delay = self.config.get(CONF_SONG_DELAY, DEFAULT_SONG_DELAY)
        await asyncio.sleep(RELOOP_DELAY + song_delay)

        if not self.enabled or self._intentional_stop or not self._current_media_id:
            return

        entity_id = self.config.get(CONF_MEDIA_PLAYER)

        # Check the player is still idle (not playing something else)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state and state.state in (STATE_IDLE, STATE_OFF, STATE_PAUSED):
            # Re-check weather; use updated track if changed, else current
            refreshed = self._refresh_weather_media_id()
            media_id = refreshed or self._current_media_id
            _LOGGER.debug(
                "Re-looping track: %s%s",
                media_id,
                " (weather updated)" if refreshed else "",
            )
            try:
                await self._play(entity_id, media_id)
            except HomeAssistantError:
                _LOGGER.warning("Could not re-loop track", exc_info=True)

    # ── Duration tracking (timer-based fallback) ────────────────

    def _schedule_duration_timer(self, media_id: str, duration_key: str | None) -> None:
        """Schedule a re-trigger after the known track duration."""
        if not self.config.get(CONF_DURATION_TRACKING):
            return

        # Cancel any existing timer
        if self._duration_timer_task and not self._duration_timer_task.done():
            self._duration_timer_task.cancel()

        self._duration_timer_task = self.hass.async_create_task(
            self._duration_timer(media_id, duration_key)
        )

    async def _duration_timer(self, media_id: str, duration_key: str | None) -> None:
        """Look up duration, wait, then re-trigger."""
        duration = TRACK_DURATIONS.get(duration_key) if duration_key else None
        if duration is None:
            _LOGGER.warning(
                "Duration tracking: no known duration for %s", duration_key
            )
            return

        song_delay = self.config.get(CONF_SONG_DELAY, DEFAULT_SONG_DELAY)
        wait_time = duration + DURATION_BUFFER + song_delay
        _LOGGER.info(
            "Duration tracking: %s is %.0fs, will re-trigger in %.0fs",
            duration_key,
            duration,
            wait_time,
        )

        await asyncio.sleep(wait_time)

        if not self.enabled or self._intentional_stop or self._transitioning:
            return
        if self._current_media_id != media_id:
            return

        entity_id = self.config.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            return

        # Re-check weather before re-triggering
        refreshed = self._refresh_weather_media_id()
        play_id = refreshed or media_id

        _LOGGER.info(
            "Duration tracking: timer fired, re-looping %s%s",
            play_id,
            " (weather updated)" if refreshed else "",
        )
        try:
            await self._play(entity_id, play_id)
        except HomeAssistantError:
            _LOGGER.warning("Could not re-loop track on timer", exc_info=True)

    # ── Shuffle scheduling ──────────────────────────────────────────

    def _schedule_shuffles(self, now: datetime) -> None:
        """Schedule track shuffles at evenly spaced intervals during the hour."""
        self._cancel_shuffle_timers()

        cfg = self.config
        shuffles = int(cfg.get(CONF_SHUFFLES_PER_HOUR, DEFAULT_SHUFFLES_PER_HOUR))
        if shuffles <= 0:
            return

        games = cfg.get(CONF_GAMES, DEFAULT_GAMES)
        if not games:
            games = DEFAULT_GAMES

        # Skip if only one possible track (1 game + fixed weather)
        weather_mode = cfg.get(CONF_WEATHER_MODE, DEFAULT_WEATHER_MODE)
        if len(games) <= 1 and weather_mode not in (WEATHER_RANDOM, WEATHER_LIVE):
            _LOGGER.debug("Shuffle skipped: only 1 possible track")
            return

        seconds_left = (59 - now.minute) * 60 + (60 - now.second)
        segment = seconds_left / (shuffles + 1)

        if segment < 30:
            _LOGGER.debug("Shuffle skipped: segments too short (%.0fs)", segment)
            return

        hour = now.hour
        for i in range(1, shuffles + 1):
            delay = segment * i
            task = self.hass.async_create_task(
                self._execute_shuffle(delay, hour)
            )
            self._shuffle_timers.append(task)

        _LOGGER.info(
            "Scheduled %d shuffles for hour %d (every %.0fs)",
            shuffles, hour, segment,
        )

    async def _execute_shuffle(self, delay: float, hour: int) -> None:
        """Wait, then switch to a different track."""
        await asyncio.sleep(delay)

        if not self.enabled or self._intentional_stop or self._transitioning:
            return

        now = datetime.now()
        if now.hour != hour:
            return

        cfg = self.config
        entity_id = cfg.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            return

        games = cfg.get(CONF_GAMES, DEFAULT_GAMES)
        if not games:
            games = DEFAULT_GAMES

        # Prefer a different game than the current one
        if len(games) > 1 and self._current_game in games:
            other_games = [g for g in games if g != self._current_game]
            game = random.choice(other_games)  # noqa: S311
        else:
            game = random.choice(games)  # noqa: S311

        weather = self._resolve_weather(cfg, game)
        media_id = player.build_hourly_media_id(game, weather, now.hour)

        self._current_media_id = media_id
        self._current_duration_key = duration_key_hourly(game, weather, now.hour)
        self._current_game = game
        self._current_weather = weather
        self._notify_state_listeners()

        # Cancel current duration timer so it doesn't re-trigger the old track
        if self._duration_timer_task and not self._duration_timer_task.done():
            self._duration_timer_task.cancel()
            self._duration_timer_task = None

        _LOGGER.info(
            "Shuffle: switching to %s/%s hour %d", game, weather, now.hour
        )
        try:
            await self._play(entity_id, media_id)
        except HomeAssistantError:
            _LOGGER.warning("Shuffle playback failed", exc_info=True)

    def _cancel_shuffle_timers(self) -> None:
        """Cancel all pending shuffle tasks."""
        for task in self._shuffle_timers:
            if not task.done():
                task.cancel()
        self._shuffle_timers.clear()

    # ── K.K. Slider shuffle scheduling ─────────────────────────────

    def _schedule_kk_shuffles(self, now: datetime) -> None:
        """Schedule K.K. song shuffles at evenly spaced intervals during the hour."""
        self._cancel_shuffle_timers()

        cfg = self.config
        shuffles = int(cfg.get(CONF_SHUFFLES_PER_HOUR, DEFAULT_SHUFFLES_PER_HOUR))
        if shuffles <= 0:
            return

        seconds_left = (59 - now.minute) * 60 + (60 - now.second)
        segment = seconds_left / (shuffles + 1)

        if segment < 30:
            _LOGGER.debug("K.K. shuffle skipped: segments too short (%.0fs)", segment)
            return

        hour = now.hour
        for i in range(1, shuffles + 1):
            delay = segment * i
            task = self.hass.async_create_task(
                self._execute_kk_shuffle(delay, hour)
            )
            self._shuffle_timers.append(task)

        _LOGGER.info(
            "Scheduled %d K.K. shuffles for hour %d (every %.0fs)",
            shuffles, hour, segment,
        )

    async def _execute_kk_shuffle(self, delay: float, hour: int) -> None:
        """Wait, then switch to a different K.K. song."""
        await asyncio.sleep(delay)

        if not self.enabled or self._intentional_stop or self._transitioning:
            return

        now = datetime.now()
        if now.hour != hour:
            return

        cfg = self.config
        entity_id = cfg.get(CONF_MEDIA_PLAYER)
        if not entity_id:
            return

        song = self._pick_kk_song(cfg)
        version = cfg.get(CONF_KK_VERSION, DEFAULT_KK_VERSION)

        media_id = player.build_kk_media_id(song, version)
        self._current_media_id = media_id
        self._current_duration_key = duration_key_kk(song, version)

        # Cancel current duration timer so it doesn't re-trigger the old track
        if self._duration_timer_task and not self._duration_timer_task.done():
            self._duration_timer_task.cancel()
            self._duration_timer_task = None

        _LOGGER.info("K.K. shuffle: switching to %s (%s)", song, version)
        try:
            await self._play(entity_id, media_id)
        except HomeAssistantError:
            _LOGGER.warning("K.K. shuffle playback failed", exc_info=True)

    # ── Helpers ────────────────────────────────────────────────────

    async def _play_town_tune(self, entity_id: str) -> bool | None:
        """Play the town tune.

        Returns True if it was sent as an announcement (the player ducks and
        resumes on its own), False if it was played as normal media, or None
        if no town tune has been generated yet.
        """
        media_id = self._get_town_tune_media_id()
        if not media_id:
            return None

        cfg = self.config
        # A separate player can be configured to route the tune to the
        # underlying device, for setups where the main player can't announce.
        tune_player = cfg.get(CONF_TOWN_TUNE_PLAYER) or entity_id

        await player.async_set_volume(
            self.hass, tune_player, cfg.get(CONF_TOWN_TUNE_VOLUME)
        )

        _LOGGER.info("Playing town tune on %s", tune_player)
        announced = await player.async_play(
            self.hass, tune_player, media_id, announce=True
        )

        # Playing the tune on a different device never interrupts the music,
        # so there's nothing to wait for either way.
        if tune_player != entity_id:
            return True

        # When the tune plays on the same device as the music, do not trust
        # the announce flag as proof of real ducking. Some bridges (VACA's
        # media-player bridge observed in the wild) accept ANNOUNCE in
        # supported_features and echo announced=True from play_media, but
        # don't actually duck-and-resume — play_media just returns as soon
        # as the call is accepted. Trusting that return value here caused
        # the immediately-following hourly-track play_media call to stomp
        # the town tune before it finished (or even started audibly).
        # Always wait out the tune's known duration in this case.
        return False

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

    def _refresh_weather_media_id(self) -> str | None:
        """Re-check weather and return an updated media id if it changed.

        Keeps the current game (no re-randomization), only refreshes the
        weather variant from the configured source.  Returns None when
        the weather has not changed or during K.K. Slider playback.
        """
        cfg = self.config
        game = self._current_game
        if not game:
            return None  # K.K. Slider playing — no weather variant

        weather = self._resolve_weather(cfg, game)
        if weather == self._current_weather:
            return None  # No change

        now = datetime.now()
        media_id = player.build_hourly_media_id(game, weather, now.hour)

        self._current_weather = weather
        self._current_media_id = media_id
        self._current_duration_key = duration_key_hourly(game, weather, now.hour)

        _LOGGER.info(
            "Weather changed to %s, switching track for %s hour %d",
            weather,
            game,
            now.hour,
        )
        self._notify_state_listeners()
        return media_id

    def _get_town_tune_media_id(self) -> str | None:
        """Return the media source id for the town tune, if it exists."""
        wav_path = self.hass.config.path("www", "ac_tunes", "town_tune.wav")
        if not os.path.isfile(wav_path):
            return None
        return player.build_town_tune_media_id()

    async def _play(self, entity_id: str | None, media_id: str) -> None:
        """Play a track, show the optional VACA clock, and arm its timer."""
        await player.async_play(self.hass, entity_id, media_id)
        await async_show_clock_after_playback(self.hass, self.config, entity_id)
        self._schedule_duration_timer(media_id, self._current_duration_key)
