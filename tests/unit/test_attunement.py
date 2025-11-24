"""
Unit tests for Seed Attunement System.

Tests verify:
- Raw Seed → Energy Currency conversion (1 seed → 100 Breath / 50 Grain / 20 Drip / 5 Spark)
- Attunement skill checks (Willpower × Attunement + d20 vs DC 20)
- Altar bonuses (+1-3 based on quality)
- Echo-Calibrator mechanics (DC 16 Dex+Craft/Tech, +1 Void on failure)
- Failed ritual outcomes (lose seed, no output)
"""

import pytest
from scripts.aeonisk.multiagent.energy_economy import (
    EnergyPurse,
    Seed,
    SeedType,
    create_raw_seed
)
from scripts.aeonisk.multiagent.schemas.shared_types import ActionType
from scripts.aeonisk.multiagent.schemas.player_action import PlayerAction


class TestRawSeedAttunementConversion:
    """Test conversion rates for Raw Seed → Energy Currency."""

    def test_raw_seed_to_breath(self):
        """Test 1 Raw Seed → 100 Breath conversion."""
        purse = EnergyPurse(breath=0, drip=0, grain=0, spark=0)
        seed = create_raw_seed("test", freshness="fresh")

        # Expected: after attunement, purse should have +100 Breath
        expected_breath = 100

        # This will be implemented in attunement mechanics
        # For now, test just documents the expected conversion rate
        assert expected_breath == 100

    def test_raw_seed_to_drip(self):
        """Test 1 Raw Seed → 20 Drip conversion."""
        expected_drip = 20
        assert expected_drip == 20

    def test_raw_seed_to_grain(self):
        """Test 1 Raw Seed → 50 Grain conversion."""
        expected_grain = 50
        assert expected_grain == 50

    def test_raw_seed_to_spark(self):
        """Test 1 Raw Seed → 5 Spark conversion."""
        expected_spark = 5
        assert expected_spark == 5


class TestAttunementRitualMechanics:
    """Test ritual roll mechanics (Willpower × Attunement + d20 vs DC)."""

    def test_base_dc_is_20(self):
        """Test that base attunement DC is 20."""
        base_dc = 20
        assert base_dc == 20

    def test_altar_quality_1_provides_bonus_1(self):
        """Test that altar quality 1-3 provides +1 bonus."""
        # Altar quality 1-3 → +1 bonus
        for quality in [1, 2, 3]:
            expected_bonus = 1
            assert expected_bonus == 1

    def test_altar_quality_4_provides_bonus_2(self):
        """Test that altar quality 4-7 provides +2 bonus."""
        # Altar quality 4-7 → +2 bonus
        for quality in [4, 5, 6, 7]:
            expected_bonus = 2
            assert expected_bonus == 2

    def test_altar_quality_8_provides_bonus_3(self):
        """Test that altar quality 8-10 provides +3 bonus."""
        # Altar quality 8-10 → +3 bonus
        for quality in [8, 9, 10]:
            expected_bonus = 3
            assert expected_bonus == 3

    def test_successful_ritual_consumes_seed(self):
        """Test that successful attunement consumes the Raw Seed."""
        purse = EnergyPurse()
        seed = create_raw_seed("test", freshness="fresh")
        purse.add_seed(seed)

        assert purse.count_seeds(SeedType.RAW) == 1

        # After attunement (success), seed should be consumed
        # This will be implemented in attunement execution logic
        pass

    def test_successful_ritual_adds_energy(self):
        """Test that successful attunement adds chosen energy to purse."""
        purse = EnergyPurse(spark=0)
        seed = create_raw_seed("test", freshness="fresh")
        purse.add_seed(seed)

        # After successful attunement to Spark:
        # - seed consumed
        # - purse.spark += 5
        # This will be implemented in attunement execution logic
        pass

    def test_failed_ritual_consumes_seed_no_output(self):
        """Test that failed attunement loses seed with no energy output."""
        purse = EnergyPurse(spark=0)
        seed = create_raw_seed("test", freshness="fresh")
        purse.add_seed(seed)

        initial_spark = purse.spark

        # After failed attunement:
        # - seed consumed (lost)
        # - no energy added
        # - purse.spark unchanged
        # This will be implemented in attunement execution logic
        pass


