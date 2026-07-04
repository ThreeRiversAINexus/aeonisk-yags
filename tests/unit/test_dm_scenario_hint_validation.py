"""
Unit tests for DM scenario hint validation and enforcement.

Tests ensure that _scenario_hint constraints from session configs are:
1. Properly extracted and injected into prompts
2. Validated after scenario generation
3. Enforced via retry logic when violated
"""

import pytest
from typing import Dict, Any, Optional
from scripts.aeonisk.multiagent.schemas.story_events import ScenarioSetup, NewClock


# Test helpers for creating valid scenarios

def make_test_clock(name="Test Clock") -> NewClock:
    """Create a valid NewClock for testing."""
    return NewClock(
        name=name,
        max_ticks=8,
        description="Test clock for validation testing purposes",
        advance_meaning="situation worsens",
        regress_meaning="situation improves"
    )


def make_test_scenario(**overrides) -> ScenarioSetup:
    """
    Create a valid ScenarioSetup for testing with optional field overrides.

    All string fields meet minimum length requirements.
    """
    defaults = {
        'theme': "Investigation and crisis management scenario",
        'location': "Generic Test Location Station",
        'situation': "A mysterious situation unfolds requiring immediate player attention and decision making.",
        'void_level': 3,
        'starting_clocks': [make_test_clock()],
        'success_conditions': "Resolve the crisis successfully without casualties",
        'failure_consequences': "Mission fails with dire consequences for the station"
    }
    defaults.update(overrides)
    return ScenarioSetup(**defaults)


# Mock scenario generation for testing validation logic
class MockScenarioValidator:
    """
    Test helper to validate generated scenarios against hints.

    This will be integrated into dm.py as _validate_scenario_against_hint()
    """

    @staticmethod
    def parse_hint_requirements(hint: str) -> Dict[str, Any]:
        """
        Extract validation requirements from scenario hint string.

        Returns dict with:
        - required_void_level: int or None
        - prohibited_elements: List[str]
        - required_elements: List[str]
        - required_location_keywords: List[str]
        """
        requirements = {
            'required_void_level': None,
            'prohibited_elements': [],
            'required_elements': [],
            'required_location_keywords': []
        }

        hint_lower = hint.lower()

        # Extract void_level requirement
        if 'void_level' in hint_lower or 'void level' in hint_lower:
            import re
            match = re.search(r'void[_ ]level\s*(\d+)', hint_lower)
            if match:
                requirements['required_void_level'] = int(match.group(1))

        # Extract prohibited elements
        if 'no spawn_enemy' in hint_lower or 'no enemies' in hint_lower:
            requirements['prohibited_elements'].append('enemies')
        if 'no npcs' in hint_lower or 'no npc' in hint_lower:
            requirements['prohibited_elements'].append('npcs')
        if 'no combat' in hint_lower:
            requirements['prohibited_elements'].append('combat')

        # Extract required location keywords
        if 'mining station' in hint_lower:
            requirements['required_location_keywords'].append('mining')
        if 'terminus outpost' in hint_lower:
            requirements['required_location_keywords'].extend(['terminus', 'outpost'])
        if 'resonance spire' in hint_lower:
            requirements['required_location_keywords'].extend(['resonance', 'spire'])

        return requirements

    @staticmethod
    def validate_scenario(scenario: ScenarioSetup, hint: str) -> tuple[bool, list[str]]:
        """
        Validate generated scenario against hint requirements.

        Returns:
            (is_valid, violations) where violations is list of error messages
        """
        violations = []
        requirements = MockScenarioValidator.parse_hint_requirements(hint)

        # Validate void_level
        if requirements['required_void_level'] is not None:
            if scenario.void_level != requirements['required_void_level']:
                violations.append(
                    f"Void level mismatch: hint requires {requirements['required_void_level']}, "
                    f"got {scenario.void_level}"
                )

        # Validate prohibited elements
        if 'enemies' in requirements['prohibited_elements']:
            if scenario.initial_enemies:
                violations.append(
                    f"Prohibited element 'enemies' found: scenario has {len(scenario.initial_enemies)} enemies "
                    f"but hint says NO enemies"
                )

        # Note: NPCs and combat detection would require analyzing situation text
        # For now, we validate what's available in structured schema

        # Validate location keywords
        location_lower = scenario.location.lower()
        for keyword in requirements['required_location_keywords']:
            if keyword not in location_lower:
                violations.append(
                    f"Required location keyword '{keyword}' not found in location: {scenario.location}"
                )

        return (len(violations) == 0, violations)


# Test cases

