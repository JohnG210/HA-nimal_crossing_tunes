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
SATELLITE_ID = "vaca_123"
PATH_SENSOR = f"sensor.{SATELLITE_ID}_current_path"


class FakeStates:
    def __init__(self, values):
        self.values = values

    def get(self, entity_id):
        return self.values.get(entity_id)

    def set(self, entity_id, state):
        self.values[entity_id] = State(entity_id, state, {})


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
    return State(
        DISPLAY,
        "",
        {"display_device": "va-123", "mic_device": f"assist_satellite.{SATELLITE_ID}"},
    )


async def _instant_sleep(_delay):
    """Stand-in for asyncio.sleep that never actually waits."""


async def run_case(hass, cfg, played=MAIN_PLAYER, *, fast=True):
    original_sleep = vaca_clock.asyncio.sleep
    if fast:
        vaca_clock.asyncio.sleep = _instant_sleep
    try:
        await async_show_clock_after_playback(hass, cfg, played)
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
    hass = FakeHass({DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, PATH, {})})
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
            hass = FakeHass(
                {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, PATH, {})}
            )
            await async_show_clock_after_playback(hass, config(), MAIN_PLAYER)
        finally:
            vaca_clock.asyncio.sleep = original_sleep
        # First sleep is the pre-navigation VACA route delay; remaining
        # sleeps (if any) come from the verification poll loop.
        assert sleeps[0] == vaca_clock.VACA_MEDIA_ROUTE_DELAY
        assert hass.services.calls == [
            ("view_assist", "navigate", {"device": DISPLAY, "path": PATH}, True)
        ]

    asyncio.run(run())


def test_verification_passes_when_satellite_confirms_path():
    async def run():
        hass = FakeHass(
            {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, PATH, {})}
        )
        warnings = []
        original_warning = vaca_clock._LOGGER.warning
        vaca_clock._LOGGER.warning = lambda *a, **k: warnings.append(a[0] % a[1:] if len(a) > 1 else a[0])
        try:
            await run_case(hass, config())
        finally:
            vaca_clock._LOGGER.warning = original_warning
        assert warnings == []

    asyncio.run(run())


def test_verification_warns_when_satellite_never_confirms_path():
    """Regression test for the v0.3.2 bug: a navigate call can be accepted

    and the *requested* path can even echo back onto the display's own
    sensor, while the satellite's independently-reported path sensor never
    actually changes (no dashboard view at that path). This must not raise,
    but it must be observable via a warning instead of silently claiming
    success.
    """

    async def run():
        # PATH_SENSOR intentionally left reporting something else, simulating
        # a navigation request to a path that doesn't exist on the dashboard.
        hass = FakeHass(
            {DISPLAY: vaca_state(), PATH_SENSOR: State(PATH_SENSOR, "/view-assist/clock", {})}
        )
        warnings = []
        original_warning = vaca_clock._LOGGER.warning
        vaca_clock._LOGGER.warning = lambda *a, **k: warnings.append(a[0] % a[1:] if len(a) > 1 else a[0])
        try:
            await run_case(hass, config())
        finally:
            vaca_clock._LOGGER.warning = original_warning
        assert len(warnings) == 1
        assert PATH in warnings[0]
        assert PATH_SENSOR in warnings[0]

    asyncio.run(run())


for name, fn in [
    ("disabled feature does nothing", test_disabled_is_noop),
    ("other media player does nothing", test_other_player_is_noop),
    ("missing or non-VACA display does nothing", test_missing_or_non_vaca_display_is_noop),
    ("missing View Assist service does nothing", test_missing_service_is_noop),
    ("valid pair navigates exactly once", test_valid_pair_navigates_once),
    ("navigation failure does not break playback", test_navigation_failure_does_not_escape),
    ("navigation waits for VACA media routing", test_navigation_waits_for_vaca_media_route),
    ("verification passes when satellite confirms path", test_verification_passes_when_satellite_confirms_path),
    ("verification warns when satellite never confirms path", test_verification_warns_when_satellite_never_confirms_path),
]:
    check(name, fn)

print("\n9/9 passed")
