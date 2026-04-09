"""Media source platform for Animal Crossing Tunes."""
from __future__ import annotations

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    GAMES,
    KK_AIRCHECK,
    KK_LIVE,
    WEATHERS,
)
from .music_data import (
    ALL_KK_SONGS,
    KK_SONGS,
    format_hour_display,
    get_hourly_url,
    get_kk_url,
    kk_display_name,
)


async def async_get_media_source(hass: HomeAssistant) -> ACTunesMediaSource:
    """Set up the Animal Crossing Tunes media source."""
    return ACTunesMediaSource(hass)


class ACTunesMediaSource(MediaSource):
    """Provide Animal Crossing music as a browsable media source."""

    name = "Animal Crossing Tunes"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the media source."""
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media source item to a playable URL."""
        identifier = item.identifier
        if not identifier:
            raise Unresolvable("No identifier provided.")

        parts = identifier.split("/")

        # Hourly: hourly/{game}/{weather}/{hour}
        if parts[0] == "hourly" and len(parts) == 4:
            game = parts[1]
            weather = parts[2]
            hour = int(parts[3])
            url = get_hourly_url(game, weather, hour)
            return PlayMedia(url, "audio/ogg")

        # K.K.: kk/{version}/{song_name}
        if parts[0] == "kk" and len(parts) == 3:
            version = parts[1]
            song_name = parts[2]
            url = get_kk_url(song_name, version)
            return PlayMedia(url, "audio/ogg")

        raise Unresolvable(f"Unknown media identifier: {identifier}")

    async def async_browse_media(
        self, item: MediaSourceItem
    ) -> BrowseMediaSource:
        """Browse the Animal Crossing music library."""
        identifier = item.identifier

        # Root level
        if not identifier:
            return self._build_root()

        parts = identifier.split("/")

        # Hourly Music top level
        if identifier == "hourly":
            return self._build_hourly_games()

        # Hourly Music > specific game
        if parts[0] == "hourly" and len(parts) == 2:
            return self._build_hourly_weathers(parts[1])

        # Hourly Music > game > weather
        if parts[0] == "hourly" and len(parts) == 3:
            return self._build_hourly_tracks(parts[1], parts[2])

        # K.K. Slider top level
        if identifier == "kk":
            return self._build_kk_versions()

        # K.K. Slider > version
        if parts[0] == "kk" and len(parts) == 2:
            return self._build_kk_songs(parts[1])

        raise Unresolvable(f"Unknown browse path: {identifier}")

    # ── Tree builders ──────────────────────────────────────────────

    def _build_root(self) -> BrowseMediaSource:
        """Build root level: Hourly Music, K.K. Slider."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="Animal Crossing Tunes",
            can_play=False,
            can_expand=True,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier="hourly",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title="Hourly Music",
                    can_play=False,
                    can_expand=True,
                ),
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier="kk",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title="K.K. Slider",
                    can_play=False,
                    can_expand=True,
                ),
            ],
        )

    def _build_hourly_games(self) -> BrowseMediaSource:
        """Build game selection level for hourly music."""
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"hourly/{game_id}",
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.MUSIC,
                title=game_name,
                can_play=False,
                can_expand=True,
            )
            for game_id, game_name in GAMES.items()
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="hourly",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="Hourly Music",
            can_play=False,
            can_expand=True,
            children=children,
        )

    def _build_hourly_weathers(self, game: str) -> BrowseMediaSource:
        """Build weather selection level for a game."""
        from .const import GAME_WEATHER_VARIANTS

        game_name = GAMES.get(game, game)
        available = GAME_WEATHER_VARIANTS.get(game, list(WEATHERS.keys()))
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"hourly/{game}/{weather_id}",
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.MUSIC,
                title=WEATHERS[weather_id],
                can_play=False,
                can_expand=True,
            )
            for weather_id in available
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"hourly/{game}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=game_name,
            can_play=False,
            can_expand=True,
            children=children,
        )

    def _build_hourly_tracks(self, game: str, weather: str) -> BrowseMediaSource:
        """Build hour track listing for a game + weather combo."""
        game_name = GAMES.get(game, game)
        weather_name = WEATHERS.get(weather, weather)
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"hourly/{game}/{weather}/{hour}",
                media_class=MediaClass.MUSIC,
                media_content_type=MediaType.MUSIC,
                title=format_hour_display(hour),
                can_play=True,
                can_expand=False,
            )
            for hour in range(24)
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"hourly/{game}/{weather}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=f"{game_name} - {weather_name}",
            can_play=False,
            can_expand=True,
            children=children,
        )

    def _build_kk_versions(self) -> BrowseMediaSource:
        """Build K.K. Slider version selection (Live / Aircheck)."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="kk",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title="K.K. Slider",
            can_play=False,
            can_expand=True,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"kk/{KK_LIVE}",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title="Live",
                    can_play=False,
                    can_expand=True,
                ),
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"kk/{KK_AIRCHECK}",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.MUSIC,
                    title="Aircheck",
                    can_play=False,
                    can_expand=True,
                ),
            ],
        )

    def _build_kk_songs(self, version: str) -> BrowseMediaSource:
        """Build the K.K. Slider song listing for a version."""
        version_label = "Live" if version == KK_LIVE else "Aircheck"
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"kk/{version}/{song}",
                media_class=MediaClass.MUSIC,
                media_content_type=MediaType.MUSIC,
                title=kk_display_name(song),
                can_play=True,
                can_expand=False,
            )
            for song in ALL_KK_SONGS
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"kk/{version}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=f"K.K. Slider - {version_label}",
            can_play=False,
            can_expand=True,
            children=children,
        )
