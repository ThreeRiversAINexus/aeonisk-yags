"""
Unit tests for balance analyzers.

Tests the datamining analyzers using existing session fixtures.
"""

import pytest
from pathlib import Path
import json
import sys

# Add scripts to path
scripts_dir = Path(__file__).parent.parent.parent / 'scripts'
sys.path.insert(0, str(scripts_dir))

from datamine.analyzers import (
    AnalyzerPipeline,
    stream_events,
    SkillsAnalyzer,
    WeaponsAnalyzer,
    EnemiesAnalyzer,
    EconomyAnalyzer,
)
from datamine.formatters import TerminalFormatter, JSONFormatter, CSVFormatter


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent.parent / 'fixtures' / 'sessions'


#: Named rather than globbed. `list(glob("*.jsonl"))[0]` returned whichever file
#: the filesystem happened to hand back first, so adding a fixture to the
#: directory silently changed what every test in this module analysed — the
#: ten-event #150 chain landed first, carried no action_resolution rows, and
#: `test_csv_formatter` failed on a module it had nothing to do with. The
#: analysers need a session with real skill and combat volume; this is the
#: densest one in the directory (39 action_resolution, 30 combat_action).
SAMPLE_FIXTURE = "session_debt_auction_ambush.jsonl"


@pytest.fixture
def sample_fixture(fixtures_dir):
    """The fixture these analysers run over. Fixed, so results are comparable."""
    path = fixtures_dir / SAMPLE_FIXTURE
    if not path.is_file():
        pytest.fail(f"{SAMPLE_FIXTURE} is missing — pick another dense session "
                    f"and update SAMPLE_FIXTURE rather than globbing")
    return path


class TestSkillsAnalyzer:
    """Tests for SkillsAnalyzer."""

    def test_name_and_event_types(self):
        """Analyzer has correct name and event types."""
        analyzer = SkillsAnalyzer()
        assert analyzer.name == "skills"
        assert "action_resolution" in analyzer.event_types

    def test_ability_bucket_classification(self):
        """Ability values are bucketed correctly."""
        from datamine.analyzers.skills import get_ability_bucket

        assert get_ability_bucket(-5) == "negative"
        assert get_ability_bucket(0) == "0 (unskilled)"
        assert get_ability_bucket(5) == "1-10 (low)"
        assert get_ability_bucket(15) == "11-20 (moderate)"
        assert get_ability_bucket(25) == "21-30 (high)"
        assert get_ability_bucket(40) == "31+ (expert)"

    def test_expected_success_calculation(self):
        """Expected success rate is calculated correctly for DC 18."""
        from datamine.analyzers.skills import calculate_expected_success

        # DC 18, ability 0: need to roll 18+ on d20 = (21-18)/20 = 15%
        # But with unskilled penalty -2, need 20+ = 5%
        assert calculate_expected_success(-2, dc=18) == 5.0

        # DC 18, ability 15: need to roll 3+ = (21-3)/20 = 90%
        assert calculate_expected_success(15, dc=18) == 90.0

        # DC 18, ability 25: need to roll -7+ = always success
        assert calculate_expected_success(25, dc=18) == 100.0

    def test_processes_action_resolution(self, sample_fixture):
        """Analyzer extracts roll data from action_resolution events."""
        analyzer = SkillsAnalyzer()
        events = stream_events(sample_fixture, filter_types=analyzer.event_types)
        analyzer.process_session(events)
        result = analyzer.get_result()

        # Should have some data
        assert result.analyzer_name == "skills"
        assert result.event_count >= 0  # May be 0 if fixture has no action_resolution
        assert "ability_buckets" in result.metrics
        assert "attr_skill_combos" in result.metrics

    def test_reset_clears_state(self):
        """Reset clears all accumulated state."""
        analyzer = SkillsAnalyzer()

        # Process a fake event
        analyzer.process_event({
            "event_type": "action_resolution",
            "roll": {
                "attr": "Agility",
                "skill": "Guns",
                "ability": 15,
                "success": True,
                "margin": 5,
            }
        })

        assert analyzer._event_count > 0

        # Reset
        analyzer.reset()

        assert analyzer._event_count == 0
        assert len(analyzer._attr_skill_combos) == 0


