"""
Test NPCSpawn schema validation for disposition and entity_type fields.

This test reproduces the validation errors seen with OpenAI gpt-5-mini:
- disposition="fearful" should be valid (currently fails)
- entity_type should clearly distinguish from threat_level
"""

import pytest
from scripts.aeonisk.multiagent.schemas.story_events import NPCSpawn, ScenarioSetup, NewClock
from pydantic import ValidationError


class TestNPCSpawnDisposition:
    """Test disposition field accepts all reasonable NPC attitudes."""

    def test_fearful_disposition_should_be_valid(self):
        """Fearful NPCs are a legitimate state (civilians in danger, intimidated witnesses, etc.)."""
        npc = NPCSpawn(
            name="Frightened Civilian",
            faction="Civilian",
            entity_type="neutral",
            disposition="fearful",  # This should be valid!
            description="Wide-eyed civilian cowering behind debris",
            health=20,
            soak=0,
            skills={}
        )
        assert npc.disposition == "fearful"

    def test_existing_dispositions_still_work(self):
        """Ensure existing dispositions still validate."""
        for disp in ["friendly", "neutral", "wary", "prisoner"]:
            npc = NPCSpawn(
                name="Test NPC",
                faction="Test",
                entity_type="neutral",
                disposition=disp,
                description="A test NPC with various dispositions",
                health=30,
                soak=2,
                skills={}
            )
            assert npc.disposition == disp


class TestNPCSpawnEntityTypeVsThreatLevel:
    """Test that entity_type and threat_level are distinct and don't overlap."""

    def test_potential_threat_is_threat_level_not_entity_type(self):
        """'potential_threat' is a threat_level value, not an entity_type value."""
        # This SHOULD fail - potential_threat is threat_level, not entity_type
        with pytest.raises(ValidationError) as exc_info:
            NPCSpawn(
                name="Confused NPC",
                faction="Civilian",
                entity_type="potential_threat",  # WRONG FIELD!
                disposition="wary",
                description="NPC with confused field usage",
                health=30,
                soak=2,
                skills={}
            )

        # Check error mentions entity_type
        assert "entity_type" in str(exc_info.value)

    def test_potential_threat_valid_for_threat_level(self):
        """'potential_threat' IS valid when used in the correct field."""
        npc = NPCSpawn(
            name="Armed Civilian",
            faction="Civilian",
            entity_type="neutral",  # Correct field
            threat_level="potential_threat",  # Correct field for this value
            disposition="wary",
            description="Nervous civilian with improvised weapon",
            health=30,
            soak=2,
            skills={}
        )
        assert npc.entity_type == "neutral"
        assert npc.threat_level == "potential_threat"

    def test_entity_type_valid_values(self):
        """entity_type should only accept: neutral, ally, prisoner."""
        valid_types = ["neutral", "ally", "prisoner"]

        for entity_type in valid_types:
            npc = NPCSpawn(
                name="Test NPC",
                faction="Test",
                entity_type=entity_type,
                disposition="neutral",
                description="Test NPC for entity_type validation",
                health=30,
                soak=2,
                skills={}
            )
            assert npc.entity_type == entity_type


class TestScenarioSetupWithFearfulNPCs:
    """Test that ScenarioSetup.initial_npcs accepts fearful NPCs."""

    def test_scenario_setup_with_fearful_npc(self):
        """Reproduce the exact OpenAI error: initial_npcs.2.disposition='fearful'"""
        scenario = ScenarioSetup(
            theme="Failed ritual aftermath",
            location="Corrupted Temple",
            situation="The ritual has failed catastrophically. Void energy cascades through the temple as terrified acolytes flee for their lives.",
            void_level=8,
            starting_clocks=[
                NewClock(
                    name="Void Breach",
                    max_ticks=8,
                    description="Uncontrolled void energy expanding",
                    advance_meaning="Breach grows larger",
                    regress_meaning="Containment efforts succeed"
                )
            ],
            success_conditions="Contain the breach and evacuate survivors",
            failure_consequences="Temple collapses, void corruption spreads to city",
            initial_npcs=[
                NPCSpawn(
                    name="Head Ritualist",
                    faction="Void Cultist",
                    entity_type="neutral",
                    disposition="fearful",  # This triggered the error
                    description="Ritualist responsible for the failed ceremony, terrified of consequences",
                    health=40,
                    soak=3,
                    skills={"ritual_arts": 8}
                )
            ]
        )

        assert len(scenario.initial_npcs) == 1
        assert scenario.initial_npcs[0].disposition == "fearful"
