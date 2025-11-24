"""
Test that ActionDeclaration accepts attunement-specific fields.

This test verifies the fix for the bug where attunement fields were
being dropped during Pydantic model → ActionDeclaration conversion.
"""
import pytest
from scripts.aeonisk.multiagent.action_schema import ActionDeclaration


def test_action_declaration_accepts_attunement_fields():
    """Test that ActionDeclaration accepts all attunement fields without error."""
    action = ActionDeclaration(
        intent="Attune Raw Seed to Drip at basic altar",
        description="I place a Raw Seed upon a modest stone altar and channel Willpower.",
        attribute="Willpower",
        skill="Attunement",
        difficulty_estimate=19,
        difficulty_justification="DC 20 base reduced to 19 by using a basic altar (-1 DC)",
        character_name="Seed Keeper Zephyr",
        agent_id="player_01",
        action_type="attune",
        # Attunement-specific fields (these were missing before fix)
        target_energy="drip",
        altar_id="alt_basic_02",
        use_echo_calibrator=False
    )

    # Verify fields are set correctly
    assert action.target_energy == "drip"
    assert action.altar_id == "alt_basic_02"
    assert action.use_echo_calibrator is False
    assert action.action_type == "attune"


def test_action_declaration_attunement_fields_optional():
    """Test that attunement fields are optional (default to None)."""
    action = ActionDeclaration(
        intent="Generic action",
        description="This is not an attunement action.",
        attribute="Strength",
        skill=None,
        difficulty_estimate=15,
        difficulty_justification="DC 15: Standard difficulty",
        character_name="Test Character",
        agent_id="test_01",
        action_type="combat"
    )

    # Attunement fields should default to None
    assert action.target_energy is None
    assert action.altar_id is None
    assert action.use_echo_calibrator is None


def test_action_declaration_to_dict_includes_attunement_fields():
    """Test that to_dict() includes attunement fields."""
    action = ActionDeclaration(
        intent="Attune Raw Seed to Spark",
        description="Using Echo-Calibrator for portable attunement.",
        attribute="Agility",
        skill="Tech",
        difficulty_estimate=16,
        difficulty_justification="DC 16: Echo-Calibrator check",
        character_name="Technician",
        agent_id="player_02",
        action_type="attune",
        target_energy="spark",
        altar_id=None,
        use_echo_calibrator=True
    )

    action_dict = action.to_dict()

    # Verify attunement fields are in dict
    assert action_dict["target_energy"] == "spark"
    assert action_dict["altar_id"] is None
    assert action_dict["use_echo_calibrator"] is True
