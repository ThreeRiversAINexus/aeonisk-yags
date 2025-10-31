"""
Unit tests for structured synthesis (Phase 5: Pydantic AI migration).

Tests story advancement, enemy spawning, enemy removal, and clock management
using structured output instead of text marker parsing.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from typing import List

# Import schemas
from schemas.story_events import (
    RoundSynthesis,
    StoryAdvancement,
    EnemySpawn,
    EnemyRemoval,
    EnemyResolution,
    NewClock,
    ScenePivot
)
from schemas.shared_types import Position


class TestStoryAdvancement(unittest.TestCase):
    """Test story advancement with conditional enemy clearing."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_mechanics = Mock()
        self.mock_mechanics.current_round = 5
        self.mock_mechanics.scene_clocks = {'Old Clock': Mock()}

    def test_story_advancement_clears_enemies_by_default(self):
        """Test that clear_all_enemies=True clears all active enemies."""
        advancement = StoryAdvancement(
            should_advance=True,
            location="Safe House",
            situation="You've escaped. Time to regroup.",
            clear_all_enemies=True,  # Default behavior
            new_clocks=[]
        )

        self.assertTrue(advancement.clear_all_enemies)
        self.assertEqual(advancement.location, "Safe House")

    def test_story_advancement_preserves_enemies_when_disabled(self):
        """Test that clear_all_enemies=False preserves active enemies."""
        advancement = StoryAdvancement(
            should_advance=True,
            location="Rooftop Chase",
            situation="The enemies follow you to the rooftop!",
            clear_all_enemies=False,  # Preserve enemies
            new_clocks=[]
        )

        self.assertFalse(advancement.clear_all_enemies)

    def test_story_advancement_with_new_clocks(self):
        """Test story advancement spawning new clocks."""
        advancement = StoryAdvancement(
            should_advance=True,
            location="Corporate Archive",
            situation="You've reached the data vault.",
            clear_all_enemies=True,
            new_clocks=[
                NewClock(
                    name="Data Extraction",
                    max_ticks=6,
                    description="Copy critical files",
                    advance_meaning="progress made",
                    regress_meaning="security countermeasures"
                ),
                NewClock(
                    name="Security Response",
                    max_ticks=8,
                    description="Corporate security mobilizing",
                    advance_meaning="threat escalates",
                    regress_meaning="delays bought"
                )
            ]
        )

        self.assertEqual(len(advancement.new_clocks), 2)
        self.assertEqual(advancement.new_clocks[0].name, "Data Extraction")
        self.assertEqual(advancement.new_clocks[1].max_ticks, 8)

    def test_no_advancement(self):
        """Test StoryAdvancement with should_advance=False (no change)."""
        advancement = StoryAdvancement(
            should_advance=False
        )

        self.assertFalse(advancement.should_advance)
        self.assertIsNone(advancement.location)
        self.assertIsNone(advancement.situation)


class TestEnemySpawning(unittest.TestCase):
    """Test enemy spawning from structured output."""

    def test_enemy_spawn_basic(self):
        """Test basic enemy spawn."""
        spawn = EnemySpawn(
            template="Grunt",
            faction="ACG Security",
            archetype="Enforcer",
            count=2,
            spawn_reason="Alarm triggered",
            initial_position=Position.FAR_ENEMY
        )

        self.assertEqual(spawn.template, "Grunt")
        self.assertEqual(spawn.count, 2)
        self.assertEqual(spawn.initial_position, Position.FAR_ENEMY)

    def test_enemy_spawn_with_traits(self):
        """Test enemy spawn with custom traits."""
        spawn = EnemySpawn(
            template="Elite",
            faction="Void Cultists",
            archetype="Ritualist",
            count=1,
            spawn_reason="Ritual completed",
            initial_position=Position.NEAR_ENEMY,
            custom_traits="void-touched, regenerating"
        )

        self.assertEqual(spawn.custom_traits, "void-touched, regenerating")

    def test_multiple_enemies_same_spawn(self):
        """Test spawning multiple enemies of the same type."""
        spawn = EnemySpawn(
            template="Grunt",
            faction="Freeborn Pirates",
            archetype="Raider",
            count=3,
            spawn_reason="Reinforcements arrive",
            initial_position=Position.EXTREME_ENEMY
        )

        self.assertEqual(spawn.count, 3)


class TestEnemyRemoval(unittest.TestCase):
    """Test enemy removal (non-combat exits)."""

    def test_enemy_fled(self):
        """Test enemy fleeing from combat."""
        removal = EnemyRemoval(
            enemy_name="ACG Guard Captain",
            resolution=EnemyResolution.FLED,
            reason="Intimidated by overwhelming force, retreated through maintenance corridor"
        )

        self.assertEqual(removal.resolution, EnemyResolution.FLED)
        self.assertIn("intimidated", removal.reason.lower())

    def test_enemy_convinced(self):
        """Test enemy convinced to stand down."""
        removal = EnemyRemoval(
            enemy_name="Security Officer",
            resolution=EnemyResolution.CONVINCED,
            reason="Persuaded to let you pass in exchange for information"
        )

        self.assertEqual(removal.resolution, EnemyResolution.CONVINCED)

    def test_enemy_neutralized(self):
        """Test enemy arrested/captured."""
        removal = EnemyRemoval(
            enemy_name="Corrupt Magistrate",
            resolution=EnemyResolution.NEUTRALIZED,
            reason="Arrested by Pantheon Security"
        )

        self.assertEqual(removal.resolution, EnemyResolution.NEUTRALIZED)


