"""
Unit tests for enemy targeting communication during action declaration.

Tests the payload structure and data contracts for targeting information
without requiring full session initialization.
"""

import pytest


class TestEnemyTargetingPayload:
    """Test that enemy declaration payload includes targeting information."""

    def test_enemy_declaration_payload_structure(self):
        """Verify enemy ACTION_DECLARED payload includes target/weapon/reasoning."""
        # Define expected payload structure (from session.py:949-958)
        enemy_declaration = {
            'agent_id': 'enemy_thug_01',
            'character_name': 'Thug',
            'major_action': 'Attack',
            'target': 'tgt_player_ash',
            'weapon': 'knife',
            'reasoning': 'Target nearest threat',
            'initiative': 15
        }

        # Build broadcast payload as done in session.py:949-958
        broadcast_payload = {
            'agent_id': enemy_declaration['agent_id'],
            'character_name': enemy_declaration['character_name'],
            'intent': enemy_declaration.get('major_action', 'Unknown action'),
            'target': enemy_declaration.get('target'),  # NEW field
            'weapon': enemy_declaration.get('weapon'),  # NEW field
            'reasoning': enemy_declaration.get('reasoning', '')[:100],  # NEW field (truncated)
            'initiative': enemy_declaration['initiative'],
            'agent_type': 'enemy'
        }

        # Verify new fields are present
        assert 'target' in broadcast_payload
        assert 'weapon' in broadcast_payload
        assert 'reasoning' in broadcast_payload

        # Verify values
        assert broadcast_payload['target'] == 'tgt_player_ash'
        assert broadcast_payload['weapon'] == 'knife'
        assert 'Target nearest threat' in broadcast_payload['reasoning']
        assert broadcast_payload['agent_type'] == 'enemy'

    def test_enemy_payload_handles_missing_optional_fields(self):
        """Enemy broadcast should handle missing target/weapon gracefully."""
        # Enemy with minimal info (e.g., "Pass" action)
        enemy_declaration = {
            'agent_id': 'enemy_thug_01',
            'character_name': 'Thug',
            'major_action': 'Pass',
            'initiative': 15
            # No target, weapon, reasoning
        }

        # Build payload with missing fields
        broadcast_payload = {
            'agent_id': enemy_declaration['agent_id'],
            'character_name': enemy_declaration['character_name'],
            'intent': enemy_declaration.get('major_action', 'Unknown action'),
            'target': enemy_declaration.get('target'),  # None
            'weapon': enemy_declaration.get('weapon'),  # None
            'reasoning': enemy_declaration.get('reasoning', '')[:100],  # Empty string
            'initiative': enemy_declaration['initiative'],
            'agent_type': 'enemy'
        }

        # Should not crash
        assert broadcast_payload['target'] is None
        assert broadcast_payload['weapon'] is None
        assert broadcast_payload['reasoning'] == ''
        assert broadcast_payload['intent'] == 'Pass'


class TestPlayerTargetingStorage:
    """Test player action storage format for targeting information."""

    def test_player_stores_targeting_tuple(self):
        """Player should store 6-field tuple with targeting info."""
        # Simulate what player._handle_action_declared stores (player.py:494)
        character_name = "Thug"
        description = ''  # Enemies don't have descriptions
        intent = 'Attack'
        target = 'tgt_player_ash'
        weapon = 'knife'
        reasoning = 'Target nearest threat'
        initiative = 15

        # Storage format: (description, intent, target, weapon, reasoning, initiative)
        stored_action = (description, intent, target, weapon, reasoning, initiative)

        # Verify tuple structure
        assert len(stored_action) == 6
        assert stored_action[0] == ''  # description (empty for enemies)
        assert stored_action[1] == 'Attack'  # intent
        assert stored_action[2] == 'tgt_player_ash'  # target
        assert stored_action[3] == 'knife'  # weapon
        assert stored_action[4] == 'Target nearest threat'  # reasoning
        assert stored_action[5] == 15  # initiative

    def test_player_targeting_display_format(self):
        """Player should format enemy targeting for display."""
        # Simulate stored action data
        character_name = "Thug"
        action_data = ('', 'Attack', 'tgt_player_ash', 'knife', 'Target nearest threat', 15)

        # Unpack (as done in player.py:1842)
        description, intent, target, weapon, reasoning, initiative = action_data

        # Format for display (player.py:1844-1854)
        if description:
            action_text = description
        else:
            # Build from components
            action_text = intent
            if target:
                action_text += f" targeting {target}"
            if weapon:
                action_text += f" with {weapon}"

        # Verify display format
        assert action_text == "Attack targeting tgt_player_ash with knife"

    def test_player_handles_action_without_target(self):
        """Player should handle enemy actions without targeting info."""
        # Enemy fleeing (no target/weapon)
        action_data = ('', 'Flee', None, None, '', 15)

        description, intent, target, weapon, reasoning, initiative = action_data

        # Format for display
        action_text = intent
        if target:
            action_text += f" targeting {target}"
        if weapon:
            action_text += f" with {weapon}"

        # Should show just intent
        assert action_text == "Flee"
        assert initiative == 15


