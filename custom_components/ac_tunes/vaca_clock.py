"""Optional View Assist navigation after AC Tunes playback."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_MEDIA_PLAYER,
    CONF_SHOW_VACA_CLOCK,
    CONF_VACA_CLOCK_PATH,
    CONF_VACA_DISPLAY_ENTITY,
    DEFAULT_VACA_CLOCK_PATH,
)

_LOGGER = logging.getLogger(__name__)

# VACA may route to its music page shortly after media_player.play_media
# returns. Delay navigation so the AC clock is the final display route.
VACA_MEDIA_ROUTE_DELAY = 1.0

# How long to keep polling the satellite's reported current path before
# giving up and logging a mismatch (seconds), and how often to check.
VACA_NAVIGATION_VERIFY_TIMEOUT = 5.0
VACA_NAVIGATION_VERIFY_INTERVAL = 0.5


def _is_view_assist_display(attributes: dict[str, Any]) -> bool:
    """Return whether state attributes identify a View Assist display."""
    return bool(attributes.get("display_device") and attributes.get("mic_device"))


def _current_path_entity_id(mic_device: str | None) -> str | None:
    """Derive the satellite's reported-current-path sensor from its mic device.

    ``sensor.desk_echo_show``'s own ``current_path`` attribute merely echoes
    back whatever path the integration most recently requested — it is not
    proof the device actually rendered it. The companion app instead reports
    ground truth on a sibling sensor named ``sensor.<satellite_id>_current_path``
    (e.g. ``assist_satellite.vaca_131c919e5`` -> ``sensor.vaca_131c919e5_current_path``).
    """
    if not mic_device or "." not in mic_device:
        return None
    satellite_id = mic_device.split(".", 1)[1]
    return f"sensor.{satellite_id}_current_path"


async def async_show_clock_after_playback(
    hass: HomeAssistant, config: dict[str, Any], played_entity_id: str | None
) -> None:
    """Navigate the explicitly paired VACA display after successful playback.

    View Assist is intentionally optional. Any absent, non-VACA, or unrelated
    configuration is a no-op so ordinary media players retain normal behavior.
    """
    if not config.get(CONF_SHOW_VACA_CLOCK, False):
        return

    if played_entity_id != config.get(CONF_MEDIA_PLAYER):
        _LOGGER.debug("Skipping AC clock navigation for non-primary player %s", played_entity_id)
        return

    display_entity = config.get(CONF_VACA_DISPLAY_ENTITY)
    if not display_entity:
        _LOGGER.debug("Skipping AC clock navigation: no View Assist display configured")
        return

    display_state = hass.states.get(display_entity)
    if display_state is None or not _is_view_assist_display(display_state.attributes):
        _LOGGER.debug("Skipping AC clock navigation: %s is not a View Assist display", display_entity)
        return

    if not hass.services.has_service("view_assist", "navigate"):
        _LOGGER.debug("Skipping AC clock navigation: View Assist is not installed")
        return

    path = config.get(CONF_VACA_CLOCK_PATH) or DEFAULT_VACA_CLOCK_PATH
    await asyncio.sleep(VACA_MEDIA_ROUTE_DELAY)
    try:
        await hass.services.async_call(
            "view_assist",
            "navigate",
            {"device": display_entity, "path": path},
            blocking=True,
        )
    except HomeAssistantError:
        _LOGGER.warning(
            "Could not navigate View Assist display %s to AC clock", display_entity, exc_info=True
        )
        return

    await _verify_navigation_landed(hass, display_state.attributes, display_entity, path)


async def _verify_navigation_landed(
    hass: HomeAssistant,
    display_attributes: dict[str, Any],
    display_entity: str,
    requested_path: str,
) -> None:
    """Poll the satellite's own reported path and warn if it never matches.

    A successful ``view_assist.navigate`` call only proves the request was
    accepted, not that the device rendered it — the v0.3.2 regression shipped
    with current_path-echo mistaken for confirmation. This checks the ground
    truth sensor instead.
    """
    path_entity_id = _current_path_entity_id(display_attributes.get("mic_device"))
    if path_entity_id is None:
        _LOGGER.debug(
            "Skipping AC clock navigation verification: could not derive path sensor for %s",
            display_entity,
        )
        return

    elapsed = 0.0
    while elapsed < VACA_NAVIGATION_VERIFY_TIMEOUT:
        state = hass.states.get(path_entity_id)
        if state is not None and state.state == requested_path:
            _LOGGER.debug(
                "AC clock navigation confirmed on %s (%s)", display_entity, path_entity_id
            )
            return
        await asyncio.sleep(VACA_NAVIGATION_VERIFY_INTERVAL)
        elapsed += VACA_NAVIGATION_VERIFY_INTERVAL

    reported = hass.states.get(path_entity_id)
    _LOGGER.warning(
        "AC clock navigation requested %s on %s but %s reports %s after %.1fs; "
        "the display may not have actually moved",
        requested_path,
        display_entity,
        path_entity_id,
        reported.state if reported else "unknown",
        VACA_NAVIGATION_VERIFY_TIMEOUT,
    )