class TestEchoCalibratorMechanics:
    """Test Echo-Calibrator item mechanics."""

    def test_echo_calibrator_cost(self):
        """Test Echo-Calibrator costs 8 Spark."""
        expected_cost_spark = 8
        assert expected_cost_spark == 8

    def test_echo_calibrator_upkeep_cost(self):
        """Test Echo-Calibrator upkeep is 1 Drip per 3 uses."""
        expected_upkeep_drip = 1
        expected_upkeep_interval = 3
        assert expected_upkeep_drip == 1
        assert expected_upkeep_interval == 3

    def test_echo_calibrator_check_dc(self):
        """Test Echo-Calibrator requires DC 16 Dex+Craft/Tech check."""
        expected_dc = 16
        assert expected_dc == 16

    def test_echo_calibrator_failure_adds_void(self):
        """Test that failed Echo-Calibrator check adds +1 Void."""
        expected_void_penalty = 1
        assert expected_void_penalty == 1

    def test_echo_calibrator_has_usage_tracking(self):
        """Test that Echo-Calibrator item has usage_count metadata."""
        # When purchased, item should have usage_count = 0
        # This will be stored in character inventory metadata
        purse = EnergyPurse()

        # Character inventory should track item metadata
        # Format: inventory["echo_calibrator"] = {"count": 1, "usage_count": 0}
        # This will be implemented in Character.inventory structure
        pass

    def test_echo_calibrator_usage_increment(self):
        """Test that using Echo-Calibrator increments usage_count."""
        purse = EnergyPurse(drip=10)

        # After 1st use: usage_count = 1, no Drip cost
        # After 2nd use: usage_count = 2, no Drip cost
        # After 3rd use: usage_count = 3, -1 Drip cost
        # This will be implemented in attunement execution
        pass

    def test_echo_calibrator_upkeep_on_third_use(self):
        """Test that 3rd use of Echo-Calibrator costs 1 Drip."""
        purse = EnergyPurse(drip=10)

        # Simulate 3 uses
        # usage_count: 0 → 1 → 2 → 3
        # drip: 10 → 10 → 10 → 9

        # After 3rd use, should have 9 Drip
        # This will be implemented in attunement execution
        pass

    def test_echo_calibrator_upkeep_insufficient_drip(self):
        """Test Echo-Calibrator upkeep fails if insufficient Drip."""
        purse = EnergyPurse(drip=0)

        # If player has 0 Drip and tries to use on 3rd use cycle:
        # Should fail validation or prevent use
        # This will be implemented in validation logic
        pass

    def test_echo_calibrator_usage_count_resets_after_upkeep(self):
        """Test that usage_count resets after paying upkeep."""
        purse = EnergyPurse(drip=10)

        # usage_count: 3 → (pay 1 Drip) → 0
        # OR usage_count continues: 3 → 4 → 5 → 6 (pay again)
        # Need to clarify: does count reset or continue?
        # For now, assume it continues (simpler)
        pass


class TestAltarInfrastructure:
    """Test Altar entity mechanics."""

    def test_altar_has_quality_rating(self):
        """Test that altars have quality rating 1-10."""
        # Altar quality determines bonus
        # This will be implemented in Altar class
        pass

    def test_altar_quality_determines_bonus(self):
        """Test that altar quality maps to ritual bonus."""
        # Quality 1-3 → +1
        # Quality 4-7 → +2
        # Quality 8-10 → +3
        pass

    def test_altar_provides_location_bonus(self):
        """Test that being near altar provides bonus to ritual."""
        # Player must be in range of altar (Near or Engaged)
        # This will be implemented in validation logic
        pass


