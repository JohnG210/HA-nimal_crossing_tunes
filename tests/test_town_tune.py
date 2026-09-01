"""Regression harness for town tune / hourly-track transition timing.

Covers the swallowed-town-tune bug: VACA's media-player bridge reports
MEDIA_ANNOUNCE support and echoes announced=True from play_media, but does
not actually duck-and-resume audio. Trusting that flag made the integration
skip its wait and immediately fire the next play_media call on the same
player, stomping the town tune before it finished playing (or was audible
at all).
"""
import asyncio
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
pkg = types.ModuleType("custom_components")
pkg.__path__ = [str(REPO / "custom_components")]
sys.modules["custom_components"] = pkg

import custom_components.ac_tunes.coordinator as coordinator_mod
import custom_components.ac_tunes.player as player_mod
from custom_components.ac_tunes.coordinator import ACTunesCoordinator
from custom_components.ac_tunes.const import (
    CONF_MEDIA_PLAYER,
    CONF_TOWN_TUNE_PLAYER,
    CONF_TOWN_TUNE_VOLUME,
)

MAIN_PLAYER = "media_player.desk_echo_show_mp_va"
OTHER_PLAYER = "media_player.desk_echo_show_mp_2"


class FakeCoordinator:
    """Minimal stand-in exposing only what _play_town_tune touches."""

    def __init__(self, hass, config, *, media_id="media-source://ac_tunes/town_tune"):
        self.hass = hass
        self._config = config
        self._media_id = media_id
        # Attributes touched by _transition_to_new_hour.
        self._duration_timer_task = None
        self._transitioning = False

    @property
    def config(self):
        return self._config

    def _get_town_tune_media_id(self):
        return self._media_id

    def _cancel_shuffle_timers(self):
        pass


def make_hass():
    return types.SimpleNamespace()


def check(name, callback):
    try:
        callback()
        print(f"PASS  {name}")
    except AssertionError as err:
        print(f"FAIL  {name}: {err}")
        raise


def test_same_player_never_trusts_announce_flag():
    """Even if the bridge claims announced=True, same-player tunes must
    report False so the caller waits out the full tune duration."""

    async def run():
        calls = []

        async def fake_set_volume(hass, entity_id, volume_pct):
            calls.append(("set_volume", entity_id, volume_pct))

        async def fake_play(hass, entity_id, media_id, *, announce=False, **kwargs):
            calls.append(("play", entity_id, media_id, announce))
            # Simulate a bridge that lies about ducking, like VACA's.
            return True

        original_set_volume = player_mod.async_set_volume
        original_play = player_mod.async_play
        player_mod.async_set_volume = fake_set_volume
        player_mod.async_play = fake_play
        try:
            fake = FakeCoordinator(
                make_hass(),
                {
                    CONF_MEDIA_PLAYER: MAIN_PLAYER,
                    CONF_TOWN_TUNE_PLAYER: None,
                    CONF_TOWN_TUNE_VOLUME: 45,
                },
            )
            result = await ACTunesCoordinator._play_town_tune(fake, MAIN_PLAYER)
        finally:
            player_mod.async_set_volume = original_set_volume
            player_mod.async_play = original_play

        assert result is False, f"expected False (must wait), got {result}"
        assert ("play", MAIN_PLAYER, "media-source://ac_tunes/town_tune", True) in calls

    asyncio.run(run())


def test_separate_tune_player_still_reports_no_wait_needed():
    """A tune routed to a genuinely different device never interrupts the
    music, regardless of what that device's announce flag reports."""

    async def run():
        calls = []

        async def fake_set_volume(hass, entity_id, volume_pct):
            calls.append(("set_volume", entity_id, volume_pct))

        async def fake_play(hass, entity_id, media_id, *, announce=False, **kwargs):
            calls.append(("play", entity_id, media_id, announce))
            return False  # even if the bridge is honest and says no ducking

        original_set_volume = player_mod.async_set_volume
        original_play = player_mod.async_play
        player_mod.async_set_volume = fake_set_volume
        player_mod.async_play = fake_play
        try:
            fake = FakeCoordinator(
                make_hass(),
                {
                    CONF_MEDIA_PLAYER: MAIN_PLAYER,
                    CONF_TOWN_TUNE_PLAYER: OTHER_PLAYER,
                    CONF_TOWN_TUNE_VOLUME: 45,
                },
            )
            result = await ACTunesCoordinator._play_town_tune(fake, MAIN_PLAYER)
        finally:
            player_mod.async_set_volume = original_set_volume
            player_mod.async_play = original_play

        assert result is True, f"expected True (no wait needed), got {result}"
        assert ("play", OTHER_PLAYER, "media-source://ac_tunes/town_tune", True) in calls

    asyncio.run(run())


def test_no_town_tune_generated_yet_is_none():
    async def run():
        fake = FakeCoordinator(
            make_hass(),
            {
                CONF_MEDIA_PLAYER: MAIN_PLAYER,
                CONF_TOWN_TUNE_PLAYER: None,
                CONF_TOWN_TUNE_VOLUME: 45,
            },
            media_id=None,
        )
        result = await ACTunesCoordinator._play_town_tune(fake, MAIN_PLAYER)
        assert result is None

    asyncio.run(run())


def test_transition_waits_full_duration_when_not_trusted():
    """End-to-end: _transition_to_new_hour must actually sleep
    TOWN_TUNE_DURATION when _play_town_tune reports announced=False,
    instead of racing straight into the next hourly-track play_media call.
    """

    async def run():
        sleeps = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        async def fake_play_town_tune(self, entity_id):
            return False  # same-player, not trusted — caller must wait

        async def fake_play_current_hour(self):
            pass

        original_sleep = coordinator_mod.asyncio.sleep
        coordinator_mod.asyncio.sleep = fake_sleep
        try:
            fake = FakeCoordinator(make_hass(), {CONF_MEDIA_PLAYER: MAIN_PLAYER})
            fake._play_town_tune = types.MethodType(fake_play_town_tune, fake)
            fake._play_current_hour = types.MethodType(fake_play_current_hour, fake)
            import datetime as _dt

            await ACTunesCoordinator._transition_to_new_hour(fake, _dt.datetime.now())
        finally:
            coordinator_mod.asyncio.sleep = original_sleep

        assert coordinator_mod.TOWN_TUNE_DURATION in sleeps, (
            f"expected a sleep of {coordinator_mod.TOWN_TUNE_DURATION}s, got {sleeps}"
        )

    asyncio.run(run())


for name, fn in [
    ("same-player tune never trusts the announce flag", test_same_player_never_trusts_announce_flag),
    ("separate-player tune still skips the wait", test_separate_tune_player_still_reports_no_wait_needed),
    ("missing town tune WAV returns None", test_no_town_tune_generated_yet_is_none),
    ("hour transition actually waits out the tune duration", test_transition_waits_full_duration_when_not_trusted),
]:
    check(name, fn)

print("\n4/4 passed")
