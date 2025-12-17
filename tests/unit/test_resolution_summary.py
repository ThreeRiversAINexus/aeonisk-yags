"""
Unit tests for Session._build_resolution_summary() method.

Tests for bug fix: AttributeError when effects is None
Issue: Line 2114 in session.py tried to call .get() on None when effects field was None
"""

import pytest
from scripts.aeonisk.multiagent.session import SelfPlayingSession


class TestBuildResolutionSummary:
    """Test SelfPlayingSession._build_resolution_summary() edge cases."""

    @pytest.fixture
    def build_resolution_summary(self):
        """Get the _build_resolution_summary method for direct testing."""
        # Test the method directly without full session initialization
        # This is valid since _build_resolution_summary is a pure function that only
        # processes the input list without accessing session state
        session = object.__new__(SelfPlayingSession)
        return session._build_resolution_summary

    def test_empty_resolutions(self, build_resolution_summary):
        """Test with empty resolution list."""
        result = build_resolution_summary([])
        assert result == "No resolutions this round"

    def test_resolution_with_none_effects(self, build_resolution_summary):
        """Test resolution where effects field is None (regression test)."""
        # This was causing AttributeError: 'NoneType' object has no attribute 'get'
        resolution = {
            'character_name': 'Test Character',
            'action_description': 'Test action',
            'success': True,
            'effects': None  # BUG: This caused crash on line 2114
        }

        # Should NOT crash - should handle None gracefully
        result = build_resolution_summary([resolution])

        # Verify output format
        assert "Test Character" in result
        assert "Test action" in result
        assert "SUCCESS" in result
        # Should NOT include damage text when effects is None
        assert "dealt" not in result

    def test_resolution_with_missing_effects(self, build_resolution_summary):
        """Test resolution where effects field is missing entirely."""
        resolution = {
            'character_name': 'Test Character',
            'action_description': 'Test action',
            'success': False
            # No 'effects' key at all
        }

        result = build_resolution_summary([resolution])

        assert "Test Character" in result
        assert "FAIL" in result
        assert "dealt" not in result

    def test_resolution_with_pydantic_effects(self, build_resolution_summary):
        """Test resolution with Pydantic ActionResolution effects (object)."""
        # Mock a Pydantic-like object with damage
        # Note: damage is now a List[DamageEffect], not a single object
        class MockDamage:
            dealt = 12

        class MockEffects:
            damage = [MockDamage()]  # List of damage effects

        resolution = {
            'character_name': 'Test Character',
            'action_description': 'Shoots enemy',
            'success': True,
            'effects': MockEffects()
        }

        result = build_resolution_summary([resolution])

        # Format shows "Damage: X" for Pydantic effects
        assert "Damage: 12" in result

    def test_resolution_with_dict_effects(self, build_resolution_summary):
        """Test resolution with dict-based effects (enemy combat format)."""
        resolution = {
            'character_name': 'Enemy Grunt',
            'action_description': 'Attacks player',
            'success': True,
            'effects': {
                'damage': {
                    'dealt': 8
                }
            }
        }

        result = build_resolution_summary([resolution])

        # Format changed: now shows "Damage: X" instead of "dealt X damage"
        assert "Damage: 8" in result or "dealt 8 damage" in result

    def test_resolution_with_empty_damage(self, build_resolution_summary):
        """Test resolution with effects but no damage dealt."""
        resolution = {
            'character_name': 'Test Character',
            'action_description': 'Misses shot',
            'success': False,
            'effects': {
                'damage': {
                    'dealt': 0
                }
            }
        }

        result = build_resolution_summary([resolution])

        # Should NOT include damage text when dealt is 0 (falsy)
        assert "dealt" not in result

    def test_resolution_with_none_damage_in_dict(self, build_resolution_summary):
        """Test resolution with effects dict where damage key is None (actual bug)."""
        # This is the ACTUAL bug: effects is a dict but damage value is None
        # effects.get('damage', {}) returns None, then .get('dealt') on None crashes
        resolution = {
            'character_name': 'Test Character',
            'action_description': 'Test action',
            'success': True,
            'effects': {
                'damage': None  # BUG: This causes crash on line 2114
            }
        }

        # Should NOT crash - should handle None damage gracefully
        result = build_resolution_summary([resolution])

        assert "Test Character" in result
        assert "dealt" not in result

    def test_multiple_resolutions_mixed_formats(self, build_resolution_summary):
        """Test with mix of PC/NPC and enemy resolution formats."""
        class MockDamage:
            dealt = 15

        class MockEffects:
            damage = [MockDamage()]  # List of damage effects

        resolutions = [
            {
                'character_name': 'Player 1',
                'action_description': 'Shoots enemy',
                'success': True,
                'effects': MockEffects()
            },
            {
                'character_name': 'Enemy 1',
                'action_description': 'Attacks player',
                'success': True,
                'effects': None  # Enemy used surrender/flee (no damage)
            },
            {
                'character_name': 'Player 2',
                'action_description': 'Investigates terminal',
                'success': False,
                'effects': None
            }
        ]

        result = build_resolution_summary(resolutions)

        # Verify all three resolutions appear
        assert "Player 1" in result
        assert "Enemy 1" in result
        assert "Player 2" in result

        # Verify damage only appears for Player 1 (format: "Damage: X")
        assert "Damage: 15" in result
        assert result.count("Damage:") == 1  # Only one damage entry

    def test_long_action_truncation(self, build_resolution_summary):
        """Test that long action descriptions are truncated."""
        resolution = {
            'character_name': 'Test Character',
            'action_description': 'A' * 150,  # 150 characters
            'success': True,
            'effects': None
        }

        result = build_resolution_summary([resolution])

        # Should be truncated (original 150 chars reduced)
        assert "..." in result
        # Find the line with the action
        for line in result.split('\n'):
            if 'Test Character' in line:
                # Extract action portion (between "Character: " and " (SUCCESS)")
                action_part = line.split(': ', 1)[1].split(' (SUCCESS)')[0]
                # Verify truncation occurred (should be less than original 150)
                assert len(action_part) < 150