class TestRoundSynthesis(unittest.TestCase):
    """Test full round synthesis with multiple components."""

    def test_round_synthesis_with_story_advancement_and_spawns(self):
        """Test the bug fix: story advancement + enemy spawning together."""
        synthesis = RoundSynthesis(
            narration="The facility alarms blare as you breach the vault. Security forces converge on your position from multiple corridors.",
            story_advancement=StoryAdvancement(
                should_advance=True,
                location="Data Vault - Level 3",
                situation="You've breached the vault but security is responding in force",
                clear_all_enemies=False,  # FIX: Don't clear enemies when spawning new ones
                new_clocks=[
                    NewClock(
                        name="Data Download",
                        max_ticks=6,
                        description="Extract critical files",
                        advance_meaning="progress made",
                        regress_meaning="upload interrupted"
                    )
                ]
            ),
            enemy_spawns=[
                EnemySpawn(
                    template="Elite",
                    faction="ACG Security",
                    archetype="Tactical Response",
                    count=2,
                    spawn_reason="Vault breach triggered tactical team deployment",
                    initial_position=Position.FAR_ENEMY
                )
            ],
            enemy_removals=[],
            clocks_filled=[],
            clocks_expired=[]
        )

        # Verify structure
        self.assertIsNotNone(synthesis.story_advancement)
        self.assertFalse(synthesis.story_advancement.clear_all_enemies)
        self.assertEqual(len(synthesis.enemy_spawns), 1)
        self.assertEqual(synthesis.enemy_spawns[0].count, 2)

    def test_round_synthesis_with_enemy_removal(self):
        """Test round synthesis with enemy fleeing."""
        synthesis = RoundSynthesis(
            narration="The cultists recoil in horror as their ritual fails. The leader flees through a void rift while the others surrender.",
            story_advancement=StoryAdvancement(should_advance=False),
            enemy_spawns=[],
            enemy_removals=[
                EnemyRemoval(
                    enemy_name="Void Cult Leader",
                    resolution=EnemyResolution.FLED,
                    reason="Escaped through emergency void rift after ritual failure"
                ),
                EnemyRemoval(
                    enemy_name="Void Cultist",
                    resolution=EnemyResolution.CONVINCED,
                    reason="Surrendered after leader fled and ritual collapsed"
                )
            ],
            clocks_filled=["Void Ritual"],
            clocks_expired=[]
        )

        self.assertEqual(len(synthesis.enemy_removals), 2)
        self.assertEqual(synthesis.enemy_removals[0].resolution, EnemyResolution.FLED)
        self.assertEqual(synthesis.enemy_removals[1].resolution, EnemyResolution.CONVINCED)

    def test_round_synthesis_with_session_end(self):
        """Test round synthesis declaring session end."""
        synthesis = RoundSynthesis(
            narration="With the data secured and the facility collapsing behind you, you escape to your ship. Mission accomplished.",
            story_advancement=StoryAdvancement(should_advance=False),
            enemy_spawns=[],
            enemy_removals=[],
            clocks_filled=["Mission Objective"],
            clocks_expired=[],
            session_end="victory",
            session_end_reason="Data extracted successfully, all objectives complete"
        )

        self.assertEqual(synthesis.session_end, "victory")
        self.assertIsNotNone(synthesis.session_end_reason)

    def test_cannot_use_scene_pivot_and_story_advancement(self):
        """Test validation: cannot use both scene_pivot and story_advancement."""
        with self.assertRaises(ValueError):
            RoundSynthesis(
                narration="Test narration",
                scene_pivot=ScenePivot(
                    should_pivot=True,
                    new_room="Control Room",
                    situation_change="Alarms blaring"
                ),
                story_advancement=StoryAdvancement(
                    should_advance=True,
                    location="Different Location",
                    situation="Major change"
                ),
                enemy_spawns=[],
                enemy_removals=[]
            )


class TestScenePivot(unittest.TestCase):
    """Test scene pivot (minor room transitions)."""

    def test_scene_pivot_basic(self):
        """Test basic scene pivot."""
        pivot = ScenePivot(
            should_pivot=True,
            new_room="Security Control Room",
            situation_change="Emergency lockdown engaged, blast doors sealing",
            clear_specific_clocks=["Breach Containment"],
            new_clocks=[
                NewClock(
                    name="Override Lockdown",
                    max_ticks=6,
                    description="Hack security terminal",
                    advance_meaning="progress made",
                    regress_meaning="countermeasures"
                )
            ]
        )

        self.assertTrue(pivot.should_pivot)
        self.assertEqual(pivot.new_room, "Security Control Room")
        self.assertEqual(len(pivot.clear_specific_clocks), 1)

    def test_scene_pivot_requires_fields_when_pivoting(self):
        """Test validation: scene pivot requires new_room and situation_change."""
        with self.assertRaises(ValueError):
            ScenePivot(
                should_pivot=True,
                # Missing new_room and situation_change
                new_room=None,
                situation_change=None
            )


