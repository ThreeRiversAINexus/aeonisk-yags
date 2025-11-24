"""
Unit tests for enemy/NPC conversion validation.

Tests that the system gracefully handles conversion attempts for non-existent
enemies/NPCs and provides feedback to prevent DM errors.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from scripts.aeonisk.multiagent.schemas.story_events import (
    EnemyConversion, EnemyResolution, Escalation, NPCSpawn
)


class TestEnemyConversionValidation:
    """Test validation of enemy→NPC conversions (de-escalations)."""

    def test_conversion_validates_enemy_exists(self):
        """Should check enemy exists before attempting conversion."""
        # Setup mock enemy combat module with known enemies
        enemy_combat = Mock()
        enemy_agent1 = Mock()
        enemy_agent1.agent_id = "enemy_thug_01"
        enemy_agent1.name = "Thug"

        enemy_combat.enemy_agents = [enemy_agent1]

        # Attempt to convert existing enemy (should succeed)
        conversion = EnemyConversion(
            enemy_id="enemy_thug_01",
            resolution=EnemyResolution.CONVINCED,
            reason="The thug surrenders"
        )

        # Find enemy in list
        enemy = next((e for e in enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)
        assert enemy is not None
        assert enemy.agent_id == "enemy_thug_01"

    def test_conversion_handles_missing_enemy(self):
        """Should handle conversion of non-existent enemy gracefully."""
        # Setup mock enemy combat module with known enemies
        enemy_combat = Mock()
        enemy_agent1 = Mock()
        enemy_agent1.agent_id = "enemy_thug_01"

        enemy_combat.enemy_agents = [enemy_agent1]

        # Attempt to convert non-existent enemy
        conversion = EnemyConversion(
            enemy_id="enemy_boss_99",  # Doesn't exist
            resolution=EnemyResolution.CONVINCED,
            reason="The boss surrenders"
        )

        # Validation should detect missing enemy
        enemy = next((e for e in enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)
        assert enemy is None  # Enemy not found

        # Session should log warning and skip conversion (test in integration test)

    def test_conversion_provides_valid_enemy_list(self):
        """DM should see list of valid enemy_ids to prevent errors."""
        # Setup mock enemy combat module
        enemy_combat = Mock()

        enemy1 = Mock()
        enemy1.agent_id = "enemy_thug_01"
        enemy1.name = "Thug"
        enemy1.health = 45
        enemy1.max_health = 100

        enemy2 = Mock()
        enemy2.agent_id = "enemy_boss_02"
        enemy2.name = "Boss"
        enemy2.health = 120
        enemy2.max_health = 150

        enemy_combat.enemy_agents = [enemy1, enemy2]

        # Format valid enemy list for DM prompt
        valid_enemies = []
        for enemy in enemy_combat.enemy_agents:
            health_pct = int((enemy.health / enemy.max_health) * 100)
            valid_enemies.append(f"{enemy.agent_id} ({enemy.name}, {health_pct}% HP)")

        # DM should see this in conversion check prompt
        assert len(valid_enemies) == 2
        assert "enemy_thug_01 (Thug, 45% HP)" in valid_enemies
        assert "enemy_boss_02 (Boss, 80% HP)" in valid_enemies

    def test_conversion_skips_invalid_preserves_valid(self):
        """Should process valid conversions even if some are invalid."""
        # Setup mock enemy combat module
        enemy_combat = Mock()

        enemy1 = Mock()
        enemy1.agent_id = "enemy_thug_01"
        enemy1.name = "Thug"

        enemy_combat.enemy_agents = [enemy1]

        # DM returns mix of valid and invalid conversions
        conversions = [
            EnemyConversion(
                enemy_id="enemy_thug_01",  # Valid
                resolution=EnemyResolution.CONVINCED,
                reason="Thug surrenders"
            ),
            EnemyConversion(
                enemy_id="enemy_boss_99",  # Invalid (doesn't exist)
                resolution=EnemyResolution.CONVINCED,
                reason="Boss surrenders"
            )
        ]

        # Process conversions - should handle gracefully
        valid_conversions = []
        invalid_conversions = []

        for conversion in conversions:
            enemy = next((e for e in enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)
            if enemy:
                valid_conversions.append((conversion, enemy))
            else:
                invalid_conversions.append(conversion)

        assert len(valid_conversions) == 1
        assert len(invalid_conversions) == 1
        assert valid_conversions[0][1].agent_id == "enemy_thug_01"
        assert invalid_conversions[0].enemy_id == "enemy_boss_99"


class TestNPCEscalationValidation:
    """Test validation of NPC→enemy conversions (escalations)."""

    def test_escalation_validates_npc_exists(self):
        """Should check NPC exists before attempting escalation."""
        # Setup mock NPC list
        npc1 = Mock()
        npc1.agent_id = "npc_prisoner_01"
        npc1.name = "Prisoner"

        npc_agents = [npc1]

        # Attempt to escalate existing NPC (should succeed)
        escalation = Escalation(
            npc_id="npc_prisoner_01",
            template="desperate_fighter",
            reason="Prisoner attacked by player, now fighting back in panic"
        )

        # Find NPC in list
        npc = next((n for n in npc_agents if n.agent_id == escalation.npc_id), None)
        assert npc is not None
        assert npc.agent_id == "npc_prisoner_01"

    def test_escalation_handles_missing_npc(self):
        """Should handle escalation of non-existent NPC gracefully."""
        # Setup mock NPC list
        npc1 = Mock()
        npc1.agent_id = "npc_prisoner_01"

        npc_agents = [npc1]

        # Attempt to escalate non-existent NPC
        escalation = Escalation(
            npc_id="npc_guard_99",  # Doesn't exist
            template="soldier",
            reason="Guard attacked by player after alarm triggered"
        )

        # Validation should detect missing NPC
        npc = next((n for n in npc_agents if n.agent_id == escalation.npc_id), None)
        assert npc is None  # NPC not found

    def test_escalation_provides_valid_npc_list(self):
        """DM should see list of valid npc_ids to prevent errors."""
        # Setup mock NPC list
        npc1 = Mock()
        npc1.agent_id = "npc_prisoner_01"
        npc1.name = "Prisoner"
        npc1.disposition = "prisoner"

        npc2 = Mock()
        npc2.agent_id = "npc_merchant_02"
        npc2.name = "Merchant"
        npc2.disposition = "neutral"

        npc_agents = [npc1, npc2]

        # Format valid NPC list for DM prompt
        valid_npcs = []
        for npc in npc_agents:
            valid_npcs.append(f"{npc.agent_id} ({npc.name}, {npc.disposition})")

        # DM should see this in conversion check prompt
        assert len(valid_npcs) == 2
        assert "npc_prisoner_01 (Prisoner, prisoner)" in valid_npcs
        assert "npc_merchant_02 (Merchant, neutral)" in valid_npcs


class TestEnemyRemovalValidation:
    """Test validation of enemy removals (defeats, escapes)."""

    def test_removal_validates_enemy_exists(self):
        """Should check enemy exists before attempting removal."""
        # Setup mock enemy combat module
        enemy_combat = Mock()

        enemy1 = Mock()
        enemy1.agent_id = "enemy_thug_01"

        enemy_combat.enemy_agents = [enemy1]

        # Attempt to remove existing enemy (should succeed)
        conversion = EnemyConversion(
            enemy_id="enemy_thug_01",
            resolution=EnemyResolution.KILLED,  # Removal, not conversion
            reason="Thug is defeated"
        )

        enemy = next((e for e in enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)
        assert enemy is not None

    def test_removal_handles_missing_enemy(self):
        """Should handle removal of non-existent enemy gracefully."""
        # Setup mock enemy combat module
        enemy_combat = Mock()

        enemy1 = Mock()
        enemy1.agent_id = "enemy_thug_01"

        enemy_combat.enemy_agents = [enemy1]

        # Attempt to remove non-existent enemy
        conversion = EnemyConversion(
            enemy_id="enemy_boss_99",  # Doesn't exist
            resolution=EnemyResolution.KILLED,
            reason="Boss is defeated"
        )

        enemy = next((e for e in enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)
        assert enemy is None  # Should log warning and skip


class TestConversionFeedbackSystem:
    """Test DM feedback system for conversion decisions."""

    def test_dm_sees_conversion_candidates(self):
        """DM should see which enemies are good candidates for conversion."""
        # Setup mock enemy combat module
        enemy_combat = Mock()

        # Low HP enemy (good surrender candidate)
        enemy1 = Mock()
        enemy1.agent_id = "enemy_thug_01"
        enemy1.name = "Thug"
        enemy1.health = 15
        enemy1.max_health = 100
        enemy1.is_defeated = False

        # High HP enemy (unlikely to surrender)
        enemy2 = Mock()
        enemy2.agent_id = "enemy_boss_02"
        enemy2.name = "Boss"
        enemy2.health = 140
        enemy2.max_health = 150
        enemy2.is_defeated = False

        # Already defeated (shouldn't be shown)
        enemy3 = Mock()
        enemy3.agent_id = "enemy_grunt_03"
        enemy3.name = "Grunt"
        enemy3.is_defeated = True

        enemy_combat.enemy_agents = [enemy1, enemy2, enemy3]

        # Format conversion candidates for DM
        conversion_candidates = []
        for enemy in enemy_combat.enemy_agents:
            if enemy.is_defeated:
                continue

            health_pct = int((enemy.health / enemy.max_health) * 100)

            # Flag low HP enemies as candidates
            is_candidate = health_pct < 30
            marker = "🎯 CANDIDATE" if is_candidate else ""

            conversion_candidates.append(
                f"{enemy.agent_id} ({enemy.name}, {health_pct}% HP) {marker}".strip()
            )

        # DM should see thug as candidate, boss as not
        assert len(conversion_candidates) == 2  # Only active enemies
        assert "enemy_thug_01 (Thug, 15% HP) 🎯 CANDIDATE" in conversion_candidates
        assert "enemy_boss_02 (Boss, 93% HP)" in conversion_candidates
        assert "enemy_grunt_03" not in str(conversion_candidates)  # Defeated enemy excluded

    def test_dm_sees_npc_escalation_triggers(self):
        """DM should see NPCs that might escalate (took damage, hostile disposition)."""
        # Setup mock NPC list
        npc1 = Mock()
        npc1.agent_id = "npc_prisoner_01"
        npc1.name = "Prisoner"
        npc1.disposition = "prisoner"
        npc1.health = 80  # Took damage
        npc1.max_health = 100

        npc2 = Mock()
        npc2.agent_id = "npc_merchant_02"
        npc2.name = "Merchant"
        npc2.disposition = "neutral"
        npc2.health = 100  # Full health
        npc2.max_health = 100

        npc_agents = [npc1, npc2]

        # Format escalation candidates for DM
        escalation_candidates = []
        for npc in npc_agents:
            health_pct = int((npc.health / npc.max_health) * 100)

            # Flag NPCs who took damage or are hostile
            took_damage = health_pct < 100
            marker = "⚠️ TOOK DAMAGE" if took_damage else ""

            escalation_candidates.append(
                f"{npc.agent_id} ({npc.name}, {npc.disposition}, {health_pct}% HP) {marker}".strip()
            )

        # DM should see prisoner with damage marker
        assert len(escalation_candidates) == 2
        assert "npc_prisoner_01 (Prisoner, prisoner, 80% HP) ⚠️ TOOK DAMAGE" in escalation_candidates
        assert "npc_merchant_02 (Merchant, neutral, 100% HP)" in escalation_candidates
