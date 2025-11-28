"""
Tests for NPC memory and dialogue progression system.

Tests verify:
1. NPCs track their own previous actions
2. NPCs receive deduplicated context (no repeated events)
3. NPCs track interactions with specific characters
4. NPC goals can evolve based on interactions
5. NPC prompts include memory context
"""

import pytest
from unittest.mock import Mock, AsyncMock
from dataclasses import dataclass

from scripts.aeonisk.multiagent.npc_agent import NPCAgent, NPCLLMClient, NPCAction, NPCMemory


class TestNPCMemoryBasics:
    """Test basic NPC memory tracking functionality."""

    def test_npc_memory_initialization(self):
        """Test: NPCMemory initializes with empty state."""
        memory = NPCMemory()

        assert memory.own_actions == []
        assert memory.interactions == {}
        assert memory.current_goal is None
        assert memory.seen_event_hashes == set()

    def test_npc_memory_record_own_action(self):
        """Test: NPC can record its own actions."""
        memory = NPCMemory()

        memory.record_own_action(
            round_num=1,
            action_type="dialogue",
            dialogue="IDs and manifests, please.",
            target="Broker Callum Vex"
        )

        assert len(memory.own_actions) == 1
        assert memory.own_actions[0]['round'] == 1
        assert memory.own_actions[0]['action_type'] == "dialogue"
        assert memory.own_actions[0]['dialogue'] == "IDs and manifests, please."
        assert memory.own_actions[0]['target'] == "Broker Callum Vex"

    def test_npc_memory_limits_action_history(self):
        """Test: NPC memory limits stored actions to prevent bloat."""
        memory = NPCMemory(max_own_actions=3)

        for i in range(5):
            memory.record_own_action(
                round_num=i,
                action_type="dialogue",
                dialogue=f"Message {i}"
            )

        # Should only keep last 3
        assert len(memory.own_actions) == 3
        assert memory.own_actions[0]['dialogue'] == "Message 2"
        assert memory.own_actions[-1]['dialogue'] == "Message 4"


class TestNPCInteractionTracking:
    """Test NPC interaction tracking with specific characters."""

    def test_record_interaction(self):
        """Test: NPC can record interactions with characters."""
        memory = NPCMemory()

        memory.record_interaction(
            character_name="Broker Callum Vex",
            interaction_type="charmed",
            details="Accepted a Drip bribe, now agreeable",
            round_num=2
        )

        assert "Broker Callum Vex" in memory.interactions
        assert len(memory.interactions["Broker Callum Vex"]) == 1
        interaction = memory.interactions["Broker Callum Vex"][0]
        assert interaction['type'] == "charmed"
        assert interaction['round'] == 2

    def test_multiple_interactions_same_character(self):
        """Test: NPC tracks multiple interactions with same character."""
        memory = NPCMemory()

        memory.record_interaction("Ash", "suspicious", "Noticed Tempest sigil", round_num=1)
        memory.record_interaction("Ash", "questioned", "Asked for ID", round_num=2)
        memory.record_interaction("Ash", "mollified", "Accepted explanation", round_num=3)

        assert len(memory.interactions["Ash"]) == 3
        # Most recent should be last
        assert memory.interactions["Ash"][-1]['type'] == "mollified"

    def test_get_relationship_summary(self):
        """Test: NPC can generate relationship summary for prompt."""
        memory = NPCMemory()

        memory.record_interaction("Broker Callum Vex", "charmed", "Gave me a Drip", round_num=2)
        memory.record_interaction("Reaver Keth", "suspicious", "Made noise in ducts", round_num=2)

        summary = memory.get_relationship_summary()

        assert "Broker Callum Vex" in summary
        assert "charmed" in summary.lower()
        assert "Reaver Keth" in summary
        assert "suspicious" in summary.lower()


class TestNPCGoalEvolution:
    """Test NPC goal tracking and evolution."""

    def test_initial_goal_from_personality(self):
        """Test: NPC can have initial goal based on personality."""
        memory = NPCMemory()
        memory.set_goal("Check IDs and wave arrivals through the docking bay")

        assert memory.current_goal == "Check IDs and wave arrivals through the docking bay"

    def test_goal_evolution(self):
        """Test: NPC goal can evolve based on events."""
        memory = NPCMemory()
        memory.set_goal("Check IDs and wave arrivals through")

        # After noticing something suspicious
        memory.set_goal("Watch the merchant with the Tempest sigil more closely")

        assert "Tempest sigil" in memory.current_goal
        # Goal history only contains PREVIOUS goals (not current)
        assert len(memory.goal_history) == 1
        assert memory.goal_history[0] == "Check IDs and wave arrivals through"

    def test_goal_history_limited(self):
        """Test: Goal history is limited to prevent bloat."""
        memory = NPCMemory(max_goal_history=3)

        for i in range(5):
            memory.set_goal(f"Goal {i}")

        assert len(memory.goal_history) == 3
        assert memory.current_goal == "Goal 4"


