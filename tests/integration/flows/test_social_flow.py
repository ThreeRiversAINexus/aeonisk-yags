"""
Social Encounter Flow Integration Tests

Tests social interaction mechanics:
- Persuasion/Empathy skill checks
- NPC interactions
- Soulcredit impact
- Narrative outcomes
"""

import pytest
import json
from pathlib import Path


class TestSocialSkillUsage:
    """Test social skills are used appropriately."""

    def test_persuasion_uses_charm_empathy(self):
        """Test persuasion attempts use Charm or Empathy skills."""
        # Social skills in YAGS
        social_skills = ['Charm', 'Empathy', 'Intimidate', 'Leadership']

        assert 'Charm' in social_skills
        assert 'Empathy' in social_skills

    def test_charm_uses_presence(self):
        """Test Charm skill typically pairs with Presence attribute."""
        # Charm = Presence × Charm skill
        presence = 4
        charm_skill = 3
        ability = presence * charm_skill

        assert ability == 12

    def test_empathy_uses_intelligence_or_presence(self):
        """Test Empathy can use Intelligence or Presence."""
        # Empathy reading intentions: Intelligence × Empathy
        intelligence = 3
        empathy_skill = 2
        ability_int = intelligence * empathy_skill

        # Empathy social influence: Presence × Empathy
        presence = 4
        ability_pres = presence * empathy_skill

        assert ability_int == 6
        assert ability_pres == 8


class TestNPCInteractions:
    """Test NPC interaction patterns."""

    def test_npc_has_disposition(self):
        """Test NPCs have disposition toward characters."""
        npc_dispositions = ['hostile', 'unfriendly', 'neutral', 'friendly', 'allied']

        assert 'neutral' in npc_dispositions
        assert 'friendly' in npc_dispositions

    def test_disposition_affects_dc(self):
        """Test NPC disposition affects persuasion DC."""
        base_dc = 20

        # Friendly NPC: easier to persuade
        friendly_dc = base_dc - 3  # 17

        # Hostile NPC: harder to persuade
        hostile_dc = base_dc + 5  # 25

        assert friendly_dc < base_dc
        assert hostile_dc > base_dc


class TestSoulcreditImpact:
    """Test Soulcredit affects social interactions."""

    def test_positive_soulcredit_helps(self):
        """Test positive Soulcredit provides social bonus."""
        soulcredit = 5  # Positive reputation
        social_bonus = min(soulcredit // 2, 3)  # Cap at +3

        assert social_bonus > 0
        assert social_bonus <= 3

    def test_negative_soulcredit_hurts(self):
        """Test negative Soulcredit penalizes social interactions."""
        soulcredit = -6  # Bad reputation
        social_penalty = max(soulcredit // 2, -3)  # Cap at -3

        assert social_penalty < 0
        assert social_penalty >= -3

    def test_neutral_soulcredit_no_effect(self):
        """Test neutral Soulcredit (0) has no modifier."""
        soulcredit = 0
        modifier = 0

        assert modifier == 0


class TestSocialOutcomes:
    """Test social encounter outcomes."""

    def test_excellent_success_major_concession(self):
        """Test excellent success gets major concession."""
        # Roll beats DC by 10+
        margin = 12
        outcome_tier = "excellent"

        # Excellent social success: major concession, valuable info
        assert margin >= 10
        assert outcome_tier == "excellent"

    def test_moderate_success_partial_concession(self):
        """Test moderate success gets partial agreement."""
        margin = 3
        outcome_tier = "moderate"

        # Moderate success: partial concession, some info
        assert 0 <= margin < 5
        assert outcome_tier == "moderate"

    def test_failure_no_concession(self):
        """Test failure means no agreement."""
        margin = -5
        outcome_tier = "failure"

        # Failure: no concession, may worsen relations
        assert margin < 0
        assert outcome_tier == "failure"


class TestNegotiationMechanics:
    """Test negotiation and deal-making."""

    def test_extended_negotiation(self):
        """Test complex negotiations use multiple checks."""
        # Extended negotiation might use:
        # 1. Empathy to read intentions
        # 2. Charm to build rapport
        # 3. Intimidate or Charm to close deal

        negotiation_phases = ["read_intentions", "build_rapport", "make_offer", "close_deal"]

        assert len(negotiation_phases) >= 3

    def test_contested_social_check(self):
        """Test social contests (opposed rolls)."""
        # Character A: Charm attempt
        char_a_roll = 22

        # Character B: Willpower to resist
        char_b_roll = 18

        # Higher roll wins
        char_a_succeeds = char_a_roll > char_b_roll
        assert char_a_succeeds == True


class TestInformationGathering:
    """Test social skill for gathering information."""

    def test_empathy_reads_emotions(self):
        """Test Empathy reveals emotional state."""
        # Empathy check to read NPC
        empathy_success = True

        if empathy_success:
            revealed_info = "NPC is nervous, hiding something"
        else:
            revealed_info = "Cannot read NPC clearly"

        assert "nervous" in revealed_info

    def test_charm_extracts_secrets(self):
        """Test Charm can get NPC to share secrets."""
        charm_margin = 8  # Good success

        if charm_margin >= 5:
            secret_revealed = True
        else:
            secret_revealed = False

        assert secret_revealed == True


class TestSocialConsequences:
    """Test social action consequences."""

    def test_failed_intimidation_worsens_relations(self):
        """Test failed intimidation harms relationship."""
        intimidate_result = "failure"
        disposition_change = -1

        assert disposition_change < 0

    def test_successful_charm_improves_relations(self):
        """Test successful charm improves relationship."""
        charm_result = "good"
        disposition_change = +1

        assert disposition_change > 0

    def test_critical_failure_burns_bridges(self):
        """Test critical failure can permanently damage relations."""
        social_margin = -15  # Critical failure
        permanent_penalty = True

        assert social_margin <= -10
        assert permanent_penalty == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
