"""
Unit tests for SharedState coordination system.

Tests communal resource management and party coordination:
- Soulcredit pool management
- Void spike tracking
- Ritual progress
- Party discoveries
- Player registration
- Coordination bonuses
"""

import pytest
from aeonisk.multiagent.shared_state import SharedState, VoidSpikeRecord


# ============================================================================
# Soulcredit Tests
# ============================================================================

class TestSoulcredit:
    """Test soulcredit pool management."""

    def test_initial_soulcredit(self):
        """Test initial soulcredit pool is zero."""
        state = SharedState()
        assert state.soulcredit_pool == 0

    def test_adjust_soulcredit_positive(self):
        """Test adding soulcredit."""
        state = SharedState()
        cue = state.adjust_soulcredit(5, reason="Good deed")

        assert state.soulcredit_pool == 5
        assert cue is None  # No escalation
        assert len(state.soulcredit_history) == 1
        assert state.soulcredit_history[0]['delta'] == 5

    def test_adjust_soulcredit_negative(self):
        """Test spending soulcredit."""
        state = SharedState()
        state.soulcredit_pool = 10

        cue = state.adjust_soulcredit(-3, reason="Used power")

        assert state.soulcredit_pool == 7
        assert cue is None

    def test_soulcredit_floor_trigger(self):
        """Test hitting soulcredit floor triggers escalation."""
        state = SharedState()
        state.soulcredit_floor = -4

        # Go below floor
        cue = state.adjust_soulcredit(-5, reason="Debt")

        assert state.soulcredit_pool == -5
        assert cue is not None
        assert "Escalate" in cue
        assert "debt collectors" in cue.lower()

    def test_soulcredit_at_floor(self):
        """Test at floor (not below) triggers escalation."""
        state = SharedState()
        state.soulcredit_floor = -4

        cue = state.adjust_soulcredit(-4, reason="Exactly at floor")

        assert state.soulcredit_pool == -4
        assert cue is not None

    def test_soulcredit_history_tracking(self):
        """Test soulcredit history is tracked."""
        state = SharedState()

        state.adjust_soulcredit(5, reason="Helped civilians")
        state.adjust_soulcredit(-2, reason="Used ritual")
        state.adjust_soulcredit(3, reason="Defeated enemy")

        assert len(state.soulcredit_history) == 3
        assert state.soulcredit_history[0]['reason'] == "Helped civilians"
        assert state.soulcredit_history[1]['delta'] == -2
        assert state.soulcredit_history[2]['result'] == 6  # 5 - 2 + 3

    def test_soulcredit_no_reason(self):
        """Test soulcredit adjustment without reason."""
        state = SharedState()

        state.adjust_soulcredit(3)

        assert state.soulcredit_pool == 3
        assert state.soulcredit_history[0]['reason'] == "unspecified"


# ============================================================================
# Void Spike Tests
# ============================================================================

class TestVoidSpikes:
    """Test void spike tracking."""

    def test_initial_void_spikes(self):
        """Test no void spikes initially."""
        state = SharedState()
        assert len(state.void_spikes) == 0

    def test_record_void_spike(self):
        """Test recording a void spike."""
        state = SharedState()

        cue = state.record_void_spike("Failed ritual", severity=1)

        assert len(state.void_spikes) == 1
        assert state.void_spikes[0].reason == "Failed ritual"
        assert state.void_spikes[0].severity == 1
        assert cue is None  # Below threshold

    def test_void_spike_threshold(self):
        """Test void spike threshold triggers escalation."""
        state = SharedState()
        state.void_threshold = 4

        # Add spikes totaling >= threshold
        state.record_void_spike("Spike 1", severity=2)
        state.record_void_spike("Spike 2", severity=1)
        cue = state.record_void_spike("Spike 3", severity=1)  # Total = 4

        assert cue is not None
        assert "Escalate" in cue
        assert "Void fallout" in cue

    def test_multiple_void_spikes(self):
        """Test multiple void spikes accumulate."""
        state = SharedState()

        state.record_void_spike("Spike A", severity=1)
        state.record_void_spike("Spike B", severity=2)
        state.record_void_spike("Spike C", severity=1)

        assert len(state.void_spikes) == 3
        total_severity = sum(spike.severity for spike in state.void_spikes)
        assert total_severity == 4

    def test_void_spike_record_dataclass(self):
        """Test VoidSpikeRecord dataclass."""
        record = VoidSpikeRecord(reason="Test spike", severity=3)

        assert record.reason == "Test spike"
        assert record.severity == 3


# ============================================================================
# Ritual Tests
# ============================================================================

