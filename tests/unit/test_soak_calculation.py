"""
Test suite for Soak calculation fix.

Written FIRST (TDD red phase) - tests FAIL initially.

This test suite verifies:
- Soak calculated from attributes (Size + Agi + End - 5 + balance)
- Not hardcoded to 10
- Enemy uses Endurance not deprecated "Health"
- Soak range is 6-15 (not all 10)

See Track C in the implementation plan for details.
"""

import pytest


class TestSoakFormula:
    """Verify Soak formula matches YAGS + combat balance"""

    def test_soak_formula_basic(self):
        """Test the YAGS Soak formula itself"""
        SOAK_COMBAT_BALANCE = 4

        # Typical human (Size=5, Agi=3, End=3)
        soak = 5 + 3 + 3 - 5 + SOAK_COMBAT_BALANCE
        assert soak == 10

        # Tank (Size=6, Agi=4, End=5)
        soak = 6 + 4 + 5 - 5 + SOAK_COMBAT_BALANCE
        assert soak == 14

        # Agile (Size=4, Agi=2, End=2)
        soak = 4 + 2 + 2 - 5 + SOAK_COMBAT_BALANCE
        assert soak == 7

        # Weak (Size=3, Agi=2, End=2)
        soak = 3 + 2 + 2 - 5 + SOAK_COMBAT_BALANCE
        assert soak == 6

        # Very tough (Size=6, Agi=5, End=5)
        soak = 6 + 5 + 5 - 5 + SOAK_COMBAT_BALANCE
        assert soak == 15


class TestEnemySoakCalculation:
    """Verify enemy Soak uses correct formula"""

    def test_enemy_soak_method(self):
        """Test enemy _calculate_base_soak method directly"""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        # Create minimal enemy for testing
        enemy = EnemyAgent(
            agent_id="test_enemy",
            name="Test Enemy",
            template="test",
            attributes={"Agility": 3, "Endurance": 3},
            skills={},
            health=30,
            max_health=30,
            soak=0,  # Will be calculated
            wounds=0,
            position=Position.ENGAGED,
            initiative=10,
            size=5
        )

        # Calculate Soak
        calculated_soak = enemy._calculate_base_soak()

        # Expected: 5 + 3 + 3 - 5 + 4 = 10
        assert calculated_soak == 10, f"Expected Soak=10, got {calculated_soak}"

    def test_enemy_uses_endurance_not_health(self):
        """Enemy should use Endurance attribute, not deprecated Health"""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        # Create enemy with higher Endurance
        enemy = EnemyAgent(
            agent_id="test_enemy_tough",
            name="Tough Enemy",
            template="test",
            attributes={"Agility": 3, "Endurance": 4},  # NOT "Health"!
            skills={},
            health=30,
            max_health=30,
            soak=0,
            wounds=0,
            position=Position.ENGAGED,
            initiative=10,
            size=5
        )

        calculated_soak = enemy._calculate_base_soak()

        # Expected: 5 + 3 + 4 - 5 + 4 = 11
        assert calculated_soak == 11, f"Expected Soak=11, got {calculated_soak}"

    def test_enemy_tank_high_soak(self):
        """Tank enemy should have higher Soak"""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        enemy = EnemyAgent(
            agent_id="test_enemy_tank",
            name="Tank Enemy",
            template="elite",
            attributes={"Agility": 4, "Endurance": 5},
            skills={},
            health=40,
            max_health=40,
            soak=0,
            wounds=0,
            position=Position.ENGAGED,
            initiative=10,
            size=6
        )

        calculated_soak = enemy._calculate_base_soak()

        # Expected: 6 + 4 + 5 - 5 + 4 = 14
        assert calculated_soak == 14, f"Expected Soak=14, got {calculated_soak}"


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
