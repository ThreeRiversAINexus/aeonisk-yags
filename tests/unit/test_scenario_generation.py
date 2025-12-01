"""
Unit tests for ScenarioSetup schema validation.

Tests the constraints on scenario generation to ensure LLM-generated
scenarios meet validation requirements without falling back to generic content.
"""

import pytest
from pydantic import ValidationError

from scripts.aeonisk.multiagent.schemas.story_events import ScenarioSetup, NewClock


class TestScenarioSetupValidation:
    """Test ScenarioSetup schema validation constraints."""

    @pytest.fixture
    def valid_clock(self):
        """Fixture providing a valid clock."""
        return NewClock(
            name="Danger Level",
            max_ticks=6,
            description="Threat escalation",
            advance_meaning="threat escalates",
            regress_meaning="threat diminishes"
        )

    @pytest.fixture
    def minimal_valid_scenario(self, valid_clock):
        """Fixture providing a minimal valid scenario."""
        return {
            "theme": "Corporate espionage",
            "location": "R&D Facility",
            "situation": "You've been sent to infiltrate the facility and steal sensitive data.",
            "starting_clocks": [valid_clock],
            "success_conditions": "Extract the data and escape undetected",
            "failure_consequences": "Captured by security or data destroyed"
        }

    def test_valid_scenario_passes(self, minimal_valid_scenario):
        """Test that a valid scenario passes validation."""
        scenario = ScenarioSetup(**minimal_valid_scenario)
        assert scenario.theme == "Corporate espionage"
        assert scenario.location == "R&D Facility"
        assert scenario.void_level == 3  # default

    def test_location_at_max_length_passes(self, minimal_valid_scenario):
        """Test location at exactly 200 characters passes (relaxed constraint)."""
        # 200 characters exactly
        long_location = "The Gestation Terraces - Arcadia Sprawl, Sub-District 7-Alpha, Near the Void-Corrupted Transit Hub Where Reality Bleeds Into Nightmare and Corporate Security Patrols Have Ceased All Operations XXXXXXX"
        assert len(long_location) == 200

        minimal_valid_scenario["location"] = long_location
        scenario = ScenarioSetup(**minimal_valid_scenario)
        assert len(scenario.location) == 200

    def test_location_exceeds_max_length_fails(self, minimal_valid_scenario):
        """Test location exceeding 500 characters fails validation."""
        # 501 characters (schema max_length=500)
        too_long = "X" * 501
        assert len(too_long) == 501

        minimal_valid_scenario["location"] = too_long
        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "location" in str(exc_info.value)
        assert "500" in str(exc_info.value)

    def test_situation_at_max_length_passes(self, minimal_valid_scenario):
        """Test situation at exactly 1200 characters passes (relaxed constraint)."""
        # 1200 characters exactly (simulating verbose LLM output)
        long_situation = (
            "The party finds themselves deep within the heart of the Gestation Terraces, "
            "a biomechanical warren of pulsing tubes and corrupted flesh-machines. "
            "The air itself seems to breathe, heavy with void corruption that makes reality shimmer at the edges. "
            "Your contact, a rogue technician named Vex, has gone silent after transmitting coordinates to this location. "
            "The walls are lined with observation pods, each containing a figure suspended in amber fluid - "
            "some human, some... not quite. The lighting flickers between sickly green bioluminescence and harsh red emergency lights. "
            "A low thrumming sound reverberates through the floor, growing stronger with each passing moment. "
            "Your void sensors are screaming warnings - the corruption level here is off the charts, "
            "easily level 8 or higher. Through a cracked viewport ahead, you can see what appears to be "
            "a massive ritual chamber, where figures in tattered corporate uniforms move with jerky, puppet-like motions "
            "around a central void-rift that tears reality itself. The sight of it makes your bonds ache with sympathetic resonance. "
            "Time is running out. Additional padding text to reach exactly 1200 characters for testing max length validation XXXXXXXXXXX"
        )
        assert len(long_situation) == 1200

        minimal_valid_scenario["situation"] = long_situation
        scenario = ScenarioSetup(**minimal_valid_scenario)
        assert len(scenario.situation) == 1200

    def test_situation_exceeds_max_length_fails(self, minimal_valid_scenario):
        """Test situation exceeding 2500 characters fails validation."""
        # 2501 characters (schema max_length=2500)
        too_long = "X" * 2501
        assert len(too_long) == 2501

        minimal_valid_scenario["situation"] = too_long
        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "situation" in str(exc_info.value)
        assert "2500" in str(exc_info.value)

    def test_missing_success_conditions_fails(self, minimal_valid_scenario):
        """Test missing success_conditions raises ValidationError."""
        del minimal_valid_scenario["success_conditions"]

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "success_conditions" in str(exc_info.value)

    def test_missing_failure_consequences_fails(self, minimal_valid_scenario):
        """Test missing failure_consequences raises ValidationError."""
        del minimal_valid_scenario["failure_consequences"]

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "failure_consequences" in str(exc_info.value)

    def test_empty_success_conditions_fails(self, minimal_valid_scenario):
        """Test empty success_conditions fails min_length validation."""
        minimal_valid_scenario["success_conditions"] = ""

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "success_conditions" in str(exc_info.value)

    def test_empty_failure_consequences_fails(self, minimal_valid_scenario):
        """Test empty failure_consequences fails min_length validation."""
        minimal_valid_scenario["failure_consequences"] = ""

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "failure_consequences" in str(exc_info.value)

    def test_void_level_defaults_to_3(self, minimal_valid_scenario):
        """Test void_level defaults to 3 when not specified."""
        scenario = ScenarioSetup(**minimal_valid_scenario)
        assert scenario.void_level == 3

    def test_void_level_out_of_range_fails(self, minimal_valid_scenario):
        """Test void_level outside 0-10 range fails validation."""
        minimal_valid_scenario["void_level"] = 11

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "void_level" in str(exc_info.value)

    def test_no_starting_clocks_fails(self, minimal_valid_scenario):
        """Test scenario without starting clocks fails validation."""
        minimal_valid_scenario["starting_clocks"] = []

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "starting_clocks" in str(exc_info.value)

    def test_too_many_starting_clocks_fails(self, minimal_valid_scenario, valid_clock):
        """Test scenario with more than 4 starting clocks fails validation."""
        minimal_valid_scenario["starting_clocks"] = [valid_clock] * 5

        with pytest.raises(ValidationError) as exc_info:
            ScenarioSetup(**minimal_valid_scenario)

        assert "starting_clocks" in str(exc_info.value)

    def test_realistic_verbose_scenario_passes(self, valid_clock):
        """Test a realistic verbose scenario (similar to failed LLM output) passes with new limits."""
        scenario_data = {
            "theme": "Ritual Containment Crisis in Void-Corrupted Biotech Facility",
            "location": "The Gestation Terraces - Arcadia Sprawl, Biomechanical Research Wing Sub-Level 4",  # 95 chars
            "situation": (
                "Your team has been dispatched to investigate a distress signal from the Gestation Terraces, "
                "a notorious biotech research facility on the edge of Arcadia. Upon arrival, you find the main "
                "entrance sealed with corporate quarantine protocols, but a service tunnel grants access. "
                "Inside, the facility is in chaos - emergency lights strobe red, klaxons wail distantly, "
                "and the air is thick with void corruption that makes your skin crawl. Through observation "
                "windows, you glimpse what appears to be a ritual in progress: figures in tattered lab coats "
                "surrounding a central void-rift, their movements synchronized in an eerie dance. "
                "Your void sensors spike to level 8 - dangerously high. Time to decide: contain the ritual, "
                "evacuate survivors, or gather intelligence on what went wrong here."
            ),  # ~780 chars
            "starting_clocks": [
                valid_clock,
                NewClock(
                    name="Ritual Progress",
                    max_ticks=8,
                    description="Void summoning nears completion",
                    advance_meaning="ritual progresses",
                    regress_meaning="ritual disrupted"
                ),
                NewClock(
                    name="Facility Containment",
                    max_ticks=10,
                    description="Structural integrity failing",
                    advance_meaning="containment weakens",
                    regress_meaning="containment restored"
                )
            ],
            "success_conditions": "Disrupt the ritual and evacuate survivors before containment breach",
            "failure_consequences": "Void-rift expands uncontrollably, corrupting entire district"
        }

        scenario = ScenarioSetup(**scenario_data)
        assert scenario.theme is not None
        assert len(scenario.location) < 200
        assert len(scenario.situation) < 1200
        assert scenario.void_level == 3  # default
        assert len(scenario.starting_clocks) == 3