class TestNewClock(unittest.TestCase):
    """Test new clock creation."""

    def test_new_clock_basic(self):
        """Test basic clock creation."""
        clock = NewClock(
            name="Passenger Safety",
            max_ticks=8,
            description="Evacuate civilians from void surge zone",
            advance_meaning="passengers evacuated",
            regress_meaning="passengers endangered"
        )

        self.assertEqual(clock.name, "Passenger Safety")
        self.assertEqual(clock.max_ticks, 8)
        self.assertEqual(clock.current_ticks, 0)  # Default

    def test_new_clock_with_initial_ticks(self):
        """Test clock with initial progress."""
        clock = NewClock(
            name="Ritual Progress",
            max_ticks=10,
            description="Void ritual nearing completion",
            advance_meaning="ritual progressing",
            regress_meaning="ritual disrupted",
            current_ticks=5
        )

        self.assertEqual(clock.current_ticks, 5)

    def test_clock_validation_current_exceeds_max(self):
        """Test validation: current_ticks cannot exceed max_ticks."""
        with self.assertRaises(ValueError):
            NewClock(
                name="Invalid Clock",
                max_ticks=6,
                description="Test",
                advance_meaning="test",
                regress_meaning="test",
                current_ticks=10  # Exceeds max!
            )


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for complex scenarios."""

    def test_bug_fix_scenario_advance_with_new_enemies(self):
        """
        Test the original bug: advancing story while spawning new enemies.

        Before fix: Enemies would be cleared AFTER spawning, leaving no enemies
        After fix: clear_all_enemies=False preserves newly spawned enemies
        """
        synthesis = RoundSynthesis(
            narration="You escape the facility, but corporate hunters track you to the transit hub. The platform is crowded with civilians, making a firefight risky. The hunters close in from multiple directions.",
            story_advancement=StoryAdvancement(
                should_advance=True,
                location="Transit Hub - Platform 7",
                situation="Corporate hunters have tracked you here",
                clear_all_enemies=False,  # KEY FIX: Don't clear when spawning
                new_clocks=[
                    NewClock(
                        name="Hunter Pursuit",
                        max_ticks=6,
                        description="Corporate kill team closing in",
                        advance_meaning="hunters closing in",
                        regress_meaning="hunters delayed"
                    )
                ]
            ),
            enemy_spawns=[
                EnemySpawn(
                    template="Elite",
                    faction="Corporate Hunters",
                    archetype="Operative",
                    count=2,
                    spawn_reason="Tracked you from facility breach",
                    initial_position=Position.FAR_ENEMY
                )
            ],
            enemy_removals=[]
        )

        # Verify the fix
        self.assertTrue(synthesis.story_advancement.should_advance)
        self.assertFalse(synthesis.story_advancement.clear_all_enemies)
        self.assertEqual(len(synthesis.enemy_spawns), 1)  # 1 spawn entry
        self.assertEqual(synthesis.enemy_spawns[0].count, 2)  # 2 enemies in that spawn

    def test_clean_story_advancement_no_enemies(self):
        """Test story advancement with enemy clearing (normal behavior)."""
        synthesis = RoundSynthesis(
            narration="You escape to the safe house. The pursuit is left behind as you slip through the undercity tunnels. The old safehouse is dusty but secure, hidden deep in the maintenance levels where few dare to venture.",
            story_advancement=StoryAdvancement(
                should_advance=True,
                location="Underground Safe House",
                situation="You've escaped. Time to regroup and plan.",
                clear_all_enemies=True,  # Clear old enemies
                new_clocks=[
                    NewClock(
                        name="Safe House Security",
                        max_ticks=8,
                        description="Establish perimeter security",
                        advance_meaning="defenses strengthened",
                        regress_meaning="security compromised"
                    )
                ]
            ),
            enemy_spawns=[],  # No new enemies
            enemy_removals=[]
        )

        self.assertTrue(synthesis.story_advancement.clear_all_enemies)
        self.assertEqual(len(synthesis.enemy_spawns), 0)


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestStoryAdvancement))
    suite.addTests(loader.loadTestsFromTestCase(TestEnemySpawning))
    suite.addTests(loader.loadTestsFromTestCase(TestEnemyRemoval))
    suite.addTests(loader.loadTestsFromTestCase(TestRoundSynthesis))
    suite.addTests(loader.loadTestsFromTestCase(TestScenePivot))
    suite.addTests(loader.loadTestsFromTestCase(TestNewClock))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationScenarios))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit(run_tests())