class TestRituals:
    """Test communal ritual tracking."""

    def test_advance_new_ritual(self):
        """Test advancing a new ritual."""
        state = SharedState()

        state.advance_ritual("Protection Barrier")

        assert "Protection Barrier" in state.rituals
        assert state.rituals["Protection Barrier"] == 1

    def test_advance_existing_ritual(self):
        """Test advancing existing ritual."""
        state = SharedState()
        state.rituals["Summoning"] = 3

        state.advance_ritual("Summoning", progress=2)

        assert state.rituals["Summoning"] == 5

    def test_advance_ritual_custom_progress(self):
        """Test advancing ritual with custom progress amount."""
        state = SharedState()

        state.advance_ritual("Fast Ritual", progress=5)

        assert state.rituals["Fast Ritual"] == 5

    def test_multiple_rituals(self):
        """Test tracking multiple rituals."""
        state = SharedState()

        state.advance_ritual("Ritual A", progress=2)
        state.advance_ritual("Ritual B", progress=3)
        state.advance_ritual("Ritual A", progress=1)

        assert state.rituals["Ritual A"] == 3
        assert state.rituals["Ritual B"] == 3
        assert len(state.rituals) == 2


# ============================================================================
# Party Discoveries Tests
# ============================================================================

class TestPartyDiscoveries:
    """Test shared party knowledge system."""

    def test_add_discovery(self):
        """Test adding a discovery."""
        state = SharedState()

        state.add_discovery("Secret passage behind bookshelf", "Alice")

        assert len(state.party_discoveries) == 1
        assert state.party_discoveries[0]['discovery'] == "Secret passage behind bookshelf"
        assert state.party_discoveries[0]['character'] == "Alice"

    def test_add_duplicate_discovery(self):
        """Test duplicate discoveries are not added."""
        state = SharedState()

        state.add_discovery("Same info", "Alice")
        state.add_discovery("Same info", "Bob")  # Duplicate

        assert len(state.party_discoveries) == 1

    def test_add_discovery_no_character(self):
        """Test discovery without character attribution."""
        state = SharedState()

        state.add_discovery("Anonymous discovery")

        assert state.party_discoveries[0]['character'] == "Unknown"

    def test_add_empty_discovery(self):
        """Test empty discovery is not added."""
        state = SharedState()

        state.add_discovery("", "Alice")
        state.add_discovery(None, "Bob")

        assert len(state.party_discoveries) == 0

    def test_discovery_limit(self):
        """Test discovery list is limited to 10."""
        state = SharedState()

        # Add 15 discoveries
        for i in range(15):
            state.add_discovery(f"Discovery {i}", f"Player{i}")

        assert len(state.party_discoveries) == 10
        # Should keep most recent
        assert "Discovery 14" in state.party_discoveries[-1]['discovery']

    def test_get_recent_discoveries(self):
        """Test getting recent discoveries."""
        state = SharedState()

        for i in range(8):
            state.add_discovery(f"Info {i}", "Player")

        recent = state.get_recent_discoveries(limit=3)

        assert len(recent) == 3
        assert "Info 7" in recent[-1]['discovery']
        assert "Info 5" in recent[0]['discovery']

    def test_get_recent_discoveries_empty(self):
        """Test getting discoveries when none exist."""
        state = SharedState()

        recent = state.get_recent_discoveries()

        assert recent == []


# ============================================================================
# Player Registration Tests
# ============================================================================

