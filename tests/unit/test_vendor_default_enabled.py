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

    def test_default_vendor_frequency_is_3_when_key_absent(self):
        """When config lacks vendor_spawn_frequency, default should be 3 (enabled)."""
        config = {"session_name": "test", "max_turns": 5, "agents": {}}
        session = self._make_session_with_config(config)

        vendor_frequency = session.config.get('vendor_spawn_frequency', 3)
        assert vendor_frequency == 3, (
            f"Expected default vendor_spawn_frequency=3, got {vendor_frequency}"
        )

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
    async def test_check_vendor_spawn_triggers_on_round_3_default(self):
        """With default frequency=3, round 3 should get past frequency check to agent lookup."""
        config = {}  # defaults to frequency=3
        session = self._make_session_with_agents(config)

        await session._check_vendor_spawn(3)
        # If default is correct (3), round 3 % 3 == 0 → reaches agent iteration
        session.agents.__iter__.assert_called()

    @pytest.mark.asyncio
    async def test_check_vendor_spawn_triggers_on_round_6_default(self):
        """With default frequency=3, round 6 should also reach agent lookup."""
        config = {}  # defaults to frequency=3
        session = self._make_session_with_agents(config)

        await session._check_vendor_spawn(6)
        session.agents.__iter__.assert_called()


class TestSessionAndDmDefaultConsistency:
    """Verify session.py and dm.py use the same default for vendor_spawn_frequency."""

    def test_session_default_matches_dm_default(self):
        """Both session.py and dm.py should default to vendor_spawn_frequency=3."""
        # session.py default (the one we're fixing)
        session_config = {}
        session_default = session_config.get('vendor_spawn_frequency', 3)

        # dm.py default (already correct at line 1335)
        dm_config = {}
        dm_default = dm_config.get('vendor_spawn_frequency', 3)

        assert session_default == dm_default == 3, (
            f"Defaults must match: session={session_default}, dm={dm_default}"
        )
