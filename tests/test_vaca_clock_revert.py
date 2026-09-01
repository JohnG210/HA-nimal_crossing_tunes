"""Regression harness for reverting the paired VACA display off the AC clock
when playback stops.

Covers the reported bug: stopping AC Tunes playback left the display parked
on the AC clock view indefinitely, because async_stop() never navigated the
satellite anywhere — only async_show_clock_after_playback (the forward
direction) existed.
"""
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
from custom_components.ac_tunes.vaca_clock import async_revert_clock_on_stop

MAIN_PLAYER = "media_player.desk_echo_show_mp_va"
DISPLAY = "sensor.desk_echo_show"
CLOCK_PATH = "/view-assist/ac-clock"
HOME_PATH = "/view-assist/clock"
SATELLITE_ID = "vaca_123"
PATH_SENSOR = f"sensor.{SATELLITE_ID}_current_path"


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
        "vaca_clock_path": CLOCK_PATH,
        "media_player_entity": MAIN_PLAYER,
    }
    value.update(overrides)
    return value


def vaca_state(*, home_screen=HOME_PATH):
    attrs = {"display_device": "va-123", "mic_device": f"assist_satellite.{SATELLITE_ID}"}
    if home_screen is not None:
        attrs["home_screen"] = home_screen
    return State(DISPLAY, "", attrs)


async def _instant_sleep(_delay):
    """Stand-in for asyncio.sleep that never actually waits."""


async def run_case(hass, cfg, stopped=MAIN_PLAYER):
    original_sleep = vaca_clock.asyncio.sleep
    vaca_clock.asyncio.sleep = _instant_sleep
    try:
        await async_revert_clock_on_stop(hass, cfg, stopped)
    finally:
        vaca_clock.asyncio.sleep = original_sleep
    return hass.services.calls


def check(name, callback):
    try:
        callback()
        print(f"PASS  {name}")
    except AssertionError as err:
        print(f"FAIL  {name}: {err}")
        raise


def test_reverts_when_currently_on_clock():
    hass = FakeHass(
        {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, CLOCK_PATH, {})}
    )
    calls = asyncio.run(run_case(hass, config()))
    assert calls == [("view_assist", "navigate", {"device": DISPLAY, "path": HOME_PATH}, True)]


def test_does_not_revert_when_not_currently_on_clock():
    """If the satellite has already moved on (camera, alarm, etc.) on its
    own, stopping playback must not clobber it back to the home screen."""
    hass = FakeHass(
        {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, "/view-assist/cribcamera", {})}
    )
    calls = asyncio.run(run_case(hass, config()))
    assert calls == []


def test_disabled_is_noop():
    hass = FakeHass(
        {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, CLOCK_PATH, {})}
    )
    calls = asyncio.run(run_case(hass, config(show_vaca_clock=False)))
    assert calls == []


def test_other_player_is_noop():
    hass = FakeHass(
        {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, CLOCK_PATH, {})}
    )
    calls = asyncio.run(run_case(hass, config(), "media_player.other"))
    assert calls == []


def test_missing_or_non_vaca_display_is_noop():
    missing = FakeHass({})
    assert asyncio.run(run_case(missing, config())) == []

    non_vaca = FakeHass({DISPLAY: State(DISPLAY, "", {})})
    assert asyncio.run(run_case(non_vaca, config())) == []


def test_missing_service_is_noop():
    hass = FakeHass(
        {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, CLOCK_PATH, {})},
        available=False,
    )
    assert asyncio.run(run_case(hass, config())) == []


def test_falls_back_to_default_home_screen_when_attribute_missing():
    hass = FakeHass(
        {
            DISPLAY: vaca_state(home_screen=None),
            PATH_SENSOR: State(PATH_SENSOR, CLOCK_PATH, {}),
        }
    )
    calls = asyncio.run(run_case(hass, config()))
    assert calls == [
        ("view_assist", "navigate", {"device": DISPLAY, "path": vaca_clock.DEFAULT_HOME_SCREEN_PATH}, True)
    ]


def test_revert_failure_does_not_escape():
    hass = FakeHass(
        {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, CLOCK_PATH, {})},
        fail=True,
    )
    calls = asyncio.run(run_case(hass, config()))
    assert calls == [("view_assist", "navigate", {"device": DISPLAY, "path": HOME_PATH}, True)]


def test_no_path_sensor_still_reverts():
    """If the ground-truth path sensor can't be derived (unexpected mic
    device shape), fail open and still attempt the revert rather than
    permanently stranding the clock on screen."""
    attrs = {"display_device": "va-123", "mic_device": "not-a-dotted-id", "home_screen": HOME_PATH}
    hass = FakeHass({DISPLAY: State(DISPLAY, "", attrs)})
    calls = asyncio.run(run_case(hass, config()))
    assert calls == [("view_assist", "navigate", {"device": DISPLAY, "path": HOME_PATH}, True)]


for name, fn in [
    ("reverts when currently on the AC clock", test_reverts_when_currently_on_clock),
    ("does not revert when not currently on the AC clock", test_does_not_revert_when_not_currently_on_clock),
    ("disabled feature does nothing", test_disabled_is_noop),
    ("other media player does nothing", test_other_player_is_noop),
    ("missing or non-VACA display does nothing", test_missing_or_non_vaca_display_is_noop),
    ("missing View Assist service does nothing", test_missing_service_is_noop),
    ("falls back to default home screen when attribute missing", test_falls_back_to_default_home_screen_when_attribute_missing),
    ("revert failure does not break stop", test_revert_failure_does_not_escape),
    ("no path sensor still reverts (fail open)", test_no_path_sensor_still_reverts),
]:
    check(name, fn)

print("\n9/9 passed")
