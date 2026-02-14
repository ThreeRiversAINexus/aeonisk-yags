"""
Tests for NPC self-escalation behavior — Gap 5 fix.

Phase 1F: Allied NPC attacking enemies should NOT escalate to enemy.
"""

import pytest


class TestAlliedNPCEscalation:
    """Only hostile-intent NPC attacks should escalate."""

    def test_allied_npc_should_not_escalate(self):
        """Allied NPC attacking an enemy is fighting FOR players — don't escalate."""
        from scripts.aeonisk.multiagent.session import _should_escalate_npc
        assert _should_escalate_npc("ally", "attack") is False

    def test_neutral_npc_attack_escalates(self):
        """Neutral NPC attacking = joining the fight, escalate."""
        from scripts.aeonisk.multiagent.session import _should_escalate_npc
        assert _should_escalate_npc("neutral", "attack") is True

    def test_prisoner_npc_attack_escalates(self):
        """Prisoner attacking = rebellion, escalate."""
        from scripts.aeonisk.multiagent.session import _should_escalate_npc
        assert _should_escalate_npc("prisoner", "attack") is True

    def test_non_attack_never_escalates(self):
        """Non-attack actions never escalate regardless of entity_type."""
        from scripts.aeonisk.multiagent.session import _should_escalate_npc
        for action in ["dialogue", "flee", "hide", "pass", "comply"]:
            assert _should_escalate_npc("neutral", action) is False
            assert _should_escalate_npc("ally", action) is False
            assert _should_escalate_npc("prisoner", action) is False
