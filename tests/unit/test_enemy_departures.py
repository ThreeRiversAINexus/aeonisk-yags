"""
Tests for enemy_departures field in ConversionDecisions.

This tests the new enemy_departures feature that allows simple removal
of enemies who leave the scene without narrative transformation.
"""

import pytest
from scripts.aeonisk.multiagent.schemas.story_events import ConversionDecisions


def test_enemy_departures_field_exists():
    """ConversionDecisions should have enemy_departures field."""
    decisions = ConversionDecisions(
        enemy_conversions=[],
        escalations=[],
        npc_spawns=[],
        npc_departures=[],
        enemy_departures=["enemy_grunt_abc123"],
        enemy_spawns=[],
        reasoning="Test enemy departure"
    )

    assert hasattr(decisions, 'enemy_departures')
    assert decisions.enemy_departures == ["enemy_grunt_abc123"]


def test_enemy_departures_defaults_to_empty_list():
    """enemy_departures should default to empty list if not provided."""
    decisions = ConversionDecisions(
        enemy_conversions=[],
        escalations=[],
        npc_spawns=[],
        npc_departures=[],
        enemy_spawns=[],
        reasoning="Test without enemy departures"
    )

    assert decisions.enemy_departures == []


def test_enemy_departures_accepts_multiple_ids():
    """enemy_departures should accept multiple enemy agent IDs."""
    enemy_ids = [
        "enemy_grunt_8cb76347",
        "enemy_grunt_4b00689d",
        "enemy_grunt_6c226863"
    ]

    decisions = ConversionDecisions(
        enemy_conversions=[],
        escalations=[],
        npc_spawns=[],
        npc_departures=[],
        enemy_departures=enemy_ids,
        enemy_spawns=[],
        reasoning="Three Cathedral Security enforcers stood down and departed"
    )

    assert len(decisions.enemy_departures) == 3
    assert all(enemy_id in decisions.enemy_departures for enemy_id in enemy_ids)


def test_entity_lifecycle_result_includes_enemies_departed():
    """EntityLifecycleResult should track enemies_departed."""
    from scripts.aeonisk.multiagent.schemas.story_events import EntityLifecycleResult

    result = EntityLifecycleResult()
    result.enemies_departed = ["enemy_grunt_abc123", "enemy_raider_def456"]

    assert len(result.enemies_departed) == 2
    assert "enemy_grunt_abc123" in result.enemies_departed


def test_entity_lifecycle_result_jsonl_includes_enemies_departed():
    """EntityLifecycleResult.to_jsonl_dict() should include enemies_departed."""
    from scripts.aeonisk.multiagent.schemas.story_events import EntityLifecycleResult

    result = EntityLifecycleResult()
    result.enemies_departed = ["enemy_grunt_123"]

    jsonl_dict = result.to_jsonl_dict(round_num=3)

    assert 'enemies_departed' in jsonl_dict
    assert jsonl_dict['enemies_departed'] == ["enemy_grunt_123"]


def test_entity_lifecycle_result_synthesis_context_includes_enemies_departed():
    """EntityLifecycleResult.to_synthesis_context() should mention enemies departed."""
    from scripts.aeonisk.multiagent.schemas.story_events import EntityLifecycleResult

    result = EntityLifecycleResult()
    result.enemies_departed = ["enemy_grunt_abc", "enemy_raider_def"]

    context = result.to_synthesis_context()

    assert "2 enemy(ies) departed" in context


def test_scene_pivot_has_enemy_departures():
    """ScenePivot should have enemy_departures field."""
    from scripts.aeonisk.multiagent.schemas.story_events import ScenePivot

    pivot = ScenePivot(
        should_pivot=True,
        new_room="Maintenance Corridor",
        situation_change="Guards finished inspection and moved on",
        npc_departures=[],
        enemy_departures=["enemy_grunt_security1", "enemy_grunt_security2"]
    )

    assert hasattr(pivot, 'enemy_departures')
    assert len(pivot.enemy_departures) == 2


def test_scene_pivot_enemy_departures_defaults_to_empty_list():
    """ScenePivot enemy_departures should default to empty list."""
    from scripts.aeonisk.multiagent.schemas.story_events import ScenePivot

    pivot = ScenePivot(
        should_pivot=True,
        new_room="Control Room",
        situation_change="Team advances to next area"
    )

    assert pivot.enemy_departures == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
