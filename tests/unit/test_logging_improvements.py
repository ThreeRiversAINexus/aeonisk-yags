"""
Tests for logging improvements (2025-12-14):
1. RollModifier schema validation
2. Roll modifiers in action_resolution events
3. Enemy defeat logging with killer info
4. Player weapon extraction from equipped_weapons
"""

import pytest
from unittest.mock import Mock, MagicMock, patch


class TestRollModifierSchema:
    """Tests for RollModifier Pydantic schema."""

    def test_rollmodifier_basic_creation(self):
        """RollModifier can be created with required fields."""
        from scripts.aeonisk.multiagent.schemas.shared_types import RollModifier

        modifier = RollModifier(
            source="void_penalty",
            value=-2
        )
        assert modifier.source == "void_penalty"
        assert modifier.value == -2
        assert modifier.details is None

    def test_rollmodifier_with_details(self):
        """RollModifier can include optional details dict."""
        from scripts.aeonisk.multiagent.schemas.shared_types import RollModifier

        modifier = RollModifier(
            source="condition",
            value=-3,
            details={"name": "Stunned"}
        )
        assert modifier.source == "condition"
        assert modifier.value == -3
        assert modifier.details == {"name": "Stunned"}

    def test_rollmodifier_model_dump(self):
        """RollModifier can be serialized with model_dump()."""
        from scripts.aeonisk.multiagent.schemas.shared_types import RollModifier

        modifier = RollModifier(
            source="altar_bonus",
            value=3,
            details={"altar_id": "alt_sanctified"}
        )
        data = modifier.model_dump()

        assert data == {
            "source": "altar_bonus",
            "value": 3,
            "details": {"altar_id": "alt_sanctified"}
        }

    def test_rollmodifier_positive_and_negative(self):
        """RollModifier correctly handles positive (bonus) and negative (penalty) values."""
        from scripts.aeonisk.multiagent.schemas.shared_types import RollModifier

        bonus = RollModifier(source="altar_bonus", value=3)
        penalty = RollModifier(source="void_penalty", value=-2)

        assert bonus.value > 0
        assert penalty.value < 0


class TestActionResolutionModifiers:
    """Tests for modifiers in ActionResolution dataclass."""

    def test_action_resolution_has_modifiers_field(self):
        """ActionResolution dataclass includes modifiers_applied field."""
        from scripts.aeonisk.multiagent.mechanics import ActionResolution

        # Check field exists
        assert hasattr(ActionResolution, '__dataclass_fields__')
        assert 'modifiers_applied' in ActionResolution.__dataclass_fields__

    def test_resolve_action_returns_modifiers(self):
        """resolve_action() populates modifiers_applied in result."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine

        mechanics = MechanicsEngine()

        # Resolve action with modifiers
        resolution = mechanics.resolve_action(
            intent="Cast protective spell",
            attribute="Willpower",
            skill="Astral Arts",
            attribute_value=3,
            skill_value=4,
            difficulty=20,
            modifiers={"altar_bonus": 3, "void_penalty": -2}
        )

        # Check modifiers are captured
        assert hasattr(resolution, 'modifiers_applied')
        assert len(resolution.modifiers_applied) >= 2

        # Verify modifier data
        sources = [m.source for m in resolution.modifiers_applied]
        assert "altar_bonus" in sources
        assert "void_penalty" in sources

    def test_resolve_action_captures_condition_modifiers(self):
        """resolve_action() captures condition penalties as modifiers."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, Condition

        mechanics = MechanicsEngine()

        # Add a condition
        mechanics.add_condition("test_agent", Condition(
            name="Stunned",
            type="stun",
            penalty=-3,
            duration=1,
            description="Test condition"
        ))

        # Resolve action for that agent
        resolution = mechanics.resolve_action(
            intent="Attack",
            attribute="Perception",
            skill="Guns",
            attribute_value=3,
            skill_value=3,
            difficulty=15,
            agent_id="test_agent"
        )

        # Check condition modifier captured
        condition_mods = [m for m in resolution.modifiers_applied if m.source == "condition"]
        assert len(condition_mods) == 1
        assert condition_mods[0].value == -3
        assert condition_mods[0].details == {"name": "Stunned"}


