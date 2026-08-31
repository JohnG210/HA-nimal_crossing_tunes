"""Generic Home Assistant media player interaction.

Every call this integration makes to a media player goes through here, so
target validation, feature checks and error reporting behave identically
for the coordinator and for the services.

Media is addressed with ``media-source://`` identifiers wherever possible.
Home Assistant core resolves those to a URL with the correct MIME type and
signs local paths for the receiving player, which is what lets the same
track work on Music Assistant, Sonos, Chromecast and Apple TV alike.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from homeassistant.components.media_player import (
    ATTR_MEDIA_ANNOUNCE,
    ATTR_MEDIA_CONTENT_ID,
    ATTR_MEDIA_CONTENT_TYPE,
    ATTR_MEDIA_ENQUEUE,
    ATTR_MEDIA_VOLUME_LEVEL,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    SERVICE_PLAY_MEDIA,
    MediaPlayerEntityFeature,
    MediaType,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_STOP,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_SET,
    STATE_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# How long to wait for a player to report itself on after turn_on.
WAKE_TIMEOUT = 5.0
WAKE_POLL_INTERVAL = 0.25


# ── Media source identifiers ───────────────────────────────────────────


def build_hourly_media_id(game: str, weather: str, hour: int) -> str:
    """Build the media source id for an hourly track."""
    return f"media-source://{DOMAIN}/hourly/{game}/{weather}/{hour}"


def build_kk_media_id(song_name: str, version: str) -> str:
    """Build the media source id for a K.K. Slider song.

    Song titles contain spaces and punctuation, and media source
    identifiers may not contain whitespace, so the title is
    percent-encoded here and decoded again by the resolver.
    """
    return f"media-source://{DOMAIN}/kk/{version}/{quote(song_name, safe='')}"


def build_town_tune_media_id() -> str:
    """Build the media source id for the generated town tune."""
    return f"media-source://{DOMAIN}/town_tune"


# ── Target resolution ──────────────────────────────────────────────────


def _features(state: State) -> int:
    """Return the supported_features bitmask for a player."""
    return state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0


def resolve_target(hass: HomeAssistant, entity_id: str | None) -> State:
    """Return the state of a usable media player, or raise.

    Home Assistant silently matches zero entities when handed an unknown
    entity id, so without this check a renamed player looks exactly like
    working playback that happens to be silent.
    """
    if not entity_id:
        raise ServiceValidationError(
            "No media player is configured for HA-nimal Crossing Tunes. "
            "Set one in the integration options."
        )

    state = hass.states.get(entity_id)
    if state is None:
        raise ServiceValidationError(
            f"Media player {entity_id} does not exist. It may have been "
            "renamed or removed — update the HA-nimal Crossing Tunes options."
        )

    if state.state == STATE_UNAVAILABLE:
        raise HomeAssistantError(f"Media player {entity_id} is unavailable.")

    return state


def supports_announce(hass: HomeAssistant, entity_id: str | None) -> bool:
    """Return True when the player can play announcements over its media."""
    if not entity_id:
        return False
    state = hass.states.get(entity_id)
    if state is None:
        return False
    return bool(_features(state) & MediaPlayerEntityFeature.MEDIA_ANNOUNCE)


async def _async_wake(hass: HomeAssistant, state: State) -> None:
    """Turn a player on and wait for it to leave the off state."""
    if state.state != STATE_OFF:
        return

    entity_id = state.entity_id
    if not _features(state) & MediaPlayerEntityFeature.TURN_ON:
        _LOGGER.debug(
            "%s is off and does not support turn_on; playing anyway", entity_id
        )
        return

    _LOGGER.debug("Waking %s before playback", entity_id)
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    waited = 0.0
    while waited < WAKE_TIMEOUT:
        current = hass.states.get(entity_id)
        if current is not None and current.state not in (
            STATE_OFF,
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ):
            return
        await asyncio.sleep(WAKE_POLL_INTERVAL)
        waited += WAKE_POLL_INTERVAL

    _LOGGER.debug(
        "%s did not report on within %.0fs; playing anyway", entity_id, WAKE_TIMEOUT
    )


# ── Playback ───────────────────────────────────────────────────────────


async def async_play(
    hass: HomeAssistant,
    entity_id: str | None,
    media_id: str,
    *,
    announce: bool = False,
    enqueue: str | None = None,
    blocking: bool = True,
) -> bool:
    """Play media on a player following the standard Home Assistant flow.

    Returns True when the media was sent as an announcement, so the caller
    knows the player will duck and resume on its own.
    """
    state = resolve_target(hass, entity_id)
    features = _features(state)

    if not features & MediaPlayerEntityFeature.PLAY_MEDIA:
        raise HomeAssistantError(
            f"Media player {entity_id} does not support playing media."
        )

    await _async_wake(hass, state)

    data: dict = {
        ATTR_ENTITY_ID: entity_id,
        ATTR_MEDIA_CONTENT_ID: media_id,
        ATTR_MEDIA_CONTENT_TYPE: MediaType.MUSIC,
    }

    announced = False
    if announce:
        if features & MediaPlayerEntityFeature.MEDIA_ANNOUNCE:
            data[ATTR_MEDIA_ANNOUNCE] = True
            announced = True
        else:
            _LOGGER.debug(
                "%s does not support announce; playing as normal media", entity_id
            )

    if enqueue is not None and features & MediaPlayerEntityFeature.MEDIA_ENQUEUE:
        data[ATTR_MEDIA_ENQUEUE] = enqueue

    _LOGGER.debug("Calling play_media on %s with %s", entity_id, data)
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN, SERVICE_PLAY_MEDIA, data, blocking=blocking
    )
    return announced


async def async_set_volume(
    hass: HomeAssistant, entity_id: str | None, volume_pct: int | None
) -> None:
    """Set the volume on a player, if one is configured and it supports it."""
    if volume_pct is None or not entity_id:
        return

    state = hass.states.get(entity_id)
    if state is None:
        _LOGGER.debug("Cannot set volume: %s does not exist", entity_id)
        return

    if not _features(state) & MediaPlayerEntityFeature.VOLUME_SET:
        _LOGGER.debug("%s does not support volume_set; skipping", entity_id)
        return

    volume = max(0.0, min(1.0, volume_pct / 100.0))
    try:
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_VOLUME_SET,
            {ATTR_ENTITY_ID: entity_id, ATTR_MEDIA_VOLUME_LEVEL: volume},
            blocking=True,
        )
    except HomeAssistantError:
        _LOGGER.warning("Could not set volume on %s", entity_id, exc_info=True)


async def async_stop(hass: HomeAssistant, entity_id: str | None) -> None:
    """Stop playback, falling back to pause or turn_off for limited players."""
    if not entity_id:
        return

    state = hass.states.get(entity_id)
    if state is None:
        _LOGGER.debug("Cannot stop: %s does not exist", entity_id)
        return

    features = _features(state)
    for feature, service in (
        (MediaPlayerEntityFeature.STOP, SERVICE_MEDIA_STOP),
        (MediaPlayerEntityFeature.PAUSE, SERVICE_MEDIA_PAUSE),
        (MediaPlayerEntityFeature.TURN_OFF, SERVICE_TURN_OFF),
    ):
        if not features & feature:
            continue
        try:
            await hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
            return
        except HomeAssistantError:
            _LOGGER.warning(
                "media_player.%s failed on %s", service, entity_id, exc_info=True
            )

    _LOGGER.warning("No supported way to stop %s", entity_id)