class TestScenarioHintParsing:
    """Test extraction of validation requirements from hint strings."""

    def test_parse_void_level_requirement(self):
        """Should extract void_level from hint."""
        hint = "Mining Station (void_level 6) - plague outbreak"
        requirements = MockScenarioValidator.parse_hint_requirements(hint)
        assert requirements['required_void_level'] == 6

    def test_parse_void_level_with_space(self):
        """Should handle 'void level' with space."""
        hint = "Station with void level 8 and critical breach"
        requirements = MockScenarioValidator.parse_hint_requirements(hint)
        assert requirements['required_void_level'] == 8

    def test_parse_no_enemies_prohibition(self):
        """Should detect NO SPAWN_ENEMY prohibition."""
        hint = "Pure PvP - NO SPAWN_ENEMY, just two PCs competing"
        requirements = MockScenarioValidator.parse_hint_requirements(hint)
        assert 'enemies' in requirements['prohibited_elements']

    def test_parse_no_npcs_prohibition(self):
        """Should detect NO NPCs prohibition."""
        hint = "Solo investigation - absolutely NO NPCs present"
        requirements = MockScenarioValidator.parse_hint_requirements(hint)
        assert 'npcs' in requirements['prohibited_elements']

    def test_parse_location_keywords(self):
        """Should extract location keywords for validation."""
        hint = "Terminus Outpost mining station scenario"
        requirements = MockScenarioValidator.parse_hint_requirements(hint)
        assert 'terminus' in requirements['required_location_keywords']
        assert 'outpost' in requirements['required_location_keywords']
        assert 'mining' in requirements['required_location_keywords']


class TestScenarioValidation:
    """Test validation of generated scenarios against hints."""

    def test_valid_scenario_with_matching_void_level(self):
        """Should pass validation when void_level matches hint."""
        scenario = make_test_scenario(
            location="Terminus Outpost Mining Station",
            void_level=6
        )
        hint = "Terminus Outpost (void_level 6) - plague outbreak"

        is_valid, violations = MockScenarioValidator.validate_scenario(scenario, hint)
        assert is_valid, f"Expected valid scenario, got violations: {violations}"
        assert len(violations) == 0

    def test_invalid_void_level_mismatch(self):
        """Should fail validation when void_level doesn't match hint."""
        scenario = make_test_scenario(
            void_level=3  # Wrong! Hint says 6
        )
        hint = "Mining Station (void_level 6) - plague"

        is_valid, violations = MockScenarioValidator.validate_scenario(scenario, hint)
        assert not is_valid, "Expected validation failure for void_level mismatch"
        assert len(violations) > 0
        assert "void level mismatch" in violations[0].lower()

    def test_invalid_prohibited_enemies_present(self):
        """Should fail validation when enemies present but hint says NO enemies."""
        from scripts.aeonisk.multiagent.schemas.story_events import EnemySpawn

        scenario = make_test_scenario(
            initial_enemies=[  # Wrong! Hint says NO enemies
                EnemySpawn(
                    template="Grunt",
                    faction="Independent",
                    archetype="Enforcer",
                    count=2,
                    spawn_reason="Test enemies for validation"
                )
            ]
        )
        hint = "Pure PvP - NO SPAWN_ENEMY, just two PCs"

        is_valid, violations = MockScenarioValidator.validate_scenario(scenario, hint)
        assert not is_valid, "Expected validation failure for prohibited enemies"
        assert len(violations) > 0
        assert "prohibited element 'enemies'" in violations[0].lower()

    def test_invalid_location_keywords_missing(self):
        """Should fail validation when required location keywords not present."""
        scenario = make_test_scenario(
            location="Random Space Station"  # Wrong! Should be "Terminus Outpost"
        )
        hint = "Terminus Outpost scenario with investigation"

        is_valid, violations = MockScenarioValidator.validate_scenario(scenario, hint)
        assert not is_valid, "Expected validation failure for missing location keywords"
        assert len(violations) >= 2  # Both 'terminus' and 'outpost' should be missing
        assert any('terminus' in v.lower() for v in violations)
        assert any('outpost' in v.lower() for v in violations)

    def test_valid_scenario_no_enemies_when_prohibited(self):
        """Should pass validation when no enemies present and hint prohibits them."""
        scenario = make_test_scenario(
            initial_enemies=[]  # Correct - no enemies
        )
        hint = "Pure PvP - NO SPAWN_ENEMY, NO NPCs, just two PCs"

        is_valid, violations = MockScenarioValidator.validate_scenario(scenario, hint)
        assert is_valid, f"Expected valid scenario, got violations: {violations}"
        assert len(violations) == 0