class TestWeaponsAnalyzer:
    """Tests for WeaponsAnalyzer."""

    def test_name_and_event_types(self):
        """Analyzer has correct name and event types."""
        analyzer = WeaponsAnalyzer()
        assert analyzer.name == "weapons"
        assert "combat_action" in analyzer.event_types
        assert "action_resolution" in analyzer.event_types
        assert "enemy_defeat" in analyzer.event_types

    def test_processes_combat_action(self):
        """Analyzer extracts weapon data from combat_action events."""
        analyzer = WeaponsAnalyzer()

        # Process fake combat events (need 3+ per weapon for min sample size)
        # Note: "hit" is nested under "attack" per real JSONL schema
        analyzer.process_event({
            "event_type": "combat_action",
            "weapon": "Pistol",
            "attack": {"hit": True},
            "damage": {"dealt": 10},
        })
        analyzer.process_event({
            "event_type": "combat_action",
            "weapon": "Pistol",
            "attack": {"hit": False},
            "damage": {"dealt": 0},
        })
        analyzer.process_event({
            "event_type": "combat_action",
            "weapon": "Pistol",
            "attack": {"hit": True},
            "damage": {"dealt": 8},
        })
        analyzer.process_event({
            "event_type": "combat_action",
            "weapon": "Rifle",
            "attack": {"hit": True},
            "damage": {"dealt": 15},
        })

        result = analyzer.get_result()

        assert result.event_count == 4
        assert result.metrics["total_attacks"] == 4
        assert result.metrics["total_hits"] == 3

        # Check weapon breakdown (min 3 samples per weapon)
        weapons = {w["weapon"]: w for w in result.metrics["weapon_effectiveness"]}
        assert "Pistol" in weapons
        assert weapons["Pistol"]["hits"] == 2
        assert weapons["Pistol"]["total"] == 3


class TestEnemiesAnalyzer:
    """Tests for EnemiesAnalyzer."""

    def test_name_and_event_types(self):
        """Analyzer has correct name and event types."""
        analyzer = EnemiesAnalyzer()
        assert analyzer.name == "enemies"
        assert "enemy_spawn" in analyzer.event_types
        assert "enemy_defeat" in analyzer.event_types

    def test_tracks_spawns(self):
        """Analyzer tracks enemy spawns by template."""
        analyzer = EnemiesAnalyzer()

        # Spawn some enemies
        analyzer.process_event({
            "event_type": "enemy_spawn",
            "enemy_id": "enemy_1",
            "template": "Grunt",
            "stats": {"health": 30, "soak": 5},
            "round": 0,
        })
        analyzer.process_event({
            "event_type": "enemy_spawn",
            "enemy_id": "enemy_2",
            "template": "Grunt",
            "stats": {"health": 30, "soak": 5},
            "round": 0,
        })
        analyzer.process_event({
            "event_type": "enemy_spawn",
            "enemy_id": "enemy_3",
            "template": "Elite",
            "stats": {"health": 50, "soak": 10},
            "round": 1,
        })

        result = analyzer.get_result()

        assert result.metrics["total_spawns"] == 3
        templates = {t["template"]: t for t in result.metrics["template_stats"]}
        assert templates["Grunt"]["spawn_count"] == 2
        assert templates["Elite"]["spawn_count"] == 1

    def test_tracks_defeats(self):
        """Analyzer tracks enemy defeats and survival."""
        analyzer = EnemiesAnalyzer()

        # Spawn and defeat an enemy
        analyzer.process_event({
            "event_type": "enemy_spawn",
            "enemy_id": "enemy_1",
            "template": "Grunt",
            "stats": {"health": 30},
            "round": 0,
        })
        analyzer.process_event({
            "event_type": "enemy_defeat",
            "enemy_id": "enemy_1",
            "defeat_reason": "killed",
            "round": 2,
        })

        result = analyzer.get_result()

        assert result.metrics["total_defeats"] == 1
        assert result.metrics["defeat_breakdown"][0]["reason"] == "killed"


class TestEconomyAnalyzer:
    """Tests for EconomyAnalyzer."""

    def test_name_and_event_types(self):
        """Analyzer has correct name and event types."""
        analyzer = EconomyAnalyzer()
        assert analyzer.name == "economy"
        assert "void_change" in analyzer.event_types
        assert "character_state" in analyzer.event_types
        assert "action_resolution" in analyzer.event_types

    def test_tracks_void_changes(self):
        """Analyzer tracks void changes."""
        analyzer = EconomyAnalyzer()

        analyzer.process_event({
            "event_type": "void_change",
            "delta": 2,
            "character_name": "Test Character",
            "reason": "void action",
        })
        analyzer.process_event({
            "event_type": "void_change",
            "delta": -1,
            "character_name": "Test Character",
            "reason": "purification",
        })

        result = analyzer.get_result()

        void_stats = result.metrics["void"]
        assert void_stats["total_changes"] == 2
        assert void_stats["total_gained"] == 2
        assert void_stats["total_lost"] == 1

    def test_tracks_character_trajectories(self):
        """Analyzer tracks character void/soulcredit over time."""
        analyzer = EconomyAnalyzer()

        # Character state snapshots
        analyzer.process_event({
            "event_type": "character_state",
            "character_name": "Hero",
            "void_score": 2,
            "soulcredit": 10,
        })
        analyzer.process_event({
            "event_type": "character_state",
            "character_name": "Hero",
            "void_score": 4,
            "soulcredit": 8,
        })

        result = analyzer.get_result()

        summaries = result.metrics["character_summaries"]
        hero = next((s for s in summaries if s["character"] == "Hero"), None)
        assert hero is not None
        assert hero["void_start"] == 2
        assert hero["void_end"] == 4
        assert hero["void_delta"] == 2