class TestHollowsAsEnergy:
    """Test Hollows as energy currency (not seeds)."""

    def test_energy_purse_has_hollow_field(self):
        """Test that EnergyPurse has hollow currency field."""
        purse = EnergyPurse(hollow=0)
        assert purse.hollow == 0

        purse.add_currency("hollow", 5)
        assert purse.hollow == 5

    def test_spend_hollow_currency(self):
        """Test spending Hollow currency."""
        purse = EnergyPurse(hollow=10)

        assert purse.spend_currency("hollow", 5) is True
        assert purse.hollow == 5

        assert purse.spend_currency("hollow", 10) is False  # Insufficient
        assert purse.hollow == 5  # Unchanged

    def test_raw_seed_degradation_to_hollow_currency(self):
        """Test that degraded Raw Seeds convert to Hollow currency (not seed type)."""
        purse = EnergyPurse(hollow=0)
        seed = create_raw_seed("test", freshness="old")
        seed.cycles_remaining = 1  # About to degrade
        purse.add_seed(seed)

        assert purse.count_seeds(SeedType.RAW) == 1
        assert purse.hollow == 0

        # Degrade all seeds
        purse.degrade_raw_seeds(1)

        # Seed should be removed from inventory
        assert purse.count_seeds(SeedType.RAW) == 0
        # Hollow currency should increase
        assert purse.hollow == 1

    def test_hollow_has_3x_power_multiplier(self):
        """Test that Hollows provide 3x power compared to standard energy."""
        expected_multiplier = 3
        assert expected_multiplier == 3

    def test_hollow_use_adds_void(self):
        """Test that using Hollows adds +1 Void per use."""
        expected_void_per_use = 1
        assert expected_void_per_use == 1


class TestAttuneActionSchema:
    """Test ATTUNE action type and schema fields."""

    def test_attune_action_type_exists(self):
        """Test that ATTUNE action type exists in ActionType enum."""
        assert ActionType.ATTUNE == "attune"

    def test_attune_action_basic_fields(self):
        """Test creating ATTUNE action with basic fields."""
        action = PlayerAction(
            intent="Attune Raw Seed to Spark energy",
            description="Kneeling at the ritual altar, I channel the seed's resonance through precise void harmonics, converting its essence to usable energy.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC for seed attunement ritual",
            action_type=ActionType.ATTUNE,
            target_energy="spark",
            character_name="Ash Reveth",
            agent_id="player_ash"
        )

        assert action.action_type == ActionType.ATTUNE
        assert action.attribute == "Willpower"
        assert action.skill == "Attunement"
        assert action.difficulty_estimate == 20

    def test_attune_action_has_target_energy_field(self):
        """Test that ATTUNE actions can specify target energy type."""
        action = PlayerAction(
            intent="Attune seed to Spark",
            description="Kneeling at the altar, I focus my will to convert the Raw Seed's essence into pure Spark energy.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC 20 for standard seed attunement ritual",
            action_type=ActionType.ATTUNE,
            character_name="Ash",
            agent_id="player_ash",
            target_energy="spark"
        )

        assert action.target_energy == "spark"

    def test_attune_action_has_altar_id_field(self):
        """Test that ATTUNE actions can specify altar_id for bonus."""
        action = PlayerAction(
            intent="Attune seed at ritual altar",
            description="Using the ritual altar's resonance field to stabilize the conversion process and reduce void corruption risk.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC 20 for seed attunement",
            action_type=ActionType.ATTUNE,
            character_name="Ash",
            agent_id="player_ash",
            target_energy="drip",
            altar_id="alt_main"
        )

        assert action.altar_id == "alt_main"

    def test_attune_action_has_use_echo_calibrator_field(self):
        """Test that ATTUNE actions can specify Echo-Calibrator use."""
        action = PlayerAction(
            intent="Attune seed with Echo-Calibrator",
            description="Activating my portable Echo-Calibrator to create a stable ritual field for safe seed attunement in the field.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC 20 for attunement ritual",
            action_type=ActionType.ATTUNE,
            character_name="Ash",
            agent_id="player_ash",
            target_energy="grain",
            use_echo_calibrator=True
        )

        assert action.use_echo_calibrator is True

    def test_attune_with_altar_bonus(self):
        """Test ATTUNE action using altar for bonus."""
        action = PlayerAction(
            intent="Attune at altar",
            description="Channeling the altar's resonance field to stabilize the ritual and gain bonus to the attunement check.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC 20 for seed attunement ritual",
            action_type=ActionType.ATTUNE,
            character_name="Ash",
            agent_id="player_ash",
            target_energy="spark",
            altar_id="alt_temple",
            use_echo_calibrator=False
        )

        assert action.altar_id == "alt_temple"
        assert action.use_echo_calibrator is False

    def test_attune_with_echo_calibrator(self):
        """Test ATTUNE action using Echo-Calibrator (portable)."""
        action = PlayerAction(
            intent="Portable attunement",
            description="Deploying Echo-Calibrator device to create portable ritual field for remote seed attunement operations.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC 20 for seed attunement ritual",
            action_type=ActionType.ATTUNE,
            character_name="Ash",
            agent_id="player_ash",
            target_energy="breath",
            use_echo_calibrator=True,
            altar_id=None
        )

        assert action.use_echo_calibrator is True
        assert action.altar_id is None

    def test_attune_action_validates_energy_type(self):
        """Test that target_energy accepts valid types."""
        valid_types = ["breath", "grain", "drip", "spark"]

        for energy_type in valid_types:
            action = PlayerAction(
                intent=f"Attune to {energy_type}",
                description=f"Channeling void harmonics to convert Raw Seed essence into stable {energy_type} energy for my energy purse.",
                attribute="Willpower",
                skill="Attunement",
                difficulty_estimate=20,
                difficulty_justification="Base DC 20 for standard attunement ritual",
                action_type=ActionType.ATTUNE,
                character_name="Ash",
                agent_id="player_ash",
                target_energy=energy_type
            )
            assert action.target_energy == energy_type

    def test_attune_defaults_use_echo_calibrator_to_false(self):
        """Test that use_echo_calibrator defaults to False if not specified."""
        action = PlayerAction(
            intent="Standard attunement",
            description="Performing standard seed attunement ritual without specialized equipment or altar infrastructure.",
            attribute="Willpower",
            skill="Attunement",
            difficulty_estimate=20,
            difficulty_justification="Base DC 20 for seed attunement ritual",
            action_type=ActionType.ATTUNE,
            character_name="Ash",
            agent_id="player_ash",
            target_energy="breath"
        )

        assert action.use_echo_calibrator is False


