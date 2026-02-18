"""
Tests for faction context in enemy prompts.

Phase 2A: Add FACTION_DESCRIPTIONS and _format_faction_context to enemy_prompts.
"""

import pytest
from unittest.mock import MagicMock

from scripts.aeonisk.multiagent.faction_utils import (
    get_faction_description,
    NEXUS_ALIGNED_CORPORATE,
    CANONICAL_SPAWN_FACTIONS,
    are_factions_allied,
)
from scripts.aeonisk.multiagent.enemy_agent import EnemyAgent, Position
from scripts.aeonisk.multiagent.enemy_prompts import (
    generate_tactical_prompt_structured,
)


class TestFactionDescriptions:
    """get_faction_description() returns useful descriptions."""

    def test_get_faction_description_acg_uses_full_name(self):
        desc = get_faction_description("ACG")
        assert "Astral Commerce Group" in desc

    def test_get_faction_description_tempest(self):
        desc = get_faction_description("Tempest Industries")
        assert "Void research" in desc or "Anti-Nexus" in desc

    def test_get_faction_description_void(self):
        desc = get_faction_description("Void")
        assert "Void" in desc

    def test_get_faction_description_freeborn(self):
        desc = get_faction_description("Freeborn")
        assert "Natural-born" in desc or "pod system" in desc

    def test_get_faction_description_aether_dynamics(self):
        desc = get_faction_description("Aether Dynamics")
        assert len(desc) > 10

    def test_get_faction_description_unknown_returns_generic(self):
        desc = get_faction_description("SomeUnknownFaction")
        assert len(desc) > 0  # Should return a generic description

    def test_aether_dynamics_is_nexus_aligned_corporate(self):
        assert "Aether Dynamics" in NEXUS_ALIGNED_CORPORATE

    def test_aether_dynamics_in_canonical_spawn_factions(self):
        assert "Aether Dynamics" in CANONICAL_SPAWN_FACTIONS

    def test_aether_dynamics_allied_with_nexus(self):
        assert are_factions_allied("Aether Dynamics", "Sovereign Nexus")


class TestNeutralFactionAlliance:
    """Neutral factions (Freeborn, Independent) should NOT be blanket-allied with everyone.

    Bug: are_factions_allied() returned True for Neutral+Others, which prevented
    escalated Freeborn enemies from attacking any non-Void target.
    """

    def test_neutral_vs_neutral_allied(self):
        """Freeborn + Freeborn = allied (same alignment, don't fight each other)."""
        assert are_factions_allied("Freeborn", "Freeborn") is True
        assert are_factions_allied("Freeborn", "Independent") is True

    def test_neutral_vs_anti_nexus_not_allied(self):
        """Freeborn + Tempest = NOT allied (independent factions, can be hostile)."""
        assert are_factions_allied("Freeborn", "Tempest Industries") is False
        assert are_factions_allied("Freeborn", "Tempest") is False

    def test_neutral_vs_pro_nexus_not_allied(self):
        """Freeborn + Sovereign Nexus = NOT allied."""
        assert are_factions_allied("Freeborn", "Sovereign Nexus") is False
        assert are_factions_allied("Independent", "Pantheon Security") is False

    def test_neutral_vs_corporate_not_allied(self):
        """Freeborn + ACG = NOT allied."""
        assert are_factions_allied("Freeborn", "ACG") is False
        assert are_factions_allied("Independent", "Aether Dynamics") is False

    def test_neutral_vs_void_not_allied(self):
        """Freeborn + Void = NOT allied (Void hostile to all)."""
        assert are_factions_allied("Freeborn", "Void") is False

    def test_existing_alliances_unchanged(self):
        """Verify the fix doesn't break existing alliance logic."""
        # Pro-Nexus alliances
        assert are_factions_allied("Sovereign Nexus", "Pantheon Security") is True
        # Corporate alliances
        assert are_factions_allied("ACG", "Aether Dynamics") is True
        # Pro-Nexus + Corporate
        assert are_factions_allied("Sovereign Nexus", "ACG") is True
        # Anti-Nexus vs Pro-Nexus
        assert are_factions_allied("Tempest Industries", "Sovereign Nexus") is False
        # Same faction
        assert are_factions_allied("Tempest", "Tempest") is True


class TestFactionContextInPrompt:
    """Tactical prompt includes faction context."""

    def test_tactical_prompt_includes_faction_context(self):
        enemy = EnemyAgent(
            agent_id="enemy_test_01",
            name="ACG Enforcer",
            template="enforcer",
            attributes={"Agility": 3, "Strength": 5, "Perception": 3, "Intelligence": 2, "Empathy": 2, "Willpower": 4, "Health": 4},
            skills={"Brawl": 4, "Melee": 4},
            health=55,
            max_health=55,
            soak=8,
            wounds=0,
            position=Position(ring="Near", side="Enemy"),
            initiative=12,
            faction="ACG",
            morale_behavior="surrender_if_cornered",
            character_brief="Methodical enforcer.",
        )
        prompt = generate_tactical_prompt_structured(
            enemy=enemy,
            player_agents=[],
            enemy_agents=[enemy],
            shared_intel=MagicMock(get_recent_intel=MagicMock(return_value=[])),
            available_tokens=[],
            current_round=1,
        )
        assert "FACTION" in prompt
        assert "Astral Commerce Group" in prompt or "ACG" in prompt
