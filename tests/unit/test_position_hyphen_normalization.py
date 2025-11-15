"""
Test Position enum handling of Unicode hyphen variants.

OpenAI models sometimes generate non-breaking hyphens (U+2011 ‑) instead of
regular ASCII hyphens (U+002D -), causing validation errors.

This test ensures Position enum normalizes hyphen variants.
"""

import pytest
from scripts.aeonisk.multiagent.schemas.shared_types import Position
from scripts.aeonisk.multiagent.schemas.story_events import EnemySpawn


class TestPositionHyphenNormalization:
    """Test Position enum accepts and normalizes hyphen variants."""

    def test_regular_hyphen_accepted(self):
        """Regular ASCII hyphen should work (baseline)."""
        pos = Position("Near-PC")
        assert pos == Position.NEAR_PC

    def test_non_breaking_hyphen_normalized(self):
        """Non-breaking hyphen (U+2011) should be normalized to regular hyphen."""
        # This is what OpenAI generates: Near‑PC (with U+2011 non-breaking hyphen)
        pos_input = "Near‑PC"  # ← Non-breaking hyphen (U+2011)
        pos = Position(pos_input)
        assert pos == Position.NEAR_PC

    def test_all_positions_with_non_breaking_hyphen(self):
        """All Position values should accept non-breaking hyphens."""
        test_cases = [
            ("Near‑PC", Position.NEAR_PC),
            ("Near‑Enemy", Position.NEAR_ENEMY),
            ("Far‑PC", Position.FAR_PC),
            ("Far‑Enemy", Position.FAR_ENEMY),
            ("Extreme‑PC", Position.EXTREME_PC),
            ("Extreme‑Enemy", Position.EXTREME_ENEMY),
        ]

        for input_val, expected in test_cases:
            pos = Position(input_val)
            assert pos == expected

    def test_enemy_spawn_with_non_breaking_hyphen(self):
        """EnemySpawn should accept position with non-breaking hyphen."""
        spawn = EnemySpawn(
            template="grunt",
            faction="Test",
            archetype="Guard",
            spawn_reason="Testing hyphen normalization",
            initial_position="Near‑PC"  # ← Non-breaking hyphen
        )
        assert spawn.initial_position == Position.NEAR_PC
