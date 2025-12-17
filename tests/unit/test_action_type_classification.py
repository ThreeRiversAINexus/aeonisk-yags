"""
Unit tests for action type classification.

Tests for player action type classification:
- Combat actions should be classified as action_type='combat' or 'attack'
- DM narration should not contain prompt leakage
- Action descriptions should match action types

Uses fixture from bulk generation run (2025-11-28).
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
        """Path to fixture with action classifications."""
        # Using debt_auction_ambush as general-purpose combat fixture
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "session_debt_auction_ambush.jsonl"

    @pytest.fixture
    def events(self, fixture_path):
        """Load fixture events."""
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found at {fixture_path}")
        return load_jsonl(fixture_path)

    def test_fixture_loads(self, events):
        """Test fixture loads successfully."""
        assert len(events) > 0, "No events loaded"
        # Bulk generation fixture has many events
        assert len(events) >= 100, f"Expected at least 100 events, got {len(events)}"

    def test_combat_actions_have_combat_type(self, events):
        """
        Test that actions with combat keywords are classified as combat/attack.

        Combat keywords in action text should result in action_type='combat' or 'attack'.
        """
        combat_keywords = ['attack', 'charges', 'hit', 'fires', 'shoots']

        # Find action resolutions with combat keywords
        action_resolutions = [
            e for e in events
            if e.get('event_type') == 'action_resolution'
        ]

        combat_actions_found = 0
        for resolution in action_resolutions:
            action = resolution.get('action', '').lower()
            action_type = resolution.get('context', {}).get('action_type', '')

            # Check if action contains combat keywords
            has_combat_keywords = any(keyword in action for keyword in combat_keywords)

            if has_combat_keywords:
                combat_actions_found += 1
                assert action_type in ('combat', 'attack'), \
                    f"Action '{resolution.get('action')[:80]}...' has combat keywords " \
                    f"but action_type='{action_type}' (expected 'combat' or 'attack')"

        # Ensure we actually tested something
        assert combat_actions_found > 0, "No combat actions found in fixture"

    def test_narration_no_prompt_leakage(self, events):
        """
        Test that DM narration does not contain interactive prompt fragments.

        Narration should not include text meant for player interaction like
        "What's your move" or "What do you do?".
        """
        action_resolutions = [
            e for e in events
            if e.get('event_type') == 'action_resolution'
        ]

        prompt_leakage_patterns = [
            "*What's your",
            "What do you do?",
            "What's your move",
            "Your turn.",
            "What will you do?"
        ]

        for resolution in action_resolutions:
            narration = resolution.get('context', {}).get('narration', '')

            for pattern in prompt_leakage_patterns:
                assert pattern not in narration, \
                    f"Narration contains prompt leakage '{pattern}'. " \
                    f"Agent: {resolution.get('agent')}, Round: {resolution.get('round')}"

    def test_multiple_rounds_exist(self, events):
        """
        Verify fixture has multiple rounds of combat.
        """
        rounds = set()
        for e in events:
            if e.get('event_type') == 'action_resolution' and e.get('round'):
                rounds.add(e['round'])

        assert len(rounds) >= 2, f"Expected at least 2 rounds, got {len(rounds)}: {rounds}"


# ============================================================================
# Action Description Consistency Tests
# ============================================================================

class TestActionDescriptionConsistency:
    """Test that action descriptions match their action types."""

    @pytest.fixture
    def fixture_path(self):
        """Path to fixture with action classifications."""
        # Using debt_auction_ambush as general-purpose combat fixture
        return Path(__file__).parent.parent / "fixtures" / "sessions" / "session_debt_auction_ambush.jsonl"

    @pytest.fixture
    def events(self, fixture_path):
        """Load fixture events."""
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found at {fixture_path}")
        return load_jsonl(fixture_path)

    def test_combat_keywords_imply_combat_type(self, events):
        """
        Test that actions with combat keywords have action_type='combat' or 'attack'.

        Combat keywords: attack, engage, fire, shoot, strike, hit, charges, etc.
        """
        # Get all action resolutions
        action_resolutions = [
            e for e in events
            if e.get('event_type') == 'action_resolution'
        ]

        combat_keywords = [
            'attack', 'charges', 'hit', 'fires', 'shoots'
        ]

        misclassified = []
        for resolution in action_resolutions:
            action = resolution.get('action', '').lower()
            action_type = resolution.get('context', {}).get('action_type', '')

            # Check if action contains combat keywords
            has_combat_keywords = any(keyword in action for keyword in combat_keywords)

            if has_combat_keywords and action_type not in ('combat', 'attack'):
                misclassified.append({
                    'action': resolution.get('action', '')[:80],
                    'type': action_type,
                    'round': resolution.get('round'),
                    'agent': resolution.get('agent')
                })

        assert len(misclassified) == 0, \
            f"Found {len(misclassified)} misclassified combat actions: {misclassified[:3]}"

    def test_social_actions_have_social_type(self, events):
        """
        Test that social actions are classified correctly.
        """
        action_resolutions = [
            e for e in events
            if e.get('event_type') == 'action_resolution'
        ]

        social_keywords = ['bluff', 'negotiate', 'persuade', 'deceive', 'intimidate', 'broadcast']

        for resolution in action_resolutions:
            action = resolution.get('action', '').lower()
            action_type = resolution.get('context', {}).get('action_type', '')

            # Check if action contains social keywords
            has_social_keywords = any(keyword in action for keyword in social_keywords)

            if has_social_keywords:
                assert action_type == 'social', \
                    f"Action '{resolution.get('action')[:60]}...' has social keywords " \
                    f"but action_type='{action_type}' (expected 'social')"
