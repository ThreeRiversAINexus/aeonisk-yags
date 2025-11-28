"""
Tests for stealth awareness system.

The DM controls which agents are aware of each action resolution via the
`aware_agents` field. This prevents NPCs and enemies from reacting to
successful stealth actions they shouldn't know about.

TDD: These tests are written FIRST to define the expected behavior.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

# Schema imports
from scripts.aeonisk.multiagent.schemas.action_resolution import (
    ActionResolution,
    MechanicalEffects,
)
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier


class TestAwareAgentsSchemaField:
    """Test that ActionResolution has the aware_agents field."""

    def test_action_resolution_has_aware_agents_field(self):
        """ActionResolution should have an aware_agents field."""
        resolution = ActionResolution(
            narration="Echo slips past the guard, completely undetected. " * 5,
            success_tier=SuccessTier.GOOD,
            margin=8,
            aware_agents=["dm", "echo"]
        )
        assert hasattr(resolution, 'aware_agents')
        assert resolution.aware_agents == ["dm", "echo"]

    def test_aware_agents_defaults_to_empty_list(self):
        """Empty aware_agents means public (all agents see it)."""
        resolution = ActionResolution(
            narration="The security guard fires at the intruder. " * 5,
            success_tier=SuccessTier.GOOD,
            margin=5,
        )
        assert resolution.aware_agents == []

    def test_aware_agents_accepts_agent_ids(self):
        """aware_agents should accept agent IDs like 'player_1', 'npc_vendor'."""
        resolution = ActionResolution(
            narration="A whispered conversation happens in the corner. " * 5,
            success_tier=SuccessTier.GOOD,
            margin=10,
            aware_agents=["player_1", "player_2", "npc_informant"]
        )
        assert "player_1" in resolution.aware_agents
        assert "npc_informant" in resolution.aware_agents


class TestNarrationEntry:
    """Test NarrationEntry dataclass for storing narrations with metadata."""

    def test_narration_entry_exists(self):
        """NarrationEntry should exist for storing narrations with awareness."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        entry = NarrationEntry(
            text="[Echo] Echo slips past the guard undetected.",
            aware_agents=["dm", "player_echo"]
        )
        assert entry.text == "[Echo] Echo slips past the guard undetected."
        assert entry.aware_agents == ["dm", "player_echo"]

    def test_narration_entry_defaults_to_public(self):
        """NarrationEntry with empty aware_agents is public."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        entry = NarrationEntry(
            text="[Guard] The guard shouts an alarm!"
        )
        assert entry.aware_agents == []


class TestAwarenessFiltering:
    """Test filtering narrations based on agent awareness."""

    def test_filter_narrations_for_agent_public(self):
        """Public narrations (empty aware_agents) visible to everyone."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(text="[Guard] Combat begins!", aware_agents=[]),
            NarrationEntry(text="[Echo] Echo sneaks past", aware_agents=["dm", "player_echo"]),
        ]

        # Guard should only see public narration
        filtered = filter_narrations_for_agent("npc_guard", narrations)
        assert len(filtered) == 1
        assert "Combat begins" in filtered[0].text

    def test_filter_narrations_for_agent_private(self):
        """Private narrations only visible to agents in aware_agents."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(text="[Echo] Echo hacks the terminal", aware_agents=["dm", "player_echo"]),
        ]

        # Echo should see their own stealth action
        filtered = filter_narrations_for_agent("player_echo", narrations)
        assert len(filtered) == 1

        # Random NPC should not see it
        filtered = filter_narrations_for_agent("npc_guard", narrations)
        assert len(filtered) == 0

    def test_filter_narrations_dm_sees_everything(self):
        """DM is always in aware_agents for private narrations."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(text="[Echo] Secret action", aware_agents=["dm", "player_echo"]),
        ]

        # DM should always see private narrations
        filtered = filter_narrations_for_agent("dm", narrations)
        assert len(filtered) == 1

    def test_filter_narrations_handles_string_list(self):
        """Backwards compatibility: handle list[str] as all public."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent

        # Old format: list of strings (all public)
        old_narrations = [
            "[Guard] Old format narration",
            "[Echo] Another old format",
        ]

        # Should treat strings as public (everyone sees them)
        filtered = filter_narrations_for_agent("npc_random", old_narrations)
        assert len(filtered) == 2


class TestPlayerNarrationStorage:
    """Test that player agents store narrations with awareness metadata."""

    @pytest.fixture
    def mock_player_agent(self):
        """Create a mock player agent with recent_narrations."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        agent = MagicMock()
        agent.agent_id = "player_echo"
        agent.recent_narrations = []
        return agent

    def test_player_stores_narration_with_awareness(self, mock_player_agent):
        """Player should store NarrationEntry objects, not plain strings."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        # Simulate receiving a resolution with aware_agents
        entry = NarrationEntry(
            text="[Echo] Echo slips past the guard",
            aware_agents=["dm", "player_echo"]
        )
        mock_player_agent.recent_narrations.append(entry)

        assert len(mock_player_agent.recent_narrations) == 1
        assert isinstance(mock_player_agent.recent_narrations[0], NarrationEntry)
        assert mock_player_agent.recent_narrations[0].aware_agents == ["dm", "player_echo"]


class TestNPCContextFiltering:
    """Test that NPCs only see narrations they're aware of."""

    def test_npc_does_not_see_stealth_success(self):
        """NPC should not see successful stealth action narration."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Echo] Echo successfully picks the lock without triggering any alarms.",
                aware_agents=["dm", "player_echo"]  # Only DM and Echo know
            ),
            NarrationEntry(
                text="[Guard] The guard patrols the corridor.",
                aware_agents=[]  # Public - everyone sees
            ),
        ]

        # NPC guard should only see their own patrol, not Echo's stealth
        filtered = filter_narrations_for_agent("npc_guard", narrations)

        assert len(filtered) == 1
        assert "patrols the corridor" in filtered[0].text
        assert "picks the lock" not in filtered[0].text

    def test_npc_sees_stealth_failure(self):
        """NPC should see failed stealth action (they noticed!)."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Echo] Echo fumbles the lockpick, metal clanging loudly!",
                aware_agents=[]  # Public - failure was noticed
            ),
        ]

        # Everyone should see the failure
        filtered = filter_narrations_for_agent("npc_guard", narrations)
        assert len(filtered) == 1
        assert "fumbles the lockpick" in filtered[0].text


