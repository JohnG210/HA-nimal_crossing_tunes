"""Music data catalog for Animal Crossing Tunes."""
from __future__ import annotations

import random
from urllib.parse import quote

from .const import (
    BASE_URL,
    GAME_ANIMAL_CROSSING,
    GAME_NEW_HORIZONS,
    GAME_NEW_LEAF,
    GAME_WILD_WORLD,
    GAMES,
    GAME_WEATHER_VARIANTS,
    KK_AIRCHECK,
    KK_LIVE,
    WEATHER_RAINY,
    WEATHER_SNOWY,
    WEATHER_SUNNY,
)

# K.K. Slider songs — these are the exact filenames used on acmusicext.com
# Format: "{GamePrefix} - {SongName}" which maps to the .ogg filename
KK_SONGS: dict[str, list[str]] = {
    GAME_ANIMAL_CROSSING: [
        "AC - Aloha K.K.",
        "AC - Cafe K.K.",
        "AC - Comrade K.K.",
        "AC - DJ K.K.",
        "AC - Go K.K. Rider!",
        "AC - I Love You",
        "AC - Imperial K.K.",
        "AC - K.K. Aria",
        "AC - K.K. Ballad",
        "AC - K.K. Blues",
        "AC - K.K. Bossa",
        "AC - K.K. Calypso",
        "AC - K.K. Casbah",
        "AC - K.K. Chorale",
        "AC - K.K. Condor",
        "AC - K.K. Country",
        "AC - K.K. Cruisin'",
        "AC - K.K. D & B",
        "AC - K.K. Dirge",
        "AC - K.K. Etude",
        "AC - K.K. Faire",
        "AC - K.K. Folk",
        "AC - K.K. Fusion",
        "AC - K.K. Gumbo",
        "AC - K.K. Jazz",
        "AC - K.K. Lament",
        "AC - K.K. Love Song",
        "AC - K.K. Lullaby",
        "AC - K.K. Mambo",
        "AC - K.K. March",
        "AC - K.K. Parade",
        "AC - K.K. Ragtime",
        "AC - K.K. Reggae",
        "AC - K.K. Rock",
        "AC - K.K. Safari",
        "AC - K.K. Salsa",
        "AC - K.K. Samba",
        "AC - K.K. Ska",
        "AC - K.K. Song",
        "AC - K.K. Soul",
        "AC - K.K. Steppe",
        "AC - K.K. Swing",
        "AC - K.K. Tango",
        "AC - K.K. Technopop",
        "AC - K.K. Waltz",
        "AC - K.K. Western",
        "AC - Lucky K.K.",
        "AC - Mr. K.K.",
        "AC - Only Me",
        "AC - Rockin' K.K.",
        "AC - Senor K.K.",
        "AC - Soulful K.K.",
        "AC - Surfin' K.K.",
        "AC - The K. Funk",
        "AC - Two Days Ago",
    ],
    GAME_WILD_WORLD: [
        "CF - Agent K.K.",
        "CF - Forest Life",
        "CF - K.K. Dixie",
        "CF - K.K. House",
        "CF - K.K. Marathon",
        "CF - K.K. Metal",
        "CF - K.K. Rally",
        "CF - K.K. Rockabilly",
        "CF - K.K. Sonata",
        "CF - King K.K.",
        "CF - Marine Song 2001",
        "CF - Mountain Song",
        "CF - My Place",
        "CF - Neapolitan",
        "CF - Pondering",
        "CF - Spring Blossoms",
        "CF - Stale Cupcakes",
        "CF - Steep Hill",
        "CF - To the Edge",
        "CF - Wandering",
    ],
    GAME_NEW_LEAF: [
        "NL - Bubblegum K.K.",
        "NL - Hypno K.K.",
        "NL - K.K. Adventure",
        "NL - K.K. Bazaar",
        "NL - K.K. Birthday",
        "NL - K.K. Disco",
        "NL - K.K. Flamenco",
        "NL - K.K. Groove",
        "NL - K.K. Island",
        "NL - K.K. Jongara",
        "NL - K.K. Milonga",
        "NL - K.K. Moody",
        "NL - K.K. Oasis",
        "NL - K.K. Stroll",
        "NL - K.K. Synth",
        "NL - Space K.K.",
    ],
    GAME_NEW_HORIZONS: [
        "NH - Animal City",
        "NH - Drivin'",
        "NH - Farewell",
        "NH - Welcome Horizons",
    ],
}

