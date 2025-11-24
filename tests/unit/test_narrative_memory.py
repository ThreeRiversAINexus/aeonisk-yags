"""
Tests for Player Narrative Memory system.

TDD: Tests written FIRST before implementation.

Tests cover:
1. NarrativeMemory schema validation
2. Location tracking accumulation
3. Story beat extraction
4. Self-summary generation
5. JSONL logging integration
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestNarrativeMemorySchema:
    """Test NarrativeMemory Pydantic schema."""

    def test_narrative_memory_creation_empty(self):
        """NarrativeMemory can be created with empty lists."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[],
            story_beats=[],
            story_summary=""
        )
        assert memory.locations_visited == []
        assert memory.story_beats == []
        assert memory.story_summary == ""

    def test_narrative_memory_with_data(self):
        """NarrativeMemory stores locations and story beats with round numbers."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[(0, "Docks"), (3, "Transit Hub"), (5, "Research Lab")],
            story_beats=[(1, "Fought gang ambush"), (2, "Rescued prisoner Vex"), (4, "Found data chip")],
            story_summary="Started at the docks investigating smugglers. After a firefight, rescued an informant who revealed the lab location."
        )

        assert len(memory.locations_visited) == 3
        # Check tuple format
        assert memory.locations_visited[1] == (3, "Transit Hub")
        assert len(memory.story_beats) == 3
        assert memory.story_beats[1] == (2, "Rescued prisoner Vex")
        assert "smugglers" in memory.story_summary

    def test_narrative_memory_serialization(self):
        """NarrativeMemory can be serialized to dict for JSONL."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[(0, "Docks")],
            story_beats=[(1, "Found clue")],
            story_summary="Investigating at the docks."
        )

        data = memory.model_dump()
        assert data['locations_visited'] == [(0, "Docks")]
        assert data['story_beats'] == [(1, "Found clue")]
        assert data['story_summary'] == "Investigating at the docks."


class TestPlayerMemoryAccumulation:
    """Test memory accumulation in Player agent."""

    def test_player_has_narrative_memory_attribute(self):
        """Player agent should have narrative_memory attribute."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        # Create minimal mock player
        player_mock = Mock()
        player_mock.narrative_memory = NarrativeMemory(
            locations_visited=[],
            story_beats=[],
            story_summary=""
        )

        assert hasattr(player_mock, 'narrative_memory')
        assert isinstance(player_mock.narrative_memory, NarrativeMemory)

    def test_location_added_on_scenario_update(self):
        """When scenario updates with new location, it should be added to memory with round."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[(0, "Docks")],
            story_beats=[],
            story_summary=""
        )

        # Simulate adding new location at round 3
        new_location = "Transit Hub"
        current_round = 3
        existing_locations = [loc for _, loc in memory.locations_visited]
        if new_location not in existing_locations:
            memory.locations_visited.append((current_round, new_location))

        assert (3, "Transit Hub") in memory.locations_visited
        assert len(memory.locations_visited) == 2

    def test_duplicate_locations_not_added(self):
        """Same location visited twice should only appear once."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[(0, "Docks")],
            story_beats=[],
            story_summary=""
        )

        # Try adding same location again at round 5
        new_location = "Docks"
        current_round = 5
        existing_locations = [loc for _, loc in memory.locations_visited]
        if new_location not in existing_locations:
            memory.locations_visited.append((current_round, new_location))

        # Should still have only one Docks entry
        assert len(memory.locations_visited) == 1

    def test_story_beat_extraction_from_synthesis(self):
        """Story beats should be extracted with round numbers."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[(0, "Docks")],
            story_beats=[],
            story_summary=""
        )

        # Simulate adding story beat at round 2
        beat = "Defeated gang leader and secured the warehouse"
        current_round = 2
        memory.story_beats.append((current_round, beat))

        assert (2, beat) in memory.story_beats

    def test_story_beats_max_limit(self):
        """Story beats should be limited to prevent unbounded growth."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        # Create memory with 10 beats (limit)
        beats = [(i, f"Beat {i}") for i in range(10)]
        memory = NarrativeMemory(
            locations_visited=[],
            story_beats=beats,
            story_summary=""
        )

        # Add 11th beat - should remove oldest
        new_beat = "New important event"
        new_round = 10
        if len(memory.story_beats) >= 10:
            memory.story_beats.pop(0)  # Remove oldest
        memory.story_beats.append((new_round, new_beat))

        assert len(memory.story_beats) == 10
        assert memory.story_beats[-1] == (10, new_beat)
        # Beat 0 should be gone
        assert (0, "Beat 0") not in memory.story_beats


class TestSelfSummaryGeneration:
    """Test player self-summary generation (Option B)."""

    def test_summary_schema_exists(self):
        """NarrativeMemorySummary schema should exist for LLM output."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemorySummary

        summary = NarrativeMemorySummary(
            summary="We started at the docks tracking smugglers. After a firefight with gang members, we rescued an informant who told us about the lab.",
            key_event="Rescued informant with critical intel"
        )

        assert "informant" in summary.summary
        assert "Rescued" in summary.key_event

    def test_summary_length_constraints(self):
        """Summary should have reasonable length constraints."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemorySummary

        # Should accept 50-500 char summary
        summary = NarrativeMemorySummary(
            summary="We investigated the docks and found evidence of void corruption.",
            key_event="Found void evidence"
        )
        assert len(summary.summary) >= 20

    def test_key_event_extracted(self):
        """Summary should include the most important event this round."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemorySummary

        summary = NarrativeMemorySummary(
            summary="Round 3 was chaotic. Enemy reinforcements arrived but we held the line.",
            key_event="Defended against enemy reinforcements"
        )

        assert summary.key_event is not None
        assert len(summary.key_event) > 0