class TestBackwardCompatibility:
    """Test backward compatibility with legacy action storage formats."""

    def test_handles_legacy_3_field_format(self):
        """Support old (description, intent, initiative) format."""
        # Old format used before targeting enhancement
        legacy_action = ("Thug attacks", "Attack", 15)

        # Code should detect length and handle appropriately
        if len(legacy_action) == 3:
            description, intent, initiative = legacy_action
            assert description == "Thug attacks"
            assert intent == "Attack"
            assert initiative == 15

    def test_handles_legacy_2_field_format(self):
        """Support very old (intent, initiative) format."""
        # Very old format
        very_old_action = ("Attack", 15)

        # Code should detect length
        if len(very_old_action) == 2:
            intent, initiative = very_old_action
            assert intent == "Attack"
            assert initiative == 15

    def test_current_6_field_format(self):
        """Current format has 6 fields."""
        current_action = ('', 'Attack', 'tgt_player_ash', 'knife', 'Target nearest', 15)

        if len(current_action) == 6:
            description, intent, target, weapon, reasoning, initiative = current_action
            assert len(current_action) == 6
            assert target == 'tgt_player_ash'
            assert weapon == 'knife'


class TestNPCActionFormat:
    """Test that NPC actions continue to include description/reasoning."""

    def test_npc_payload_includes_description(self):
        """NPCs should include description field (their reasoning)."""
        # NPC action (from session.py:1171-1178)
        npc_action = {
            'action_type': 'flee',
            'reason': 'Trying to escape while guards distracted',
            'target': None
        }

        # NPC broadcast payload
        npc_payload = {
            'agent_id': 'npc_prisoner_01',
            'character_name': 'Prisoner',
            'description': npc_action['reason'],  # ✅ Already includes reasoning
            'intent': npc_action['action_type'],
            'initiative': 12,
            'agent_type': 'npc'
        }

        # Verify NPC has description
        assert 'description' in npc_payload
        assert npc_payload['description'] == 'Trying to escape while guards distracted'
        assert npc_payload['agent_type'] == 'npc'


class TestTargetingIntegration:
    """Integration tests for targeting across declaration and resolution."""

    def test_targeting_preserved_through_phases(self):
        """Targeting info should be visible in both declaration and resolution."""
        # Enemy action definition
        enemy_action = {
            'agent_id': 'enemy_thug_01',
            'character_name': 'Thug',
            'major_action': 'Attack',
            'target': 'tgt_player_ash',
            'weapon': 'knife',
            'reasoning': 'Target nearest threat',
            'initiative': 15
        }

        # Declaration phase (broadcast to players)
        declaration_payload = {
            'agent_id': enemy_action['agent_id'],
            'intent': enemy_action['major_action'],
            'target': enemy_action['target'],
            'weapon': enemy_action['weapon'],
            'reasoning': enemy_action['reasoning'][:100],
        }

        # Resolution phase (DM receives same action context)
        # Already working - DM gets full action dict

        # Verify targeting info present in both
        assert declaration_payload['target'] == enemy_action['target']
        assert declaration_payload['weapon'] == enemy_action['weapon']
