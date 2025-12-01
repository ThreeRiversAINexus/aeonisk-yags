"""
Structured Output Validation Pipeline Integration Tests

Tests that Pydantic schemas correctly validate game data from actual sessions.

This verifies the core architecture: Structured output > Keyword detection.

Note: These tests verify that schemas WORK with real data, not exhaustive validation.
For detailed schema validation, see tests/unit/test_schemas_*.py (future work).
"""

import pytest
import json
from pathlib import Path
from typing import List, Dict, Any
from pydantic import ValidationError


# ==============================================================================
# Fixtures
# ==============================================================================

def load_fixture(relative_path: str) -> List[Dict[str, Any]]:
    """Load JSONL fixture and return list of events."""
    fixture_paths = [
        Path(__file__).parent.parent.parent / "fixtures" / relative_path,
        Path(__file__).parent.parent.parent.parent / relative_path,
    ]

    for fixture_path in fixture_paths:
        if fixture_path.exists():
            events = []
            with open(fixture_path, 'r') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
            return events

    raise FileNotFoundError(f"Fixture not found: {relative_path}")


@pytest.fixture
def debt_auction_session():
    """Load debt auction ambush session for schema testing."""
    return load_fixture("sessions/session_debt_auction_ambush.jsonl")


# ==============================================================================
# Test Class 1: Schema Validation with Real Session Data
# ==============================================================================

class TestSchemaValidationWithRealData:
    """Test that Pydantic schemas can parse real session JSONL events."""

    def test_void_change_schema_rejects_environmental_targets(self):
        """
        Verify VoidChange schema rejects environmental/abstract targets (Bug #2 fix).

        Tests that the schema enforces character-specific void changes only.
        Environmental void should use scene clocks, not VoidChange.
        """
        from aeonisk.multiagent.schemas.shared_types import VoidChange

        # Valid: Character-specific void change
        valid_change = VoidChange(
            character_name="Ash Vex",
            amount=2,
            reason="Failed ritual without protective wards"
        )
        assert valid_change.character_name == "Ash Vex"

        # Invalid: Environmental target should be rejected
        with pytest.raises(ValidationError) as exc_info:
            VoidChange(
                character_name="Environmental Void",
                amount=-2,
                reason="Void dispersal"
            )

        # Verify error mentions environmental validation
        error_str = str(exc_info.value)
        assert "environmental" in error_str.lower() or "scene clocks" in error_str.lower()

    def test_damage_effect_schema_enforces_positive_damage(self):
        """
        Verify DamageEffect schema rejects negative damage amounts.

        Tests that schema validates sensible value ranges.
        """
        from aeonisk.multiagent.schemas.shared_types import DamageEffect

        # Valid: Positive damage
        valid_damage = DamageEffect(
            target="Enemy Raider",
            base_damage=8,
            dealt=5,  # After soak
            damage_type="slashing"
        )
        assert valid_damage.dealt == 5

        # Invalid: Negative damage
        with pytest.raises(ValidationError):
            DamageEffect(
                target="Enemy",
                base_damage=-3,  # Negative should be rejected
                dealt=-3,
                damage_type="healing?"
            )

    def test_soulcredit_change_schema_accepts_zero(self):
        """
        Verify SoulcreditChange schema accepts zero-amount changes.

        Tests that neutral actions can be explicitly marked as amount=0.
        """
        from aeonisk.multiagent.schemas.shared_types import SoulcreditChange

        # Zero is valid (neutral action)
        neutral_change = SoulcreditChange(
            character_name="Riven",
            amount=0,
            reason="Justified combat, morally neutral action"
        )
        assert neutral_change.amount == 0

    def test_condition_schema_accepts_debuffs(self):
        """
        Verify Condition schema accepts status effects like Stunned.

        Tests that status effects (debuffs/buffs) validate correctly.
        """
        from aeonisk.multiagent.schemas.shared_types import Condition

        stunned = Condition(
            name="Stunned",
            penalty=-3,  # Negative = debuff
            duration=2,
            description="Disoriented by crushing impact, -3 to all rolls"
        )
        assert stunned.name == "Stunned"
        assert stunned.penalty == -3
        assert stunned.duration == 2


# ==============================================================================
# Test Class 2: Schema Integration - Real Events
# ==============================================================================

