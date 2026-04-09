"""Constants for Animal Crossing Tunes."""

DOMAIN = "ac_tunes"

# Remote audio base URL
BASE_URL = "https://acmusicext.com/static"

# Game identifiers (used in URL paths)
GAME_ANIMAL_CROSSING = "animal-crossing"
GAME_WILD_WORLD = "wild-world"
GAME_NEW_LEAF = "new-leaf"
GAME_NEW_HORIZONS = "new-horizons"

GAMES = {
    GAME_ANIMAL_CROSSING: "Animal Crossing",
    GAME_WILD_WORLD: "Wild World & City Folk",
    GAME_NEW_LEAF: "New Leaf",
    GAME_NEW_HORIZONS: "New Horizons",
}

GAME_RANDOM = "game-random"

# Weather identifiers (used in URL paths)
WEATHER_SUNNY = "sunny"
WEATHER_RAINY = "raining"
WEATHER_SNOWY = "snowing"

WEATHERS = {
    WEATHER_SUNNY: "Sunny",
    WEATHER_RAINY: "Rainy",
    WEATHER_SNOWY: "Snowy",
}

WEATHER_RANDOM = "weather-random"
WEATHER_LIVE = "live"

# Weather variants available per game
GAME_WEATHER_VARIANTS = {
    GAME_ANIMAL_CROSSING: [WEATHER_SUNNY, WEATHER_SNOWY],
    GAME_WILD_WORLD: [WEATHER_SUNNY, WEATHER_RAINY, WEATHER_SNOWY],
    GAME_NEW_LEAF: [WEATHER_SUNNY, WEATHER_RAINY, WEATHER_SNOWY],
    GAME_NEW_HORIZONS: [WEATHER_SUNNY, WEATHER_RAINY, WEATHER_SNOWY],
}

# K.K. Slider versions
KK_LIVE = "live"
KK_AIRCHECK = "aircheck"

# K.K. schedule options
KK_NEVER = "never"
KK_SATURDAYS = "saturdays"
KK_ALWAYS = "always"

# Config keys
CONF_GAME = "game"
CONF_WEATHER_MODE = "weather_mode"
CONF_MEDIA_PLAYER = "media_player_entity"
CONF_AUDIO_SOURCE = "audio_source"
CONF_LOCAL_PATH = "local_path"
CONF_KK_SCHEDULE = "kk_schedule"
CONF_KK_VERSION = "kk_version"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_TOWN_TUNE_PLAYER = "town_tune_player"
CONF_ENABLED = "enabled"

# Audio source options
AUDIO_REMOTE = "remote"
AUDIO_LOCAL = "local"

# Defaults
DEFAULT_GAME = GAME_NEW_HORIZONS
DEFAULT_WEATHER_MODE = WEATHER_SUNNY
DEFAULT_KK_SCHEDULE = KK_SATURDAYS
DEFAULT_KK_VERSION = KK_LIVE
DEFAULT_AUDIO_SOURCE = AUDIO_REMOTE