class TestPlayerRegistration:
    """Test player registration system."""

    def test_register_player(self):
        """Test registering a player."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")

        assert len(state.registered_players) == 1
        assert state.registered_players[0]['name'] == "Alice"
        assert state.registered_players[0]['faction'] == "Witches"

    def test_register_duplicate_player(self):
        """Test duplicate registration is prevented."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_001", "Alice", "Witches")  # Duplicate

        assert len(state.registered_players) == 1

    def test_register_multiple_players(self):
        """Test registering multiple players."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")
        state.register_player("agent_003", "Carol", "Diplomats")

        assert len(state.registered_players) == 3

    def test_get_other_players(self):
        """Test getting other player names."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")
        state.register_player("agent_003", "Carol", "Diplomats")

        others = state.get_other_players("agent_002")

        assert len(others) == 2
        assert "Alice" in others
        assert "Carol" in others
        assert "Bob" not in others  # Excluded self

    def test_get_other_players_empty(self):
        """Test getting other players when only one exists."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")

        others = state.get_other_players("agent_001")

        assert others == []


# ============================================================================
# Coordination Bonus Tests
# ============================================================================

class TestCoordinationBonuses:
    """Test coordination bonus system."""

    def test_grant_coordination_bonus(self):
        """Test granting coordination bonus."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")

        success = state.grant_coordination_bonus(
            from_agent="agent_001",
            from_name="Alice",
            to_name="Bob",
            reason="Shared intel"
        )

        assert success is True
        assert "agent_002" in state.coordination_bonuses
        assert state.coordination_bonuses["agent_002"]['bonus'] == 2
        assert state.coordination_bonuses["agent_002"]['from'] == "Alice"
        assert state.coordination_bonuses["agent_002"]['reason'] == "Shared intel"

    def test_grant_bonus_to_nonexistent_player(self):
        """Test granting bonus to unregistered player fails."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")

        success = state.grant_coordination_bonus(
            from_agent="agent_001",
            from_name="Alice",
            to_name="NonexistentPlayer",
            reason="Test"
        )

        assert success is False
        assert len(state.coordination_bonuses) == 0

    def test_grant_bonus_case_insensitive(self):
        """Test bonus granting is case insensitive."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")

        success = state.grant_coordination_bonus(
            from_agent="agent_001",
            from_name="Alice",
            to_name="bob",  # Lowercase
            reason="Test"
        )

        assert success is True

    def test_coordination_bonus_replaces_existing(self):
        """Test new bonus replaces existing one."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")

        state.grant_coordination_bonus("agent_001", "Alice", "Bob", "First reason")
        state.grant_coordination_bonus("agent_001", "Alice", "Bob", "Second reason")

        assert state.coordination_bonuses["agent_002"]['reason'] == "Second reason"

    def test_multiple_coordination_bonuses(self):
        """Test multiple players can have bonuses."""
        state = SharedState()

        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")
        state.register_player("agent_003", "Carol", "Diplomats")

        state.grant_coordination_bonus("agent_001", "Alice", "Bob", "Reason A")
        state.grant_coordination_bonus("agent_001", "Alice", "Carol", "Reason B")

        assert len(state.coordination_bonuses) == 2
        assert "agent_002" in state.coordination_bonuses
        assert "agent_003" in state.coordination_bonuses


# ============================================================================
# Integration Tests
# ============================================================================

class TestSharedStateIntegration:
    """Test multiple systems working together."""

    def test_full_session_flow(self):
        """Test typical session flow with shared state."""
        state = SharedState()

        # Register players
        state.register_player("agent_001", "Alice", "Witches")
        state.register_player("agent_002", "Bob", "Hackers")

        # Good action
        state.adjust_soulcredit(2, reason="Helped civilians")
        state.add_discovery("Enemy base location", "Alice")

        # Coordination
        state.grant_coordination_bonus("agent_001", "Alice", "Bob", "Shared map")

        # Bad action
        state.adjust_soulcredit(-1, reason="Necessary violence")
        state.record_void_spike("Combat escalation", severity=1)

        # Ritual progress
        state.advance_ritual("Protective Ward", progress=2)

        # Verify state
        assert state.soulcredit_pool == 1
        assert len(state.party_discoveries) == 1
        assert "agent_002" in state.coordination_bonuses
        assert len(state.void_spikes) == 1
        assert state.rituals["Protective Ward"] == 2

    def test_escalation_scenarios(self):
        """Test multiple escalation triggers."""
        state = SharedState()
        state.soulcredit_floor = -4
        state.void_threshold = 3

        # Trigger soulcredit escalation
        sc_cue = state.adjust_soulcredit(-5, reason="Debt spiral")

        # Trigger void escalation
        state.record_void_spike("Major corruption", severity=3)
        void_cue = state.record_void_spike("Minor event", severity=1)

        assert sc_cue is not None
        assert void_cue is not None
        assert "debt collectors" in sc_cue.lower()
        assert "Void fallout" in void_cue

    def test_state_persistence(self):
        """Test state values persist across operations."""
        state = SharedState()

        # Build up state
        state.adjust_soulcredit(10, reason="Start bonus")
        state.advance_ritual("Test Ritual", progress=3)
        state.add_discovery("Test info", "Player")
        state.register_player("agent_001", "Player", "Faction")

        # Verify all persisted
        assert state.soulcredit_pool == 10
        assert state.rituals["Test Ritual"] == 3
        assert len(state.party_discoveries) == 1
        assert len(state.registered_players) == 1

    def test_empty_state(self):
        """Test newly created state has safe defaults."""
        state = SharedState()

        assert state.soulcredit_pool == 0
        assert len(state.void_spikes) == 0
        assert len(state.rituals) == 0
        assert len(state.party_discoveries) == 0
        assert len(state.registered_players) == 0
        assert len(state.coordination_bonuses) == 0
        assert state.soulcredit_floor == -4
        assert state.void_threshold == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