class TestSchemaIntegrationWithFixtures:
    """Test that schemas could parse events from real sessions (conceptual)."""

    def test_session_events_use_structured_mechanics_not_keywords(self, debt_auction_session):
        """
        Verify session uses structured mechanical effects, not keyword parsing.

        This is a META test - it verifies we're NOT doing keyword detection.
        Tests that effects are in structured fields, not parsed from narration.
        """
        action_resolutions = [
            e for e in debt_auction_session
            if e.get("event_type") == "action_resolution"
        ]

        assert len(action_resolutions) > 0, "Should have action resolutions"

        # Check for structured mechanical data
        for resolution in action_resolutions:
            # Should have structured effects, not just narration
            has_structured_data = False

            if "effects" in resolution and len(resolution["effects"]) > 0:
                has_structured_data = True
            if "roll" in resolution:
                has_structured_data = True
            if "economy" in resolution:
                has_structured_data = True

            # At minimum, resolutions should have structured outcome data
            assert has_structured_data, \
                f"Resolution should have structured mechanical data, not just narration"

    def test_void_changes_not_applied_to_environmental_targets_in_fixture(self, debt_auction_session):
        """
        Verify fixture doesn't have void changes applied to environmental targets (Bug #2).

        Tests that real session data follows the schema constraint:
        VoidChange.character_name must be a specific character, not "Environmental Void".
        """
        # Look for any void economy changes in the session
        void_economy_changes = []

        for event in debt_auction_session:
            if event.get("event_type") == "action_resolution":
                economy = event.get("economy", {})
                if economy.get("void_delta", 0) != 0:
                    void_economy_changes.append({
                        "agent": event.get("agent"),
                        "delta": economy["void_delta"],
                        "triggers": economy.get("void_triggers", [])
                    })

        # If we found void changes, verify they're character-specific
        for change in void_economy_changes:
            # Should have character agent name, not "Environmental Void"
            assert change["agent"] is not None
            assert "environmental" not in change["agent"].lower(), \
                f"Bug #2: Void change applied to '{change['agent']}' (should be character name)"


# ==============================================================================
# Test Class 3: Schema Evolution Safety
# ==============================================================================

class TestSchemaEvolutionSafety:
    """Test that schema changes don't break existing functionality."""

    def test_enum_values_are_consistent(self):
        """
        Verify SuccessTier enum values match expected tiers.

        Tests that enum refactoring doesn't break tier logic.
        """
        from aeonisk.multiagent.schemas.shared_types import SuccessTier

        expected_tiers = [
            "critical_failure",
            "failure",
            "marginal",
            "moderate",
            "good",
            "excellent",
            "exceptional"
        ]

        actual_tiers = [tier.value for tier in SuccessTier]

        assert set(actual_tiers) == set(expected_tiers), \
            "SuccessTier enum values changed - may break existing code"

    def test_action_type_enum_has_core_types(self):
        """
        Verify ActionType enum includes core action categories.

        Tests that action categorization hasn't lost key types.
        """
        from aeonisk.multiagent.schemas.shared_types import ActionType

        core_types = ["combat", "social", "ritual", "investigate"]

        actual_types = [action_type.value for action_type in ActionType]

        for core_type in core_types:
            assert core_type in actual_types, \
                f"ActionType enum missing core type: {core_type}"


# ==============================================================================
# Test Class 4: Schema Defaults and Optional Fields
# ==============================================================================

class TestSchemaDefaults:
    """Test that schema defaults work correctly."""

    def test_mechanical_effects_defaults_to_empty_collections(self):
        """
        Verify MechanicalEffects has sensible defaults for optional fields.

        Tests that creating minimal effects doesn't require all fields.
        """
        from aeonisk.multiagent.schemas.action_resolution import MechanicalEffects

        # Create minimal effects
        effects = MechanicalEffects()

        # Should default to empty collections
        assert effects.void_changes == []
        assert effects.soulcredit_changes == []
        assert effects.clock_updates == []
        assert effects.conditions == []
        assert effects.position_changes == []
        assert effects.damage == []

    def test_void_change_requires_character_name(self):
        """
        Verify VoidChange enforces required fields.

        Tests that schema validation catches missing required data.
        """
        from aeonisk.multiagent.schemas.shared_types import VoidChange

        # Missing character_name
        with pytest.raises(ValidationError):
            VoidChange(
                amount=2,
                reason="Some reason"
                # Missing character_name
            )

    def test_soulcredit_change_requires_reason(self):
        """
        Verify SoulcreditChange enforces reason field with minimum length.

        Tests that moral economy tracking requires explanation.
        """
        from aeonisk.multiagent.schemas.shared_types import SoulcreditChange

        # Reason too short (< 5 chars)
        with pytest.raises(ValidationError):
            SoulcreditChange(
                character_name="Player",
                amount=1,
                reason="yep"  # Too short
            )

        # Valid reason
        valid_change = SoulcreditChange(
            character_name="Player",
            amount=1,
            reason="Defeated void creature"  # Long enough
        )
        assert valid_change.reason is not None