class TestNPCEventDeduplication:
    """Test event deduplication to prevent repeated context."""

    def test_event_hash_tracking(self):
        """Test: NPC tracks seen event hashes."""
        memory = NPCMemory()

        event1 = "[Broker Callum Vex] Charms the dockhand successfully"
        event2 = "[Spectre Voss] Slips into shadows"

        # First time seeing events
        assert not memory.has_seen_event(event1)
        assert not memory.has_seen_event(event2)

        memory.mark_event_seen(event1)
        memory.mark_event_seen(event2)

        # Now should recognize them
        assert memory.has_seen_event(event1)
        assert memory.has_seen_event(event2)

    def test_filter_unseen_events(self):
        """Test: NPC can filter to only unseen events."""
        memory = NPCMemory()

        events = [
            "[Ash] Does something new",
            "[Marcus] Already seen this",
            "[Vex] Another new event",
        ]

        # Mark one as seen
        memory.mark_event_seen("[Marcus] Already seen this")

        unseen = memory.filter_unseen_events(events)

        assert len(unseen) == 2
        assert "[Marcus] Already seen this" not in unseen
        assert "[Ash] Does something new" in unseen
        assert "[Vex] Another new event" in unseen

    def test_seen_events_limited_to_prevent_memory_bloat(self):
        """Test: Seen event cache is limited."""
        memory = NPCMemory(max_seen_events=100)

        # Add 150 events
        for i in range(150):
            memory.mark_event_seen(f"Event {i}")

        # Should have pruned oldest
        assert len(memory.seen_event_hashes) <= 100


class TestNPCMemoryPromptGeneration:
    """Test NPC memory integration with prompt generation."""

    def test_get_memory_context_for_prompt(self):
        """Test: NPCMemory generates context string for prompt."""
        memory = NPCMemory()

        # Add some history
        memory.record_own_action(1, "dialogue", "IDs please", target="arrivals")
        memory.record_own_action(2, "dialogue", "Keep that cuff visible", target="Broker")
        memory.record_interaction("Broker Callum Vex", "charmed", "Gave me a Drip", round_num=2)
        memory.set_goal("Watch the Tempest sigil guy")

        context = memory.get_memory_context()

        # Should include own actions
        assert "IDs please" in context or "Keep that cuff visible" in context
        # Should include relationships
        assert "Broker" in context
        # Should include goal
        assert "Tempest" in context or "goal" in context.lower()

    def test_memory_context_empty_when_no_history(self):
        """Test: Empty memory returns minimal context."""
        memory = NPCMemory()

        context = memory.get_memory_context()

        # Should be empty or very minimal
        assert context == "" or "no previous" in context.lower()


class TestNPCAgentWithMemory:
    """Test NPCAgent integration with memory system."""

    @pytest.fixture
    def npc_with_memory(self):
        """Create NPC agent with memory enabled."""
        npc = NPCAgent(
            agent_id="npc_dockhand_001",
            name="Bored Dockhand",
            faction="Freeborn Pirates",
            entity_type="neutral",
            disposition="wary",
            threat_level="armed_neutral",
            description="A bored pirate with a rusted shotgun waving arrivals through the docking bay.",
            health=22,
            max_health=22,
            soak=2,
            void_score=0,
            can_act=True
        )
        return npc

    def test_npc_agent_has_memory(self, npc_with_memory):
        """Test: NPCAgent has memory attribute."""
        assert hasattr(npc_with_memory, 'memory')
        assert isinstance(npc_with_memory.memory, NPCMemory)

    def test_npc_memory_persists_across_rounds(self, npc_with_memory):
        """Test: NPC memory persists between action declarations."""
        npc = npc_with_memory

        # Simulate round 1 action
        npc.memory.record_own_action(1, "dialogue", "IDs please")

        # Simulate round 2 - memory should still have round 1
        npc.memory.record_own_action(2, "dialogue", "Keep that cuff visible")

        assert len(npc.memory.own_actions) == 2