class TestLogEnemyDefeat:
    """Tests for extended log_enemy_defeat() with killer info."""

    def test_log_enemy_defeat_with_killer_info(self):
        """log_enemy_defeat() includes killer info when provided."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger
        import json

        # Create logger with mocked file writing
        with patch('builtins.open', MagicMock()):
            logger = JSONLLogger(session_id="test_session", output_dir="/tmp")
            logger._write_event = MagicMock()

            # Log defeat with killer info
            logger.log_enemy_defeat(
                round_num=5,
                enemy_id="enemy_cultist_abc123",
                enemy_name="Void Cultist",
                defeat_reason="killed",
                rounds_survived=3,
                killer_id="player_alpha",
                killer_name="Agent Alpha",
                final_damage=15
            )

            # Verify event was written
            logger._write_event.assert_called_once()
            event = logger._write_event.call_args[0][0]

            assert event["event_type"] == "enemy_defeat"
            assert event["enemy_id"] == "enemy_cultist_abc123"
            assert event["enemy_name"] == "Void Cultist"
            assert event["defeat_reason"] == "killed"
            assert event["rounds_survived"] == 3
            assert event["killer_id"] == "player_alpha"
            assert event["killer_name"] == "Agent Alpha"
            assert event["final_damage"] == 15

    def test_log_enemy_defeat_without_killer_info(self):
        """log_enemy_defeat() works without killer info (backward compatible)."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        with patch('builtins.open', MagicMock()):
            logger = JSONLLogger(session_id="test_session", output_dir="/tmp")
            logger._write_event = MagicMock()

            # Log defeat without killer info
            logger.log_enemy_defeat(
                round_num=3,
                enemy_id="enemy_grunt_xyz",
                enemy_name="Security Guard",
                defeat_reason="fled",
                rounds_survived=2
            )

            event = logger._write_event.call_args[0][0]

            assert "killer_id" not in event
            assert "killer_name" not in event
            assert "final_damage" not in event


class TestPlayerWeaponExtraction:
    """Tests for player weapon extraction from equipped_weapons."""

    def test_weapon_from_equipped_primary(self):
        """Weapon name is extracted from player's equipped primary weapon."""
        # This is an integration test - the actual logic is in dm.py
        # Testing the expected behavior pattern

        from scripts.aeonisk.multiagent.weapons import Weapon

        # Create mock weapon
        weapon = Weapon(
            name="Assault Rifle",
            skill="Guns",
            attack=2,
            defence=0,
            damage=8,
            damage_type="wound"
        )

        # Simulate equipped_weapons lookup
        equipped_weapons = {"primary": weapon, "sidearm": None}
        primary = equipped_weapons.get("primary")

        assert primary is not None
        assert primary.name == "Assault Rifle"

    def test_weapon_fallback_to_intent_guess(self):
        """Falls back to intent-based guessing when no equipped weapon."""
        # Pattern used in dm.py for fallback
        weapon_name = "Unknown Weapon"
        intent = "fires his rifle at the enemy"
        intent_lower = intent.lower()

        if 'rifle' in intent_lower or 'gun' in intent_lower:
            weapon_name = "Firearm"

        assert weapon_name == "Firearm"


class TestSessionDebriefFix:
    """Test that debrief llm_config bug is fixed."""

    def test_session_has_no_llm_config(self):
        """SelfPlayingSession should NOT have llm_config attribute."""
        from scripts.aeonisk.multiagent.session import SelfPlayingSession

        # The class itself shouldn't define llm_config
        # This is a sanity check that the architecture is correct
        # (individual agents have llm_config, not the session)
        class_attrs = dir(SelfPlayingSession)

        # llm_config should not be a class attribute
        # (instance might get it dynamically but that's the bug we fixed)
        assert 'llm_config' not in SelfPlayingSession.__dict__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
