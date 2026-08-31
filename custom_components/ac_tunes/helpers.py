"""Shared helpers for HA-nimal Crossing Tunes.

Everything that turns a (game, weather, hour) or K.K. song into a playable
URL lives here, so the media source resolver, the coordinator and the
services all agree on one answer.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import (
    AUDIO_LOCAL,
    CONF_AUDIO_SOURCE,
    CONF_LOCAL_PATH,
    DEFAULT_LOCAL_PATH,
    DOMAIN,
)
from .music_data import (
    format_hour,
    get_hourly_url,
    get_hourly_url_local,
    get_kk_url,
    get_kk_url_local,
)

_LOGGER = logging.getLogger(__name__)


def get_config(hass: HomeAssistant) -> dict:
    """Return the merged config (data + options) of the first config entry."""
    for entry_data in hass.data.get(DOMAIN, {}).values():
        coordinator = entry_data.get("coordinator")
        if coordinator:
            return coordinator.config
    return {}


def _local_root(cfg: dict) -> str:
    """Return the configured local media root, normalised."""
    root = (cfg.get(CONF_LOCAL_PATH) or DEFAULT_LOCAL_PATH).strip().rstrip("/")
    if not root.startswith("/"):
        root = f"/{root}"
    return root


def _localise(root: str, built: str) -> str:
    """Adapt a built local path to something Home Assistant can actually play.

    ``/local/...`` is served straight out of ``config/www``. ``/media/...``
    lives in the media directory, which is *not* reachable over plain HTTP —
    it is only addressable through Home Assistant's own media source, so it
    is expressed as a nested media source id for core to resolve and sign.
    """
    if root == "/media" or root.startswith("/media/"):
        sub = root[len("/media"):].strip("/")
        rel = built[len(root):].lstrip("/")
        prefix = f"{sub}/" if sub else ""
        return f"media-source://media_source/local/{prefix}{rel}"
    return built


def uses_local_audio(cfg: dict) -> bool:
    """Return True when the integration is configured for local files."""
    return cfg.get(CONF_AUDIO_SOURCE) == AUDIO_LOCAL


def resolve_hourly_url(cfg: dict, game: str, weather: str, hour: int) -> str:
    """Return the URL (or nested media source id) for an hourly track."""
    if not uses_local_audio(cfg):
        return get_hourly_url(game, weather, hour)
    root = _local_root(cfg)
    return _localise(root, get_hourly_url_local(game, weather, hour, root))


def resolve_kk_url(cfg: dict, song_name: str, version: str) -> str:
    """Return the URL (or nested media source id) for a K.K. Slider song."""
    if not uses_local_audio(cfg):
        return get_kk_url(song_name, version)
    root = _local_root(cfg)
    return _localise(root, get_kk_url_local(song_name, version, root))


def duration_key_hourly(game: str, weather: str, hour: int) -> str:
    """Return the TRACK_DURATIONS lookup key for an hourly track."""
    return f"{game}/{weather}/{format_hour(hour)}"


def duration_key_kk(song_name: str, version: str) -> str:
    """Return the TRACK_DURATIONS lookup key for a K.K. Slider song."""
    return f"kk/{version}/{song_name}"
