"""
Test suite for YAGS skill system enhancements.

Written FIRST (TDD red phase) - all tests FAIL initially.

This test suite verifies:
- Strength-based skills exist (critical gap fix)
- Endurance-based skills exist (critical gap fix)
- Top 10 undefined skills are resolved
- Skill aliases work correctly
- Database completeness and balance
- Action routing updated for new skills

See Track A in the implementation plan for details.
"""

import pytest
from collections import Counter


class TestStrengthSkills:
    """Verify Strength-based skills exist (critical gap fix)"""

    def test_climbing_skill_exists(self):
        """Climbing should exist as a Strength skill"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Climbing")
        assert skill is not None, "Climbing skill not found in SKILL_DATABASE"
        assert skill.attribute == "Strength", f"Climbing should use Strength, got {skill.attribute}"
        assert skill.category == "Movement", f"Climbing should be Movement category"

    def test_swimming_skill_exists(self):
        """Swimming should exist as a Strength skill"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Swimming")
        assert skill is not None, "Swimming skill not found"
        assert skill.attribute == "Strength"

    def test_lifting_skill_exists(self):
        """Lifting should exist as a Strength skill"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Lifting")
        assert skill is not None, "Lifting skill not found"
        assert skill.attribute == "Strength"
        assert skill.category == "Physical"


class TestEnduranceSkills:
    """Verify Endurance-based skills exist (critical gap fix)"""

    def test_resistance_skill_exists(self):
        """Resistance should exist as an Endurance skill"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Resistance")
        assert skill is not None, "Resistance skill not found"
        assert skill.attribute == "Endurance"
        assert skill.category == "Survival"

    def test_stamina_skill_exists(self):
        """Stamina should exist as an Endurance skill"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Stamina")
        assert skill is not None, "Stamina skill not found"
        assert skill.attribute == "Endurance"

    def test_running_skill_exists(self):
        """Running should exist as an Endurance skill"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Running")
        assert skill is not None, "Running skill not found"
        assert skill.attribute == "Endurance"
        assert skill.category == "Movement"