class TestScenarioSetupOldConstraints:
    """Tests documenting the OLD constraints that caused the failure."""

    @pytest.fixture
    def old_constraints_scenario(self):
        """Scenario that would fail with OLD constraints (100/800) but passes with NEW (200/1200)."""
        return {
            "theme": "Ritual Containment Crisis",
            "location": "The Gestation Terraces - Arcadia Sprawl, Sub-District 7-Alpha Biomechanical Research Facility Wing Complex",  # 108 chars
            "situation": (
                "The party finds themselves deep within the heart of the Gestation Terraces, "
                "a biomechanical warren of pulsing tubes and corrupted flesh-machines. "
                "The air itself seems to breathe, heavy with void corruption that makes reality shimmer at the edges. "
                "Your contact, a rogue technician named Vex, has gone silent after transmitting coordinates to this location. "
                "The walls are lined with observation pods, each containing a figure suspended in amber fluid - "
                "some human, some... not quite. The lighting flickers between sickly green bioluminescence and harsh red emergency lights. "
                "A low thrumming sound reverberates through the floor, growing stronger with each passing moment. "
                "Your void sensors are screaming warnings - the corruption level here is off the charts. "
                "Additional descriptive padding to exceed 800 character limit XXXXXXXXXXXXXXXXXXXXX"
            ),  # ~850 chars
            "starting_clocks": [
                NewClock(
                    name="Ritual Progress",
                    max_ticks=8,
                    description="Summoning nears completion",
                    advance_meaning="ritual progresses",
                    regress_meaning="ritual disrupted"
                )
            ],
            "success_conditions": "Disrupt the ritual before completion",
            "failure_consequences": "Void-rift tears reality apart"
        }

    def test_scenario_passes_with_new_constraints(self, old_constraints_scenario):
        """
        Test that scenarios which FAILED with old constraints (100/800)
        now PASS with new constraints (200/1200).

        This documents the fix for the production bug.
        """
        # This should NOT raise ValidationError with new constraints
        scenario = ScenarioSetup(**old_constraints_scenario)

        assert len(scenario.location) > 100  # Would have failed old constraint
        assert len(scenario.location) <= 200  # Passes new constraint

        assert len(scenario.situation) > 800  # Would have failed old constraint
        assert len(scenario.situation) <= 1200  # Passes new constraint
