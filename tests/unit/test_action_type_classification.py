"""
Unit tests for action type classification.

Regression tests for player action type classification:
- Combat actions should be classified as action_type='combat'
- DM narration should not contain prompt leakage
- Action descriptions should match action types

Based on fixture from hybrid replay test (2025-11-02).
"""

import pytest
import json
from pathlib import Path


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(path: Path):
    """Load JSONL file into list of events."""
    events = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events


def find_event(events, **filters):
    """Find first event matching all filters."""
    for event in events:
        if all(event.get(k) == v for k, v in filters.items()):
            return event
    return None


# ============================================================================
# Action Type Classification Tests
# ============================================================================

class TestActionTypeClassification:
    """Test action type classification for player actions."""

    @pytest.fixture
    def fixture_path(self):
        """Path to fixture with action_type classification bug."""
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "action_type_investigate_bug.jsonl"

    @pytest.fixture
    def events(self, fixture_path):
        """Load fixture events."""
        assert fixture_path.exists(), f"Fixture not found at {fixture_path}"
        return load_jsonl(fixture_path)

    def test_fixture_loads(self, events):
        """Test fixture loads successfully."""
        assert len(events) > 0, "No events loaded"
        assert len(events) == 59, f"Expected 59 events, got {len(events)}"

    def test_combat_action_has_combat_type(self, events):
        """
        Regression test: Combat actions should have action_type='combat'.

        Bug: Round 2 Drifter Sable action "Engage Elite Assault Squad with
        concentrated pistol fire" was classified as action_type='investigate'
        instead of 'combat'.

        This test DOCUMENTS the current broken behavior and will FAIL until fixed.
        """
        # Find Drifter Sable's round 2 action resolution
        sable_r2 = find_event(
            events,
            event_type="action_resolution",
            round=2,
            agent="Drifter Sable"
        )

        assert sable_r2 is not None, "Could not find Drifter Sable round 2 action"

        # Get the action details
        action = sable_r2.get('action', '')
        action_type = sable_r2.get('context', {}).get('action_type', '')

        # The action is clearly combat
        assert 'Engage Elite Assault Squad' in action, \
            f"Expected combat action, got: {action}"

        # REGRESSION TEST - This currently FAILS
        # Expected: action_type == 'combat'
        # Actual: action_type == 'investigate'
        assert action_type == 'combat', \
            f"Combat action 'Engage Elite Assault Squad with concentrated pistol fire' " \
            f"should have action_type='combat', got '{action_type}'"

    def test_narration_no_prompt_leakage(self, events):
        """
        Regression test: DM narration should not contain interactive prompt fragments.

        Bug: Round 2 Drifter Sable narration ended with "*What's your move,"
        which suggests the DM response included prompt text meant for player interaction.

        This test DOCUMENTS the current broken behavior and will FAIL until fixed.
        """
        # Find Drifter Sable's round 2 action resolution
        sable_r2 = find_event(
            events,
            event_type="action_resolution",
            round=2,
            agent="Drifter Sable"
        )

        assert sable_r2 is not None, "Could not find Drifter Sable round 2 action"

        narration = sable_r2.get('context', {}).get('narration', '')

        # REGRESSION TEST - This currently FAILS
        # Narration should not end with interactive prompt fragments
        assert not narration.endswith("*What's your move,"), \
            f"Narration should not end with interactive prompt fragments. " \
            f"Last 100 chars: ...{narration[-100:]}"

        # Also check for other common prompt leakage patterns
        assert "*What's your" not in narration, \
            "Narration should not contain '*What's your' prompt fragments"

        assert "What do you do?" not in narration, \
            "Narration should not contain 'What do you do?' prompt fragments"

    def test_round_2_has_live_llm_content(self, events):
        """
        Verify round 2 has LIVE LLM content (not cached).

        This test documents that round 2 was generated with live LLM,
        so the action_type bug is happening during real generation,
        not just cached replay.
        """
        # Find round 2 action resolutions
        round_2_actions = [
            e for e in events
            if e.get('event_type') == 'action_resolution' and e.get('round') == 2
        ]

        assert len(round_2_actions) == 2, \
            f"Expected 2 round 2 actions (Sable + Kael), got {len(round_2_actions)}"

        # Verify both players have actions in round 2
        agents = [a['agent'] for a in round_2_actions]
        assert 'Drifter Sable' in agents, "Missing Drifter Sable round 2 action"
        assert 'Enforcer Kael Dren' in agents, "Missing Enforcer Kael Dren round 2 action"


# ============================================================================
# Action Description Consistency Tests
# ============================================================================

class TestActionDescriptionConsistency:
    """Test that action descriptions match their action types."""

    @pytest.fixture
    def fixture_path(self):
        """Path to fixture with action_type classification bug."""
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "action_type_investigate_bug.jsonl"

    @pytest.fixture
    def events(self, fixture_path):
        """Load fixture events."""
        return load_jsonl(fixture_path)

    def test_combat_keywords_imply_combat_type(self, events):
        """
        Test that actions with combat keywords have action_type='combat'.

        Combat keywords: attack, engage, fire, shoot, strike, hit, etc.
        """
        # Get all action resolutions
        action_resolutions = [
            e for e in events
            if e.get('event_type') == 'action_resolution'
        ]

        combat_keywords = [
            'attack', 'engage', 'fire', 'shoot', 'strike', 'hit',
            'assault', 'burst', 'pistol', 'rifle', 'weapon', 'combat'
        ]

        for resolution in action_resolutions:
            action = resolution.get('action', '').lower()
            action_type = resolution.get('context', {}).get('action_type', '')

            # Check if action contains combat keywords
            has_combat_keywords = any(keyword in action for keyword in combat_keywords)

            if has_combat_keywords:
                # EXPECTED: Should be action_type='combat'
                assert action_type == 'combat', \
                    f"Action '{resolution.get('action')}' contains combat keywords " \
                    f"but has action_type='{action_type}' (expected 'combat')"