class TestNPCLLMClientWithMemory:
    """Test NPCLLMClient memory integration."""

    @pytest.fixture
    def mock_npc_with_memory(self):
        """Create mock NPC with memory for LLM client testing."""
        npc = Mock(spec=NPCAgent)
        npc.agent_id = "npc_test_123"
        npc.name = "Test Dockhand"
        npc.description = "A wary guard"
        npc.disposition = "wary"
        npc.entity_type = "neutral"
        npc.threat_level = "armed_neutral"
        npc.faction = "Freeborn Pirates"
        npc.health = 22
        npc.max_health = 22
        npc.stuns = 0
        npc.wounds = 0
        npc.can_act = True

        # Add real memory
        npc.memory = NPCMemory()
        npc.memory.record_own_action(1, "dialogue", "IDs and manifests, please")
        npc.memory.record_interaction("Broker Callum Vex", "charmed", "Gave me a Drip", round_num=2)
        npc.memory.set_goal("Watch the Tempest sigil merchant")

        return npc

    def test_llm_client_includes_memory_in_prompt(self, mock_npc_with_memory):
        """Test: NPCLLMClient includes memory context in prompt."""
        client = NPCLLMClient(
            npc=mock_npc_with_memory,
            llm_provider=None  # No LLM needed for prompt testing
        )

        context = "Round 2: Calm situation. 3 players present."
        prompt = client._build_prompt(context)

        # Should include memory section
        assert "**Your Memory:**" in prompt or "**What You Remember:**" in prompt
        # Should include previous action
        assert "IDs and manifests" in prompt
        # Should include relationship
        assert "Broker" in prompt or "charmed" in prompt
        # Should include goal
        assert "Tempest" in prompt or "Watch" in prompt

    def test_llm_client_handles_empty_memory(self):
        """Test: NPCLLMClient handles NPC with no memory gracefully."""
        npc = Mock(spec=NPCAgent)
        npc.agent_id = "npc_new"
        npc.name = "New NPC"
        npc.description = "Fresh NPC"
        npc.disposition = "neutral"
        npc.entity_type = "neutral"
        npc.threat_level = "non_combatant"
        npc.faction = "Civilian"
        npc.health = 10
        npc.max_health = 10
        npc.stuns = 0
        npc.wounds = 0
        npc.can_act = True
        npc.memory = NPCMemory()  # Empty memory

        client = NPCLLMClient(npc=npc, llm_provider=None)

        context = "Round 1: Calm situation. 2 players present."
        prompt = client._build_prompt(context)

        # Should not crash, should have basic structure
        assert "**Current Situation:**" in prompt
        assert "**Your Status:**" in prompt


class TestNPCContextDeduplicationIntegration:
    """Test that session.py properly deduplicates NPC context."""

    def test_deduplicate_narrations_for_npc(self):
        """
        Test: Narrations passed to NPC are deduplicated across rounds.

        This simulates what session.py should do when building NPC context.
        The deduplication works by marking events as seen after showing them,
        so on subsequent rounds, duplicates are filtered out.
        """
        memory = NPCMemory()

        # Round 1: First batch of events
        round1_narrations = [
            "[Broker Callum Vex] Charms the dockhand successfully",
            "[Spectre Voss] Slips into shadows",
        ]

        # Filter and mark as seen
        unseen1 = memory.filter_unseen_events(round1_narrations)
        for event in unseen1:
            memory.mark_event_seen(event)

        # Both should be shown (first time seeing them)
        assert len(unseen1) == 2

        # Round 2: Some duplicates, some new
        round2_narrations = [
            "[Broker Callum Vex] Charms the dockhand successfully",  # DUPLICATE
            "[Reaver Keth] Makes noise in ducts",  # NEW
            "[Spectre Voss] Slips into shadows",  # DUPLICATE
        ]

        unseen2 = memory.filter_unseen_events(round2_narrations)

        # Only the new one should be shown
        assert len(unseen2) == 1
        assert "[Reaver Keth] Makes noise in ducts" in unseen2
        assert "[Broker Callum Vex] Charms the dockhand successfully" not in unseen2

    def test_new_events_shown_old_events_filtered(self):
        """
        Test: New round events shown, old round events filtered.

        Simulates multi-round progression.
        """
        memory = NPCMemory()

        # Round 1 events
        round1_events = [
            "[Ash] Scans the area",
            "[Marcus] Talks to guard",
        ]

        # Process round 1
        for event in round1_events:
            memory.mark_event_seen(event)

        # Round 2 events (includes duplicates from round 1)
        round2_events = [
            "[Ash] Scans the area",  # OLD - should filter
            "[Marcus] Talks to guard",  # OLD - should filter
            "[Ash] Hacks the terminal",  # NEW
            "[Vex] Charms the dockhand",  # NEW
        ]

        new_events = memory.filter_unseen_events(round2_events)

        assert len(new_events) == 2
        assert "[Ash] Hacks the terminal" in new_events
        assert "[Vex] Charms the dockhand" in new_events
        assert "[Ash] Scans the area" not in new_events