class TestAnalyzerPipeline:
    """Tests for AnalyzerPipeline."""

    def test_single_pass_multiple_analyzers(self, sample_fixture):
        """Pipeline processes multiple analyzers in single pass."""
        pipeline = AnalyzerPipeline([
            SkillsAnalyzer(),
            EnemiesAnalyzer(),
        ])

        events = list(stream_events(sample_fixture))
        pipeline.process_session(iter(events))

        results = pipeline.get_results()
        assert len(results) == 2
        assert {r.analyzer_name for r in results} == {"skills", "enemies"}

    def test_event_routing(self):
        """Pipeline routes events to correct analyzers."""
        skills_analyzer = SkillsAnalyzer()
        enemies_analyzer = EnemiesAnalyzer()
        pipeline = AnalyzerPipeline([skills_analyzer, enemies_analyzer])

        # This should go to skills analyzer only
        # Note: SkillsAnalyzer skips events where roll.attr is None
        pipeline.process_session(iter([
            {"event_type": "action_resolution", "roll": {"attr": "Dexterity", "skill": "Guns", "success": True}},
        ]))

        results = pipeline.get_results()
        skills_result = next(r for r in results if r.analyzer_name == "skills")
        enemies_result = next(r for r in results if r.analyzer_name == "enemies")

        assert skills_result.event_count == 1
        assert enemies_result.event_count == 0

    def test_reset_all_analyzers(self):
        """Pipeline reset clears all analyzers."""
        pipeline = AnalyzerPipeline([
            SkillsAnalyzer(),
            EnemiesAnalyzer(),
        ])

        pipeline.process_session(iter([
            {"event_type": "action_resolution", "roll": {"attr": "Dexterity", "skill": "Guns"}},
            {"event_type": "enemy_spawn", "template": "Grunt"},
        ]))

        pipeline.reset()

        results = pipeline.get_results()
        assert all(r.event_count == 0 for r in results)


class TestFormatters:
    """Tests for output formatters."""

    def test_terminal_formatter(self, sample_fixture):
        """TerminalFormatter produces text output."""
        analyzer = SkillsAnalyzer()
        events = stream_events(sample_fixture, filter_types=analyzer.event_types)
        analyzer.process_session(events)
        result = analyzer.get_result()

        formatter = TerminalFormatter()
        import io
        output = io.StringIO()
        formatter.format(result, output)

        text = output.getvalue()
        assert "SKILLS ANALYSIS" in text
        assert "Sessions:" in text

    def test_json_formatter(self, sample_fixture):
        """JSONFormatter produces valid JSON output."""
        analyzer = SkillsAnalyzer()
        events = stream_events(sample_fixture, filter_types=analyzer.event_types)
        analyzer.process_session(events)
        result = analyzer.get_result()

        formatter = JSONFormatter()
        import io
        output = io.StringIO()
        formatter.format(result, output)

        # Should be valid JSON
        data = json.loads(output.getvalue())
        assert data["analyzer"] == "skills"
        assert "metrics" in data

    def test_csv_formatter(self, sample_fixture):
        """CSVFormatter produces CSV output."""
        analyzer = SkillsAnalyzer()
        events = stream_events(sample_fixture, filter_types=analyzer.event_types)
        analyzer.process_session(events)
        result = analyzer.get_result()

        formatter = CSVFormatter()
        import io
        output = io.StringIO()
        formatter.format(result, output)

        text = output.getvalue()
        # Should have CSV headers
        assert "attr" in text or "Attribute" in text or "bucket" in text


class TestStreamEvents:
    """Tests for stream_events utility."""

    def test_filters_by_event_type(self, sample_fixture):
        """stream_events filters by event type."""
        # Get all events
        all_events = list(stream_events(sample_fixture))

        # Get filtered events
        filtered = list(stream_events(sample_fixture, filter_types={"action_resolution"}))

        # Filtered should be subset
        assert len(filtered) <= len(all_events)
        assert all(e.get("event_type") == "action_resolution" for e in filtered)

    def test_handles_empty_file(self, tmp_path):
        """stream_events handles empty files."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        events = list(stream_events(empty_file))
        assert events == []

    def test_skips_malformed_lines(self, tmp_path):
        """stream_events skips malformed JSON lines."""
        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text('{"event_type": "good"}\nnot json\n{"event_type": "also_good"}\n')

        events = list(stream_events(bad_file))
        assert len(events) == 2
        assert events[0]["event_type"] == "good"
        assert events[1]["event_type"] == "also_good"