class TestEnemyContextFiltering:
    """Test that enemies only see narrations they're aware of."""

    def test_enemy_does_not_see_stealth_success(self):
        """Enemy should not see successful stealth action."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Ash] Ash silently flanks the enemy position.",
                aware_agents=["dm", "player_ash"]  # Enemy unaware
            ),
        ]

        filtered = filter_narrations_for_agent("enemy_grunt_1", narrations)
        assert len(filtered) == 0

    def test_enemy_sees_loud_combat(self):
        """Enemy should see loud combat actions."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Ash] Ash fires their rifle, muzzle flash lighting up the corridor!",
                aware_agents=[]  # Public - loud combat
            ),
        ]

        filtered = filter_narrations_for_agent("enemy_grunt_1", narrations)
        assert len(filtered) == 1


class TestBackwardsCompatibility:
    """Test that existing sessions without aware_agents still work."""

    def test_resolution_without_aware_agents_is_public(self):
        """Resolutions without aware_agents field should be treated as public."""
        resolution = ActionResolution(
            narration="Standard action that everyone sees. The guard fires their weapon at the intruder, muzzle flash illuminating the dark corridor. " * 3,
            success_tier=SuccessTier.GOOD,
            margin=5,
        )
        # Empty list means public
        assert resolution.aware_agents == []

    def test_mixed_narration_types_handled(self):
        """System should handle mix of old strings and new NarrationEntry."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        # Mix of old and new formats
        mixed = [
            "[Old] Old string format",  # Old: plain string
            NarrationEntry(text="[New] New format", aware_agents=["dm"]),  # New: NarrationEntry
        ]

        # Should handle both - strings treated as public
        filtered = filter_narrations_for_agent("random_npc", mixed)
        # Old string should be visible (public), new entry should not (NPC not in aware_agents)
        assert len(filtered) == 1
        assert "Old string format" in filtered[0] if isinstance(filtered[0], str) else filtered[0].text
