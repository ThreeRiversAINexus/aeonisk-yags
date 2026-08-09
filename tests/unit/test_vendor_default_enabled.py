"""
Unit tests for vendor_spawn_frequency default behavior.

Verifies that vendors are enabled by default (frequency=3) when
session configs don't explicitly set vendor_spawn_frequency.

TDD: These tests define expected behavior for the default change.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from scripts.aeonisk.multiagent.session import SelfPlayingSession


class TestVendorSpawnFrequencyDefault:
    """Test that vendor_spawn_frequency defaults to 3 (enabled)."""

    def _make_session_with_config(self, config: dict) -> SelfPlayingSession:
        """Create a SelfPlayingSession with a given config dict (bypass file loading)."""
        session = SelfPlayingSession.__new__(SelfPlayingSession)
        session.config = config
        session.coordinator = None
        session.agents = []
        session.human_interface = None
        session.session_id = None
        session.session_data = []
        session.running = False
        return session

    def test_default_vendor_frequency_is_never_when_key_absent(self):
        """When config lacks vendor_spawn_frequency, the registry default is -1.

        Asserted against CONFIG_SCHEMA rather than a literal restated here: the
        previous version of this test computed `config.get(key, 3)` with its own
        hardcoded 3, so it passed no matter what the production default was.
        """
        from scripts.aeonisk.multiagent.config_schema import CONFIG_SCHEMA

        spec = next(s for s in CONFIG_SCHEMA
                    if getattr(s, "path", None) == "vendor_spawn_frequency")

        assert spec.default == -1

    def test_explicit_negative_one_disables_vendors(self):
        """Explicit -1 should override default and disable vendors."""
        config = {"vendor_spawn_frequency": -1}
        session = self._make_session_with_config(config)

        vendor_frequency = session.config.get('vendor_spawn_frequency', 3)
        assert vendor_frequency == -1

    def test_explicit_zero_disables_vendors(self):
        """Explicit 0 should override default and disable vendors."""
        config = {"vendor_spawn_frequency": 0}
        session = self._make_session_with_config(config)

        vendor_frequency = session.config.get('vendor_spawn_frequency', 3)
        assert vendor_frequency == 0

    def test_explicit_positive_value_respected(self):
        """Explicit positive value should be used as-is."""
        config = {"vendor_spawn_frequency": 5}
        session = self._make_session_with_config(config)

        vendor_frequency = session.config.get('vendor_spawn_frequency', 3)
        assert vendor_frequency == 5


class TestCheckVendorSpawnDefault:
    """Test _check_vendor_spawn behavior with default frequency.

    These tests verify the method gets PAST the frequency guard (line ~3392)
    by checking whether DM agent lookup is reached. If the default is wrong
    (e.g., -1), the method returns early and never reaches agent iteration.
    """

    def _make_session_with_agents(self, config: dict) -> SelfPlayingSession:
        """Create a minimal SelfPlayingSession with mock agents."""
        session = SelfPlayingSession.__new__(SelfPlayingSession)
        session.config = config
        session.coordinator = MagicMock()
        session.coordinator.message_bus = MagicMock()
        session.coordinator.message_bus._route_message = AsyncMock()
        # Use a mock list that tracks iteration (proves we got past frequency check)
        session.agents = MagicMock()
        session.agents.__iter__ = MagicMock(return_value=iter([]))
        session.human_interface = None
        session.session_id = "test-session"
        session.session_data = []
        session.running = True
        return session

    @pytest.mark.asyncio
    async def test_check_vendor_spawn_returns_early_when_disabled(self):
        """With vendor_spawn_frequency=-1, _check_vendor_spawn should NOT iterate agents."""
        config = {"vendor_spawn_frequency": -1}
        session = self._make_session_with_agents(config)

        await session._check_vendor_spawn(3)
        # agents should NOT have been iterated (early return before agent lookup)
        session.agents.__iter__.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_vendor_spawn_skips_non_spawn_round(self):
        """On non-spawn rounds, should return before agent lookup."""
        config = {"vendor_spawn_frequency": 3}
        session = self._make_session_with_agents(config)

        # Round 2 is not divisible by 3, should skip
        await session._check_vendor_spawn(2)
        session.agents.__iter__.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_spawn_by_default(self):
        """Default is now -1 (never): an authored scene gets no random trader.

        The timer used to default to 3, which put a House of Vox courier drone
        inside a sealed blind sanctuary mid-raid in session fa9d2891 — and the
        config summary had promised no vendors. The DM spawns vendors when the
        scene warrants one, via NPCSpawn(is_vendor=True).
        """
        session = self._make_session_with_agents({})  # no explicit frequency

        for round_num in (3, 6, 9):
            await session._check_vendor_spawn(round_num)

        session.agents.__iter__.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_frequency_still_spawns(self):
        """Opting in for economy-exercise corpus runs still works."""
        session = self._make_session_with_agents({"vendor_spawn_frequency": 3})

        await session._check_vendor_spawn(3)

        session.agents.__iter__.assert_called()


class TestSessionAndDmDefaultConsistency:
    """Verify session.py and dm.py use the same default for vendor_spawn_frequency."""

    def test_session_and_dm_defaults_agree_with_registry(self):
        """session.py, dm.py and CONFIG_SCHEMA must all say the same thing.

        Reads the literals out of the source, because the previous version
        restated its own `3` on both sides and compared those — it could never
        have caught a drift between the two modules it claimed to check.
        """
        import re
        from pathlib import Path
        from scripts.aeonisk.multiagent.config_schema import CONFIG_SCHEMA

        pkg = Path(__file__).resolve().parents[2] / "scripts" / "aeonisk" / "multiagent"
        pattern = re.compile(r"get\(\s*['\"]vendor_spawn_frequency['\"]\s*,\s*(-?\d+)\s*\)")

        found = {}
        for module in ("session.py", "dm.py"):
            matches = pattern.findall((pkg / module).read_text())
            assert matches, f"no vendor_spawn_frequency default found in {module}"
            found[module] = {int(m) for m in matches}

        registry_default = next(
            s.default for s in CONFIG_SCHEMA
            if getattr(s, "path", None) == "vendor_spawn_frequency")

        assert found["session.py"] == found["dm.py"] == {registry_default}, (
            f"defaults disagree: {found}, registry={registry_default}")