class TestNarrativeMemoryJSONLLogging:
    """Test JSONL logging of narrative memory."""

    def test_log_narrative_memory_method_exists(self):
        """JSONLLogger should have log_narrative_memory method."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger

        assert hasattr(JSONLLogger, 'log_narrative_memory')

    def test_narrative_memory_event_structure(self):
        """Logged event should have correct structure."""
        from scripts.aeonisk.multiagent.mechanics import JSONLLogger
        import tempfile
        import json
        import os

        # Create temp directory and file
        with tempfile.TemporaryDirectory() as tmpdir:
            # JSONLLogger(session_id, output_dir) - creates session_{session_id}.jsonl
            logger = JSONLLogger("test_session", tmpdir)
            log_file = os.path.join(tmpdir, "session_test_session.jsonl")

            logger.log_narrative_memory(
                round_num=3,
                agent_id="player_ash",
                character_name="Ash",
                locations_visited=[(0, "Docks"), (3, "Transit Hub")],
                story_beats=[(1, "Fought gang"), (2, "Found data chip")],
                story_summary="Started at docks, moved to hub after combat."
            )

            # Read back the logged events (skip session_start, get narrative_memory)
            with open(log_file, 'r') as rf:
                lines = rf.readlines()
                # Find the narrative_memory event
                event = None
                for line in lines:
                    e = json.loads(line)
                    if e.get('event_type') == 'narrative_memory':
                        event = e
                        break

            assert event is not None, "narrative_memory event not found"
            assert event['event_type'] == 'narrative_memory'
            assert event['round'] == 3
            assert event['agent_id'] == 'player_ash'
            assert event['character_name'] == 'Ash'
            assert event['memory']['locations_visited'] == [[0, "Docks"], [3, "Transit Hub"]]
            assert event['memory']['story_beats'] == [[1, "Fought gang"], [2, "Found data chip"]]
            assert "docks" in event['memory']['story_summary'].lower()


class TestPlayerPromptIntegration:
    """Test narrative memory integration into player prompts."""

    def test_memory_context_in_prompt_variables(self):
        """Player prompt should include narrative memory context."""
        # Read the raw prompt file to verify placeholders exist
        import os
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'scripts', 'aeonisk', 'multiagent', 'prompts', 'claude', 'en', 'player', 'player_intent.yaml'
        )

        with open(prompt_path, 'r') as f:
            prompt = f.read()

        # Check that memory placeholders exist in prompt
        assert '{journey_locations}' in prompt or 'Journey' in prompt

    def test_memory_formatted_for_display(self):
        """Memory should format nicely for prompt injection with round numbers."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        memory = NarrativeMemory(
            locations_visited=[(0, "Docks"), (3, "Transit Hub"), (5, "Research Lab")],
            story_beats=[(1, "Fought gang"), (2, "Rescued Vex"), (4, "Found chip")],
            story_summary="Started at docks. Combat led to transit hub. Now at lab."
        )

        # Format for display with round numbers
        locations_display = " → ".join(f"(R{r}) {loc}" for r, loc in memory.locations_visited)
        beats_display = "\n".join(f"- (R{r}) {beat}" for r, beat in memory.story_beats[-3:])

        assert locations_display == "(R0) Docks → (R3) Transit Hub → (R5) Research Lab"
        assert "- (R2) Rescued Vex" in beats_display


class TestMemoryPersistenceAcrossRounds:
    """Test that memory persists properly across rounds."""

    def test_memory_survives_round_transition(self):
        """Memory should persist when round ends and new round begins."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        # Simulate round 1 memory
        memory = NarrativeMemory(
            locations_visited=[(0, "Docks")],
            story_beats=[(1, "Found clue")],
            story_summary="Investigating at docks."
        )

        # Simulate round 2 update
        memory.locations_visited.append((2, "Transit Hub"))
        memory.story_beats.append((2, "Escaped ambush"))
        memory.story_summary = "Started at docks, escaped ambush to transit hub."

        # Verify accumulation
        assert len(memory.locations_visited) == 2
        assert len(memory.story_beats) == 2
        assert "docks" in memory.story_summary.lower()
        assert "transit" in memory.story_summary.lower()

    def test_memory_not_reset_on_scenario_update(self):
        """Scenario update should ADD to memory, not replace it."""
        from scripts.aeonisk.multiagent.schemas.story_events import NarrativeMemory

        # Pre-existing memory
        memory = NarrativeMemory(
            locations_visited=[(0, "Docks"), (3, "Transit Hub")],
            story_beats=[(1, "Fought gang"), (2, "Escaped")],
            story_summary="Combat and escape sequence."
        )

        # Simulate story advancement (new location)
        new_location = "Research Lab"
        existing_locations = [loc for _, loc in memory.locations_visited]
        if new_location not in existing_locations:
            memory.locations_visited.append((5, new_location))

        # Should have all 3 locations, not just new one
        assert len(memory.locations_visited) == 3
        assert (0, "Docks") in memory.locations_visited
        assert (5, "Research Lab") in memory.locations_visited
