"""
Regression tests to ensure Charisma is fully removed and Dexterity is added.

These tests enforce YAGS + Aeonisk attribute conformance:
- 8 attributes total: Strength, Agility, Endurance, Dexterity, Perception, Intelligence, Empathy, Willpower
- NO "Charisma" (non-YAGS attribute that crept into codebase)
- Skills correctly mapped to attributes per YAGS standard
"""

import inspect
import pathlib


def test_attributes_list_has_8_items():
    """ATTRIBUTES constant must have exactly 8 items."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
    assert len(MechanicsEngine.ATTRIBUTES) == 8, \
        f"Expected 8 attributes, got {len(MechanicsEngine.ATTRIBUTES)}: {MechanicsEngine.ATTRIBUTES}"


def test_attributes_list_includes_dexterity():
    """ATTRIBUTES must include Dexterity."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
    assert "Dexterity" in MechanicsEngine.ATTRIBUTES, \
        f"Dexterity missing from ATTRIBUTES: {MechanicsEngine.ATTRIBUTES}"


def test_attributes_list_excludes_charisma():
    """ATTRIBUTES must NOT include Charisma."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
    assert "Charisma" not in MechanicsEngine.ATTRIBUTES, \
        f"Charisma found in ATTRIBUTES (should be removed): {MechanicsEngine.ATTRIBUTES}"


def test_attributes_list_correct_order():
    """ATTRIBUTES should match YAGS + Aeonisk standard."""
    from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
    expected = [
        "Strength", "Agility", "Endurance", "Dexterity",
        "Perception", "Intelligence", "Empathy", "Willpower"
    ]
    assert MechanicsEngine.ATTRIBUTES == expected, \
        f"ATTRIBUTES mismatch.\nExpected: {expected}\nGot: {MechanicsEngine.ATTRIBUTES}"


def test_no_charisma_in_action_router():
    """action_router.py must not map any skill to Charisma."""
    from scripts.aeonisk.multiagent.action_router import ActionRouter
    source = inspect.getsource(ActionRouter)
    assert "Charisma" not in source, \
        "Found 'Charisma' in ActionRouter source - all skills must map to valid YAGS attributes"


def test_guile_maps_to_empathy():
    """Guile skill must map to Empathy (not Charisma)."""
    from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE
    assert SKILL_DATABASE["Guile"].attribute == "Empathy", \
        f"Guile should map to Empathy, got {SKILL_DATABASE['Guile'].attribute}"


def test_sleight_maps_to_dexterity():
    """Sleight skill must map to Dexterity."""
    from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE
    assert SKILL_DATABASE["Sleight"].attribute == "Dexterity", \
        f"Sleight should map to Dexterity, got {SKILL_DATABASE['Sleight'].attribute}"


def test_throw_maps_to_dexterity():
    """Throw skill must map to Dexterity."""
    from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE
    assert SKILL_DATABASE["Throw"].attribute == "Dexterity", \
        f"Throw should map to Dexterity, got {SKILL_DATABASE['Throw'].attribute}"


def test_player_valid_attributes_excludes_charisma():
    """VALID_ATTRIBUTES in player.py must not include charisma."""
    player_py = pathlib.Path("scripts/aeonisk/multiagent/player.py").read_text()
    assert "'charisma': 'Charisma'" not in player_py, \
        "Found 'charisma': 'Charisma' in player.py VALID_ATTRIBUTES (should be removed)"


def test_player_valid_attributes_includes_dexterity():
    """VALID_ATTRIBUTES in player.py must include dexterity."""
    player_py = pathlib.Path("scripts/aeonisk/multiagent/player.py").read_text()
    assert "'dexterity': 'Dexterity'" in player_py, \
        "Missing 'dexterity': 'Dexterity' in player.py VALID_ATTRIBUTES"


def test_schema_whitelist_excludes_charisma():
    """Schema validation in player_action.py must not whitelist Charisma."""
    schema_py = pathlib.Path("scripts/aeonisk/multiagent/schemas/player_action.py").read_text()

    # Check that if valid_attributes exists, it doesn't contain "Charisma"
    if 'valid_attributes' in schema_py:
        assert '"Charisma"' not in schema_py, \
            "Found 'Charisma' in player_action.py valid_attributes whitelist (should be removed)"


def test_schema_whitelist_includes_dexterity():
    """Schema validation in player_action.py must whitelist Dexterity."""
    schema_py = pathlib.Path("scripts/aeonisk/multiagent/schemas/player_action.py").read_text()

    if 'valid_attributes' in schema_py:
        assert '"Dexterity"' in schema_py, \
            "Missing 'Dexterity' in player_action.py valid_attributes whitelist"


def test_skill_mapping_excludes_charisma():
    """skill_mapping.py must not validate Charisma as a social attribute."""
    skill_mapping_py = pathlib.Path("scripts/aeonisk/multiagent/skill_mapping.py").read_text()

    # Check for the social attribute validation list
    assert "'Charisma'" not in skill_mapping_py or "['Empathy', 'Charisma']" not in skill_mapping_py, \
        "Found Charisma in skill_mapping.py social attribute validation (should only allow Empathy)"
