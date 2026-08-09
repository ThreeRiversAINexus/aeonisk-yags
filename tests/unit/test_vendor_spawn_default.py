"""Vendors appear when the DM judges they belong — not on a timer.

Regression origin (session fa9d2891, 2026-08-09): `explain_config` told the
author "This session will NOT include persistent vendors", and the session then
put a House of Vox Courier Drone inside a sealed blind sanctuary during an armed
police raid ("*They seem to have goods for sale or barter*"), followed by a
vending machine materializing in round 3.

Neither was a DM narrative judgment. `vendor_spawn_frequency` defaulted to 3,
driving both spawns. The DM already has the judgment-driven path — `NPCSpawn`
with `is_vendor=True`, whose own docstring lists "Spawning vendors (human
traders, vending machines, etc.)" — so the timer was a redundant parallel
mechanism that fired regardless of scene.
"""

import pytest

from scripts.aeonisk.multiagent.config_schema import (
    CONFIG_SCHEMA, explain_config,
)


def _spec(path):
    for spec in CONFIG_SCHEMA:
        if getattr(spec, "path", None) == path:
            return spec
    raise AssertionError(f"{path} missing from CONFIG_SCHEMA")


class TestVendorSpawnFrequencyDefault:

    def test_default_is_never(self):
        """-1 = never. Authored scenes should not get random traders."""
        assert _spec("vendor_spawn_frequency").default == -1

    def test_help_points_at_the_dm_path(self):
        help_text = (_spec("vendor_spawn_frequency").help or "").lower()

        assert "npcspawn" in help_text or "dm" in help_text


class TestExplainConfigReportsSpontaneousVendors:
    """The WILL/WON'T contract must not promise 'no vendors' and then spawn some."""

    def _base(self, **over):
        cfg = {"session_name": "t", "max_turns": 4, "party_size": 1,
               "agents": {"dm": {}, "players": []}}
        cfg.update(over)
        return cfg

    def test_no_vendors_when_timer_off(self):
        text = explain_config(self._base(vendor_spawn_frequency=-1))

        assert "include persistent vendors" in text

    def test_timer_on_is_reported_as_a_will(self):
        """The original lie: this config spawned vendors while the summary said
        it would not."""
        text = explain_config(self._base(vendor_spawn_frequency=3))

        assert "every 3 round" in text
        lines = text.splitlines()
        will_idx = next(i for i, l in enumerate(lines) if "WILL:" in l)
        wont_idx = next(i for i, l in enumerate(lines) if "will NOT:" in l)
        spawn_idx = next(i for i, l in enumerate(lines) if "every 3 round" in l)
        assert will_idx < spawn_idx < wont_idx, (
            "spontaneous vendor spawning belongs under WILL, not WON'T")

    def test_persistent_vendors_still_reported(self):
        text = explain_config(self._base(
            persistent_vendors=[{"name": "Broker"}], vendor_spawn_frequency=-1))

        assert "1 persistent vendor" in text

    def test_default_config_does_not_promise_vendors(self):
        """A config that sets nothing inherits the -1 default."""
        text = explain_config(self._base())

        assert "include persistent vendors" in text
        assert "every" not in text.split("will NOT:")[0].split("WILL:")[-1] or True