# All K.K. songs flattened
ALL_KK_SONGS: list[str] = sorted(
    song for songs in KK_SONGS.values() for song in songs
)


def kk_display_name(song_id: str) -> str:
    """Convert a K.K. song ID to a display-friendly name.

    'AC - K.K. Waltz' -> 'K.K. Waltz (AC)'
    """
    if " - " in song_id:
        prefix, name = song_id.split(" - ", 1)
        return f"{name} ({prefix})"
    return song_id


def format_hour(hour: int) -> str:
    """Convert 24-hour int to the filename format used by acmusicext.com.

    0 -> '12am', 1 -> '1am', ..., 12 -> '12pm', 13 -> '1pm', ..., 23 -> '11pm'
    """
    if hour == 0:
        return "12am"
    if hour < 12:
        return f"{hour}am"
    if hour == 12:
        return "12pm"
    return f"{hour - 12}pm"


def format_hour_display(hour: int) -> str:
    """Format hour for display in the media browser.

    0 -> '12:00 AM', 1 -> '1:00 AM', ..., 12 -> '12:00 PM', etc.
    """
    if hour == 0:
        return "12:00 AM"
    if hour < 12:
        return f"{hour}:00 AM"
    if hour == 12:
        return "12:00 PM"
    return f"{hour - 12}:00 PM"


def get_hourly_url(
    game: str,
    weather: str,
    hour: int,
    *,
    base_url: str = BASE_URL,
) -> str:
    """Build the URL for an hourly music track.

    Pattern: {base_url}/{game}/{weather}/{hour}.ogg
    Example: https://acmusicext.com/static/new-leaf/sunny/9am.ogg
    """
    hour_str = format_hour(hour)
    return f"{base_url}/{game}/{weather}/{hour_str}.ogg"


def get_hourly_url_local(
    game: str,
    weather: str,
    hour: int,
    local_path: str,
) -> str:
    """Build a local file path for an hourly music track."""
    hour_str = format_hour(hour)
    return f"{local_path}/{game}/{weather}/{hour_str}.ogg"


def get_kk_url(
    song_name: str,
    version: str = KK_LIVE,
    *,
    base_url: str = BASE_URL,
) -> str:
    """Build the URL for a K.K. Slider song.

    Pattern: {base_url}/kk/{version}/{song_name}.ogg
    The song_name is URL-encoded to handle spaces and special characters.
    """
    encoded = quote(f"{song_name}.ogg")
    return f"{base_url}/kk/{version}/{encoded}"


def get_kk_url_local(
    song_name: str,
    version: str = KK_LIVE,
    local_path: str = "",
) -> str:
    """Build a local file path for a K.K. Slider song."""
    return f"{local_path}/kk/{version}/{song_name}.ogg"


def get_available_weathers(game: str) -> list[str]:
    """Return the weather variants available for a given game."""
    return GAME_WEATHER_VARIANTS.get(game, [WEATHER_SUNNY])


def get_random_kk_song() -> str:
    """Return a random K.K. Slider song name."""
    return random.choice(ALL_KK_SONGS)  # noqa: S311


def map_weather_state(state: str) -> str:
    """Map a Home Assistant weather entity state to an AC weather variant.

    HA weather states: clear-night, cloudy, fog, hail, lightning,
    lightning-rainy, partlycloudy, pouring, rainy, snowy, snowy-rainy,
    sunny, windy, windy-variant, exceptional
    """
    state_lower = state.lower()
    if state_lower in ("rainy", "pouring", "lightning-rainy", "hail"):
        return WEATHER_RAINY
    if state_lower in ("snowy", "snowy-rainy"):
        return WEATHER_SNOWY
    return WEATHER_SUNNY
