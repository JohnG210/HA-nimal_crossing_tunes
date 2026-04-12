"""Config flow for HA-nimal Crossing Tunes."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    AUDIO_LOCAL,
    AUDIO_REMOTE,
    CONF_AUDIO_SOURCE,
    CONF_GAME,
    CONF_GAMES,
    CONF_KK_SCHEDULE,
    CONF_KK_SHUFFLE_NO_REPEATS,
    CONF_KK_VERSION,
    CONF_LOCAL_PATH,
    CONF_MEDIA_PLAYER,
    CONF_DURATION_TRACKING,
    CONF_MUSIC_VOLUME,
    CONF_SHUFFLES_PER_HOUR,
    CONF_SONG_DELAY,
    CONF_TOWN_TUNE,
    CONF_TOWN_TUNE_PLAYER,
    CONF_TOWN_TUNE_VOLUME,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_MODE,
    DEFAULT_AUDIO_SOURCE,
    DEFAULT_GAMES,
    DEFAULT_KK_SCHEDULE,
    DEFAULT_KK_VERSION,
    DEFAULT_SHUFFLES_PER_HOUR,
    DEFAULT_SONG_DELAY,
    DEFAULT_WEATHER_MODE,
    DOMAIN,
    GAME_ANIMAL_CROSSING,
    GAME_NEW_HORIZONS,
    GAME_NEW_LEAF,
    GAME_RANDOM,
    GAME_WILD_WORLD,
    GAMES,
    KK_AIRCHECK,
    KK_ALWAYS,
    KK_LIVE,
    KK_NEVER,
    KK_SATURDAYS,
    WEATHER_LIVE,
    WEATHER_RAINY,
    WEATHER_RANDOM,
    WEATHER_SNOWY,
    WEATHER_SUNNY,
)


def _build_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the config/options schema."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_GAMES, default=d.get(CONF_GAMES, DEFAULT_GAMES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=GAME_ANIMAL_CROSSING, label="Animal Crossing"
                        ),
                        selector.SelectOptionDict(
                            value=GAME_WILD_WORLD, label="Wild World & City Folk"
                        ),
                        selector.SelectOptionDict(
                            value=GAME_NEW_LEAF, label="New Leaf"
                        ),
                        selector.SelectOptionDict(
                            value=GAME_NEW_HORIZONS, label="New Horizons"
                        ),
                    ],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                CONF_WEATHER_MODE,
                default=d.get(CONF_WEATHER_MODE, DEFAULT_WEATHER_MODE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=WEATHER_SUNNY, label="Always Sunny"
                        ),
                        selector.SelectOptionDict(
                            value=WEATHER_RAINY, label="Always Rainy"
                        ),
                        selector.SelectOptionDict(
                            value=WEATHER_SNOWY, label="Always Snowy"
                        ),
                        selector.SelectOptionDict(
                            value=WEATHER_LIVE, label="Live Weather"
                        ),
                        selector.SelectOptionDict(
                            value=WEATHER_RANDOM, label="Random"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_MEDIA_PLAYER,
                default=d.get(CONF_MEDIA_PLAYER, ""),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player")
            ),
            vol.Required(
                CONF_AUDIO_SOURCE,
                default=d.get(CONF_AUDIO_SOURCE, DEFAULT_AUDIO_SOURCE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=AUDIO_REMOTE, label="Remote (acmusicext.com)"
                        ),
                        selector.SelectOptionDict(
                            value=AUDIO_LOCAL, label="Local Files"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_LOCAL_PATH,
                description={"suggested_value": d.get(CONF_LOCAL_PATH, "")},
            ): selector.TextSelector(),
            vol.Required(
                CONF_KK_SCHEDULE,
                default=d.get(CONF_KK_SCHEDULE, DEFAULT_KK_SCHEDULE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=KK_NEVER, label="Never"
                        ),
                        selector.SelectOptionDict(
                            value=KK_SATURDAYS, label="Saturday Nights"
                        ),
                        selector.SelectOptionDict(
                            value=KK_ALWAYS, label="Always"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_KK_VERSION,
                default=d.get(CONF_KK_VERSION, DEFAULT_KK_VERSION),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=KK_LIVE, label="Live"
                        ),
                        selector.SelectOptionDict(
                            value=KK_AIRCHECK, label="Aircheck"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_KK_SHUFFLE_NO_REPEATS,
                default=d.get(CONF_KK_SHUFFLE_NO_REPEATS, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_WEATHER_ENTITY,
                description={"suggested_value": d.get(CONF_WEATHER_ENTITY)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Optional(
                CONF_TOWN_TUNE_PLAYER,
                description={"suggested_value": d.get(CONF_TOWN_TUNE_PLAYER)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player")
            ),
            vol.Optional(
                CONF_MUSIC_VOLUME,
                description={"suggested_value": d.get(CONF_MUSIC_VOLUME)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_TOWN_TUNE_VOLUME,
                description={"suggested_value": d.get(CONF_TOWN_TUNE_VOLUME)},
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=100,
                    step=1,
                    unit_of_measurement="%",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
            vol.Optional(
                CONF_DURATION_TRACKING,
                default=d.get(CONF_DURATION_TRACKING, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_SONG_DELAY,
                default=d.get(CONF_SONG_DELAY, DEFAULT_SONG_DELAY),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=3600,
                    step=1,
                    unit_of_measurement="seconds",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_SHUFFLES_PER_HOUR,
                default=d.get(CONF_SHUFFLES_PER_HOUR, DEFAULT_SHUFFLES_PER_HOUR),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=10,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


class ACTunesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA-nimal Crossing Tunes."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="HA-nimal Crossing Tunes", data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ACTunesOptionsFlow:
        """Return the options flow handler."""
        return ACTunesOptionsFlow(config_entry)


class ACTunesOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for HA-nimal Crossing Tunes."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Preserve town tune (saved via service, not in this form)
            existing_tune = self._config_entry.options.get(CONF_TOWN_TUNE)
            if existing_tune is not None:
                user_input[CONF_TOWN_TUNE] = existing_tune
            return self.async_create_entry(title="", data=user_input)

        # Use current config as defaults, migrating legacy game→games
        current = {**self._config_entry.data, **self._config_entry.options}
        if CONF_GAME in current and CONF_GAMES not in current:
            old_game = current.pop(CONF_GAME)
            if old_game == GAME_RANDOM:
                current[CONF_GAMES] = list(GAMES.keys())
            else:
                current[CONF_GAMES] = [old_game]
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(current),
        )
