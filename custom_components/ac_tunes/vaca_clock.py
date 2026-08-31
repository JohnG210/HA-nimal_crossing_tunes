"""Optional View Assist navigation after AC Tunes playback."""
from __future__ import annotations

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


def _is_view_assist_display(attributes: dict[str, Any]) -> bool:
    """Return whether state attributes identify a View Assist display."""
    return bool(attributes.get("display_device") and attributes.get("mic_device"))


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