class TestUndefinedSkillsResolved:
    """Verify top 10 undefined skills now exist or alias correctly"""

    def test_insight_skill_exists(self):
        """Insight should exist (27 configs use it)"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Insight")
        assert skill is not None, "Insight skill not found (used by 27 configs!)"
        assert skill.attribute == "Empathy", "Insight should use Empathy (emotional reading)"

    def test_void_lore_skill_exists(self):
        """Void Lore should exist (17 configs use it - Aeonisk-specific)"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Void Lore")
        assert skill is not None, "Void Lore skill not found"
        assert skill.attribute == "Intelligence"
        assert skill.category == "Knowledge"

    def test_hacking_skill_exists(self):
        """Hacking should exist (8 configs use it, distinct from Systems)"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Hacking")
        assert skill is not None, "Hacking skill not found"
        assert skill.attribute == "Intelligence"
        assert skill.category == "Technical"

    def test_tactics_skill_exists(self):
        """Tactics should exist (7 configs use it)"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Tactics")
        assert skill is not None, "Tactics skill not found"
        assert skill.attribute == "Intelligence"
        assert skill.category == "Combat"

    def test_ritual_lore_skill_exists(self):
        """Ritual Lore should exist (5 configs use it)"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Ritual Lore")
        assert skill is not None, "Ritual Lore skill not found"
        assert skill.attribute == "Intelligence"
        assert skill.category == "Knowledge"


class TestSkillAliases:
    """Verify skill aliases resolve correctly"""

    def test_persuasion_aliases_to_charm(self):
        """Persuasion should alias to Charm (21 configs use it)"""
        from scripts.aeonisk.multiagent.skill_mapping import normalize_skill

        assert normalize_skill("Persuasion") == "Charm"
        assert normalize_skill("persuasion") == "Charm"  # Case insensitive

    def test_meditation_aliases_to_discipline(self):
        """Meditation should alias to Discipline (5 configs use it)"""
        from scripts.aeonisk.multiagent.skill_mapping import normalize_skill

        assert normalize_skill("Meditation") == "Discipline"
        assert normalize_skill("meditation") == "Discipline"

    def test_engineering_aliases_to_tech_craft(self):
        """Engineering should alias to Tech/Craft (16 configs use it)"""
        from scripts.aeonisk.multiagent.skill_mapping import normalize_skill

        assert normalize_skill("Engineering") == "Tech/Craft"
        assert normalize_skill("engineering") == "Tech/Craft"

    def test_observation_aliases_to_awareness(self):
        """Observation should alias to Awareness (1 config uses it)"""
        from scripts.aeonisk.multiagent.skill_mapping import normalize_skill

        assert normalize_skill("Observation") == "Awareness"
        assert normalize_skill("observation") == "Awareness"

    def test_deception_aliases_to_guile(self):
        """Deception should alias to Guile (already exists, verify it works)"""
        from scripts.aeonisk.multiagent.skill_mapping import normalize_skill

        # This alias should already exist
        assert normalize_skill("Deception") == "Guile"
        assert normalize_skill("deception") == "Guile"


class TestDatabaseCompleteness:
    """Verify skill database has balanced coverage"""

    def test_all_attributes_have_minimum_skills(self):
        """Each attribute should have ≥2 skills (after additions)"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE
        from scripts.aeonisk.multiagent.constants import YAGS_ATTRIBUTES

        # Count skills per attribute
        counts = Counter(skill.attribute for skill in SKILL_DATABASE.values())

        for attr in YAGS_ATTRIBUTES:
            assert counts[attr] >= 2, \
                f"{attr} has only {counts[attr]} skill(s) - need at least 2!"

    def test_strength_has_skills(self):
        """Strength should have at least 3 skills (was 0)"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        strength_skills = [s for s in SKILL_DATABASE.values() if s.attribute == "Strength"]
        assert len(strength_skills) >= 3, \
            f"Strength has {len(strength_skills)} skills, expected ≥3 (Climbing, Swimming, Lifting)"

    def test_endurance_has_skills(self):
        """Endurance should have at least 3 skills (was 0)"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        endurance_skills = [s for s in SKILL_DATABASE.values() if s.attribute == "Endurance"]
        assert len(endurance_skills) >= 3, \
            f"Endurance has {len(endurance_skills)} skills, expected ≥3 (Resistance, Stamina, Running)"

    def test_no_attribute_bloat(self):
        """No attribute should have >15 skills (prevent Intelligence bloat)"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        counts = Counter(skill.attribute for skill in SKILL_DATABASE.values())

        for attr, count in counts.items():
            assert count <= 15, \
                f"{attr} has {count} skills (bloat!) - max should be 15"

    def test_total_skills_increased(self):
        """Database should have ≥43 skills (from 32)"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        total = len(SKILL_DATABASE)
        assert total >= 43, \
            f"SKILL_DATABASE has {total} skills, expected ≥43 (32 original + 11 new)"

    def test_skill_count_by_attribute(self):
        """Verify expected skill distribution after additions"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        counts = Counter(skill.attribute for skill in SKILL_DATABASE.values())

        # After additions, expected distribution:
        # Strength: 3 (was 0)
        # Endurance: 3 (was 0)
        # Agility: 5
        # Dexterity: 4
        # Perception: 4
        # Intelligence: 15 (was 10, added 5)
        # Empathy: 6 (was 5, added Insight)
        # Willpower: 4

        expected_minimums = {
            "Strength": 3,
            "Endurance": 3,
            "Agility": 5,
            "Dexterity": 4,
            "Perception": 4,
            "Intelligence": 10,  # Allow some variance
            "Empathy": 6,
            "Willpower": 4
        }

        for attr, min_count in expected_minimums.items():
            actual = counts.get(attr, 0)
            assert actual >= min_count, \
                f"{attr} has {actual} skills, expected ≥{min_count}"


class TestSkillRouting:
    """Verify action_router.py handles new skills"""

    def test_climbing_routes_to_strength(self):
        """Climbing should route to Strength attribute"""
        # Note: action_router.py might not exist or might use different pattern
        # This test verifies the skill can be looked up with correct attribute
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Climbing")
        assert skill.attribute == "Strength"

    def test_void_lore_routes_to_intelligence(self):
        """Void Lore should route to Intelligence"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Void Lore")
        assert skill.attribute == "Intelligence"

    def test_insight_routes_to_empathy(self):
        """Insight should route to Empathy"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        skill = get_skill_info("Insight")
        assert skill.attribute == "Empathy"


class TestSkillCategories:
    """Verify skills are categorized correctly"""

    def test_movement_skills_exist(self):
        """Movement category should include Climbing, Swimming, Running"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        movement_skills = [s.name for s in SKILL_DATABASE.values() if s.category == "Movement"]

        assert "Climbing" in movement_skills
        assert "Swimming" in movement_skills
        assert "Running" in movement_skills

    def test_knowledge_skills_exist(self):
        """Knowledge category should include Void Lore, Ritual Lore"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        knowledge_skills = [s.name for s in SKILL_DATABASE.values() if s.category == "Knowledge"]

        assert "Void Lore" in knowledge_skills
        assert "Ritual Lore" in knowledge_skills

    def test_technical_skills_exist(self):
        """Technical category should include Hacking"""
        from scripts.aeonisk.multiagent.skill_descriptions import SKILL_DATABASE

        technical_skills = [s.name for s in SKILL_DATABASE.values() if s.category == "Technical"]

        assert "Hacking" in technical_skills


class TestSkillDetails:
    """Verify skill definitions have proper structure"""

    def test_new_skills_have_use_cases(self):
        """All new skills should have use_cases defined"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        new_skills = ["Climbing", "Swimming", "Lifting", "Resistance", "Stamina",
                     "Running", "Insight", "Void Lore", "Hacking", "Tactics", "Ritual Lore"]

        for skill_name in new_skills:
            skill = get_skill_info(skill_name)
            assert skill is not None, f"{skill_name} not found"
            assert skill.use_cases, f"{skill_name} missing use_cases"
            assert len(skill.use_cases) >= 3, \
                f"{skill_name} has {len(skill.use_cases)} use_cases, expected ≥3"

    def test_new_skills_have_descriptions(self):
        """All new skills should have clear descriptions"""
        from scripts.aeonisk.multiagent.skill_descriptions import get_skill_info

        new_skills = ["Climbing", "Swimming", "Lifting", "Resistance", "Stamina",
                     "Running", "Insight", "Void Lore", "Hacking", "Tactics", "Ritual Lore"]

        for skill_name in new_skills:
            skill = get_skill_info(skill_name)
            assert skill.description, f"{skill_name} missing description"
            assert len(skill.description) >= 20, \
                f"{skill_name} description too short: {skill.description}"


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