class TestPromptInjection:
    """Test that scenario hints are properly injected into prompts."""

    def test_hint_appears_at_top_of_prompt(self):
        """Scenario hint should appear before all other context."""
        # This will test the actual dm.py implementation
        # For now, we document the expected behavior
        hint = "Test scenario hint"

        # Expected prompt structure:
        # 1. CRITICAL SCENARIO CONSTRAINTS (scenario_hint)
        # 2. Party context
        # 3. Lore context
        # 4. Variety context
        # 5. Scenario requirements template

        # TODO: Add integration test that calls _generate_ai_scenario()
        # and verifies prompt structure
        pass

    def test_system_prompt_includes_validation_warning(self):
        """System prompt should warn LLM about validation checks."""
        # Expected system prompt enhancement:
        # "Your scenario MUST match the CRITICAL SCENARIO CONSTRAINTS.
        #  Violations will cause regeneration. Pay special attention to:
        #  - void_level (must match exactly)
        #  - Prohibited elements (NO SPAWN_ENEMY means zero enemies)
        #  - Required locations/NPCs (use exact names from constraints)"

        # TODO: Test actual system prompt construction in dm.py
        pass


class TestRetryLogic:
    """Test scenario regeneration when validation fails."""

    @pytest.mark.asyncio
    async def test_retry_on_validation_failure(self):
        """Should retry scenario generation up to 3 times on validation failure."""
        # TODO: Mock _generate_scenario_structured to return invalid scenarios,
        # then verify it retries and eventually succeeds or raises error
        pass

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises_error(self):
        """Should raise error after 3 failed validation attempts."""
        # TODO: Mock _generate_scenario_structured to always return invalid scenarios,
        # verify it raises RuntimeError after 3 attempts
        pass

    @pytest.mark.asyncio
    async def test_validation_violations_logged(self):
        """Should log validation violations for debugging."""
        # TODO: Verify that violations are logged with logger.warning()
        pass


class TestRealValidatorLocationAlternatives:
    """Tests against the REAL dm.py validator (not the mock above).

    Regression: 2026-07-04 corpus pilot, scenario 19 — hint mentioned
    'ArcGen', the DM generated location 'Arcane Genetics Debt Registry
    Annex', and validation failed 3x because it demanded the literal
    token 'arcgen'. Named entities must accept their spelled-out and
    abbreviated forms interchangeably.
    """

    @staticmethod
    def _validate(scenario, hint):
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        return dm._validate_scenario_against_hint(scenario, hint)

    def test_spelled_out_location_satisfies_abbreviated_hint(self):
        scenario = make_test_scenario(
            location="Arcane Genetics Debt Registry Annex, Aeonisk Prime")
        hint = "ArcGen debt registry after hours, severance bargain"

        is_valid, violations = self._validate(scenario, hint)
        assert is_valid, f"violations: {violations}"

    def test_abbreviated_location_satisfies_spelled_out_hint(self):
        scenario = make_test_scenario(location="ArcGen Tower, sublevel 3")
        hint = "Arcane Genetics corporate scenario"

        is_valid, violations = self._validate(scenario, hint)
        assert is_valid, f"violations: {violations}"

    def test_unrelated_location_still_rejected(self):
        scenario = make_test_scenario(location="Random Dockside Warehouse")
        hint = "ArcGen debt registry scenario"

        is_valid, violations = self._validate(scenario, hint)
        assert not is_valid
        assert any("arcgen" in v.lower() for v in violations)

    def test_single_keyword_requirements_still_enforced(self):
        scenario = make_test_scenario(location="Terminus Outpost Mining Station")
        hint = "Terminus Outpost mining station scenario"

        is_valid, violations = self._validate(scenario, hint)
        assert is_valid, f"violations: {violations}"


# Integration test helper (to be run manually against real LLM)

class TestRealScenarioGeneration:
    """Integration tests with real LLM calls (expensive, run manually)."""

    @pytest.mark.skip(reason="Expensive LLM call - run manually only")
    @pytest.mark.asyncio
    async def test_real_pvp_scenario_respects_no_enemies(self):
        """Real LLM should respect NO SPAWN_ENEMY constraint."""
        # TODO: Create minimal DM instance, call _generate_ai_scenario()
        # with PvP hint, verify no enemies in result
        pass

    @pytest.mark.skip(reason="Expensive LLM call - run manually only")
    @pytest.mark.asyncio
    async def test_real_void_level_constraint_respected(self):
        """Real LLM should generate scenario with exact void_level from hint."""
        # TODO: Test with "void_level 8" hint, verify result has void_level=8
        pass
