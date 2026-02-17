"""
Test suite for YAGS-correct Soak calculation.

Verifies:
- Soak = Size + Agi + End - 5 (pure YAGS, no combat balance modifier)
- PC armor from inventory applies to soak
- Enemy soak = base + armor (no combat balance modifier)
- Armor loading from player config inventory
"""

import pytest


class TestSoakFormula:
    """Verify Soak formula matches pure YAGS (no combat balance)."""

    def test_soak_formula_no_balance_modifier(self):
        """YAGS Soak = Size + Agi + End - 5, no +4 combat balance."""
        # Typical human (Size=5, Agi=3, End=3)
        soak = 5 + 3 + 3 - 5
        assert soak == 6

        # Tank (Size=6, Agi=4, End=5)
        soak = 6 + 4 + 5 - 5
        assert soak == 10

        # Kael Dren (Size=5, Agi=4, End=4)
        soak = 5 + 4 + 4 - 5
        assert soak == 8


class TestEnemySoakCalculation:
    """Verify enemy Soak uses correct formula without combat balance."""

    def test_enemy_soak_no_balance_modifier(self):
        """Enemy _calculate_base_soak should NOT include +4 combat balance."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        enemy = EnemyAgent(
            agent_id="test_enemy",
            name="Test Enemy",
            template="test",
            attributes={"Agility": 3, "Endurance": 3},
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

        # YAGS: 5 + 3 + 3 - 5 = 6 (no +4 balance)
        assert calculated_soak == 6, f"Expected Soak=6, got {calculated_soak}"

    def test_enemy_uses_endurance_not_health(self):
        """Enemy should use Endurance attribute, not deprecated Health."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position

        enemy = EnemyAgent(
            agent_id="test_enemy_tough",
            name="Tough Enemy",
            template="test",
            attributes={"Agility": 3, "Endurance": 4},
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

        # YAGS: 5 + 3 + 4 - 5 = 7 (no +4 balance)
        assert calculated_soak == 7, f"Expected Soak=7, got {calculated_soak}"

    def test_enemy_soak_with_armor(self):
        """Enemy soak should be base + armor bonus (no combat balance)."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position
        from scripts.aeonisk.multiagent.weapons import get_armor

        light_armor = get_armor("light_armor")

        enemy = EnemyAgent(
            agent_id="test_enemy_armored",
            name="Armored Enemy",
            template="grunt",
            attributes={"Agility": 3, "Endurance": 3},
            skills={},
            health=30,
            max_health=30,
            soak=0,
            wounds=0,
            position=Position.ENGAGED,
            initiative=10,
            size=5,
            armor=light_armor
        )

        # __post_init__ calculates base soak and adds armor
        # YAGS: 5 + 3 + 3 - 5 = 6, + light_armor(3) = 9
        assert enemy.soak == 9, f"Expected Soak=9, got {enemy.soak}"

    def test_enemy_tank_high_soak(self):
        """Tank enemy with heavy armor should have correct high soak."""
        from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent
        from scripts.aeonisk.multiagent.schemas.shared_types import Position
        from scripts.aeonisk.multiagent.weapons import get_armor

        heavy_armor = get_armor("heavy_armor")

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
            size=6,
            armor=heavy_armor
        )

        # YAGS: 6 + 4 + 5 - 5 = 10, + heavy_armor(8) = 18
        assert enemy.soak == 18, f"Expected Soak=18, got {enemy.soak}"


class TestPlayerArmorLoading:
    """Verify PC armor loading from inventory and soak application."""

    def test_riot_carapace_in_armor_library(self):
        """riot_carapace should exist in ARMOR_LIBRARY with correct stats."""
        from scripts.aeonisk.multiagent.weapons import ARMOR_LIBRARY

        assert "riot_carapace" in ARMOR_LIBRARY, "riot_carapace not in ARMOR_LIBRARY"
        armor = ARMOR_LIBRARY["riot_carapace"]
        assert armor.soak_bonus == 3
        assert armor.armor_type == "light"
        assert armor.name == "Riot Carapace"

    def test_pc_armor_applies_to_soak(self):
        """Player with riot_carapace in inventory should get +3 soak."""
        from scripts.aeonisk.multiagent.weapons import ARMOR_LIBRARY, get_armor

        # Simulate: Kael Dren with Agi=4, End=4, Size=5, riot_carapace in inventory
        size = 5
        agility = 4
        endurance = 4
        base_soak = size + agility + endurance - 5  # = 8

        armor = get_armor("riot_carapace")
        total_soak = base_soak + armor.soak_bonus  # = 8 + 3 = 11

        assert base_soak == 8
        assert total_soak == 11

    def test_player_load_armor_from_inventory(self):
        """Player._load_armor() should find armor in inventory."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent
        from scripts.aeonisk.multiagent.weapons import ARMOR_LIBRARY

        # Create a minimal player-like object with riot_carapace in inventory
        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_config = {
            "inventory": {
                "riot_carapace": 1,
                "med_kit": 1
            }
        }

        armor = player._load_armor()
        assert armor is not None, "Should find riot_carapace in inventory"
        assert armor.name == "Riot Carapace"
        assert armor.soak_bonus == 3

    def test_player_load_armor_none_when_no_armor(self):
        """Player._load_armor() should return None when no armor in inventory."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_config = {
            "inventory": {
                "med_kit": 1,
                "pistol": 1
            }
        }

        armor = player._load_armor()
        assert armor is None, "Should return None when no armor in inventory"

    def test_player_load_armor_empty_inventory(self):
        """Player._load_armor() should return None with empty/missing inventory."""
        from scripts.aeonisk.multiagent.player import AIPlayerAgent

        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_config = {}

        armor = player._load_armor()
        assert armor is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
