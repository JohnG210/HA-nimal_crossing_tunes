"""Behavioral regression harness for optional VACA clock navigation."""
import asyncio
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
pkg = types.ModuleType("custom_components")
pkg.__path__ = [str(REPO / "custom_components")]
sys.modules["custom_components"] = pkg

from homeassistant.core import State

import custom_components.ac_tunes.vaca_clock as vaca_clock
from custom_components.ac_tunes.vaca_clock import async_show_clock_after_playback

MAIN_PLAYER = "media_player.desk_echo_show_mp_va"
DISPLAY = "sensor.desk_echo_show"
PATH = "/dashboard-viewassist/ac-clock"


class FakeStates:
    def __init__(self, values):
        self.values = values

    def get(self, entity_id):
        return self.values.get(entity_id)


class FakeServices:
    def __init__(self, *, available=True, fail=False):
        self.available = available
        self.fail = fail
        self.calls = []

    def has_service(self, domain, service):
        return self.available and (domain, service) == ("view_assist", "navigate")

    async def async_call(self, domain, service, data, blocking=True):
        self.calls.append((domain, service, dict(data), blocking))
        if self.fail:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError("simulated VACA failure")


class FakeHass:
    def __init__(self, states, *, available=True, fail=False):
        self.states = FakeStates(states)
        self.services = FakeServices(available=available, fail=fail)


def config(**overrides):
    value = {
        "show_vaca_clock": True,
        "vaca_display_entity": DISPLAY,
        "vaca_clock_path": PATH,
        "media_player_entity": MAIN_PLAYER,
    }
    value.update(overrides)
    return value


def vaca_state():
    return State(DISPLAY, "", {"display_device": "va-123", "mic_device": "assist_satellite.vaca_123"})


async def run_case(hass, cfg, played=MAIN_PLAYER):
    await async_show_clock_after_playback(hass, cfg, played)
    return hass.services.calls


def check(name, callback):
    try:
        callback()
        print(f"PASS  {name}")
    except AssertionError as err:
        print(f"FAIL  {name}: {err}")
        raise


def test_disabled_is_noop():
    hass = FakeHass({DISPLAY: vaca_state()})
    assert asyncio.run(run_case(hass, config(show_vaca_clock=False))) == []


def test_other_player_is_noop():
    hass = FakeHass({DISPLAY: vaca_state()})
    assert asyncio.run(run_case(hass, config(), "media_player.other")) == []


def test_missing_or_non_vaca_display_is_noop():
    missing = FakeHass({})
    assert asyncio.run(run_case(missing, config())) == []

    non_vaca = FakeHass({DISPLAY: State(DISPLAY, "", {})})
    assert asyncio.run(run_case(non_vaca, config())) == []


def test_missing_service_is_noop():
    hass = FakeHass({DISPLAY: vaca_state()}, available=False)
    assert asyncio.run(run_case(hass, config())) == []


def test_valid_pair_navigates_once():
    hass = FakeHass({DISPLAY: vaca_state()})
    calls = asyncio.run(run_case(hass, config()))
    assert calls == [("view_assist", "navigate", {"device": DISPLAY, "path": PATH}, True)]


def test_navigation_failure_does_not_escape():
    hass = FakeHass({DISPLAY: vaca_state()}, fail=True)
    assert asyncio.run(run_case(hass, config())) == [
        ("view_assist", "navigate", {"device": DISPLAY, "path": PATH}, True)
    ]


def test_navigation_waits_for_vaca_media_route():
    async def run():
        sleeps = []
        original_sleep = vaca_clock.asyncio.sleep

        async def fake_sleep(delay):
            sleeps.append(delay)

        vaca_clock.asyncio.sleep = fake_sleep
        try:
            hass = FakeHass({DISPLAY: vaca_state()})
            await async_show_clock_after_playback(hass, config(), MAIN_PLAYER)
        finally:
            vaca_clock.asyncio.sleep = original_sleep
        assert sleeps == [vaca_clock.VACA_MEDIA_ROUTE_DELAY]
        assert hass.services.calls == [
            ("view_assist", "navigate", {"device": DISPLAY, "path": PATH}, True)
        ]

    asyncio.run(run())


for name, fn in [
    ("disabled feature does nothing", test_disabled_is_noop),
    ("other media player does nothing", test_other_player_is_noop),
    ("missing or non-VACA display does nothing", test_missing_or_non_vaca_display_is_noop),
    ("missing View Assist service does nothing", test_missing_service_is_noop),
    ("valid pair navigates exactly once", test_valid_pair_navigates_once),
    ("navigation failure does not break playback", test_navigation_failure_does_not_escape),
    ("navigation waits for VACA media routing", test_navigation_waits_for_vaca_media_route),
]:
    check(name, fn)

print("\n7/7 passed")