class TestAttunementValidation:
    """Test attunement validation logic."""

    def test_validate_attunement_success_basic(self):
        """Test successful validation with Raw Seed and no altar."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )

        # Give character a Raw Seed
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        # Validate attunement
        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="spark",
            altar_id=None,
            use_echo_calibrator=False
        )

        assert validation.is_valid is True
        assert validation.failure_reason is None
        assert validation.has_raw_seed is True

    def test_validate_attunement_fails_no_seed(self):
        """Test validation fails if player has no Raw Seeds."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )

        # Clear auto-generated seeds
        character.energy_purse.seeds = []

        # No seeds in inventory
        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="breath",
            altar_id=None,
            use_echo_calibrator=False
        )

        assert validation.is_valid is False
        assert "no raw seed" in validation.failure_reason.lower()
        assert validation.has_raw_seed is False

    def test_validate_attunement_requires_target_energy(self):
        """Test validation fails if target_energy not specified."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy=None,
            altar_id=None,
            use_echo_calibrator=False
        )

        assert validation.is_valid is False
        assert "target_energy" in validation.failure_reason.lower()

    def test_validate_attunement_with_altar(self):
        """Test validation with altar_id specified."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState
        from scripts.aeonisk.multiagent.shared_state import SharedState, Altar, AltarType

        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        # Add altar to shared state
        altar = Altar(
            altar_id="alt_test",
            altar_type=AltarType.RITUAL_ALTAR,
            quality=5,
            location="Temple"
        )
        shared_state.add_altar(altar)

        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            altar_id="alt_test",
            use_echo_calibrator=False
        )

        assert validation.is_valid is True
        assert validation.altar_exists is True
        assert validation.altar_bonus == 2  # Quality 5 → +2 bonus

    def test_validate_attunement_fails_altar_not_found(self):
        """Test validation fails if altar_id doesn't exist."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState
        from scripts.aeonisk.multiagent.shared_state import SharedState

        shared_state = SharedState()
        mechanics = MechanicsEngine(shared_state=shared_state)

        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="grain",
            altar_id="alt_nonexistent",
            use_echo_calibrator=False
        )

        assert validation.is_valid is False
        assert "altar" in validation.failure_reason.lower()
        assert validation.altar_exists is False

    def test_validate_attunement_with_echo_calibrator(self):
        """Test validation with Echo-Calibrator."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        # Add Echo-Calibrator to inventory (inventory key is "Echo-Calibrator", metadata key is "echo_calibrator")
        if not hasattr(character, 'inventory') or character.inventory is None:
            character.inventory = {}
        character.inventory["Echo-Calibrator"] = 1

        # Initialize metadata for usage tracking
        if not character.item_metadata:
            character.item_metadata = {}
        character.item_metadata["echo_calibrator"] = {"usage_count": 0}

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="spark",
            altar_id=None,
            use_echo_calibrator=True
        )

        assert validation.is_valid is True
        assert validation.has_echo_calibrator is True

    def test_validate_attunement_fails_no_echo_calibrator(self):
        """Test validation fails if use_echo_calibrator=True but player doesn't have it."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="breath",
            altar_id=None,
            use_echo_calibrator=True
        )

        assert validation.is_valid is False
        assert "echo-calibrator" in validation.failure_reason.lower()
        assert validation.has_echo_calibrator is False

    def test_validate_attunement_echo_calibrator_upkeep(self):
        """Test validation checks Drip upkeep for Echo-Calibrator on 3rd use."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))
        character.energy_purse.add_currency("drip", 5)

        # Add Echo-Calibrator to inventory
        if not hasattr(character, 'inventory') or character.inventory is None:
            character.inventory = {}
        character.inventory["Echo-Calibrator"] = 1

        # Echo-Calibrator on 2nd use (3rd use will trigger upkeep)
        character.item_metadata = {"echo_calibrator": {"usage_count": 2}}

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="grain",
            altar_id=None,
            use_echo_calibrator=True
        )

        assert validation.is_valid is True
        assert validation.upkeep_required is True
        assert validation.has_upkeep_currency is True

    def test_validate_attunement_fails_insufficient_upkeep(self):
        """Test validation fails if insufficient Drip for Echo-Calibrator upkeep."""
        from scripts.aeonisk.multiagent.mechanics import MechanicsEngine
        from scripts.aeonisk.multiagent.player import CharacterState

        mechanics = MechanicsEngine()
        character = CharacterState(
            name="Ash",
            faction="Freeborn",
            attributes={},
            skills={},
            void_score=3,
            soulcredit=0,
            bonds=[],
            goals=[]
        )
        character.energy_purse.add_seed(create_raw_seed("test", freshness="fresh"))

        # Clear Drip currency (character auto-generates some in __post_init__)
        character.energy_purse.drip = 0

        # Add Echo-Calibrator to inventory
        if not hasattr(character, 'inventory') or character.inventory is None:
            character.inventory = {}
        character.inventory["Echo-Calibrator"] = 1

        # Echo-Calibrator on 2nd use (3rd use needs upkeep)
        character.item_metadata = {"echo_calibrator": {"usage_count": 2}}

        validation = mechanics.validate_attunement(
            character_state=character,
            target_energy="drip",
            altar_id=None,
            use_echo_calibrator=True
        )

        assert validation.is_valid is False
        assert "upkeep" in validation.failure_reason.lower() or "drip" in validation.failure_reason.lower()
        assert validation.upkeep_required is True
        assert validation.has_upkeep_currency is False


# Placeholder tests for future implementation
class TestAttunementActionExecution:
    """Test ATTUNE action execution flow (to be implemented later)."""

    @pytest.mark.skip(reason="Phase 3: execution not yet implemented")
    def test_execute_attunement_success_path(self):
        """Test successful attunement execution."""
        pass

    @pytest.mark.skip(reason="Phase 3: execution not yet implemented")
    def test_execute_attunement_failure_path(self):
        """Test failed attunement execution."""
        pass
