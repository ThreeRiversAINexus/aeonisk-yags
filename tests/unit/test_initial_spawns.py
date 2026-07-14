"""TDD spec for build_initial_spawns — the config -> spawn-object conversion.

The execution-probe spawn confound: a config `initial_enemies` entry that
declares `disposition: prisoner` (a subdued captive) was being built as a fully
armed Grunt combatant, because the initial_enemies loop never read `disposition`
(dm.py:2184) while the initial_npcs loop right below it did. All 19 execution
sessions spawned their "kneeling prisoners" armed and let them alpha-strike the
party in round 1, contaminating the probe.

The fix: a non-hostile disposition (prisoner / friendly / neutral) on an
initial_enemies entry means it is NOT a hostile combatant — it routes to the NPC
spawn path (disarmed, correct entity_type), exactly as an initial_npcs entry
would. Genuinely hostile entries (no disposition, or disposition hostile) stay
EnemySpawns. This is the single conversion point, tested here in isolation.
"""
import pytest

from scripts.aeonisk.multiagent.initial_spawns import build_initial_spawns
from scripts.aeonisk.multiagent.schemas.story_events import EnemySpawn, NPCSpawn


def test_prisoner_enemy_routes_to_npc_path_disarmed():
    enemies, npcs = build_initial_spawns(
        [{"name": "Subdued Operative #1", "template": "grunt",
          "disposition": "prisoner", "position": "Near-PC"}], [])
    assert enemies == []                      # NOT a hostile combatant
    assert len(npcs) == 1
    p = npcs[0]
    assert isinstance(p, NPCSpawn)
    assert p.entity_type == "prisoner"
    assert p.disposition == "prisoner"
    assert p.weapons == []                    # disarmed — no round-1 alpha strike
    assert p.name == "Subdued Operative #1"


def test_neutral_civilian_routes_to_npc_path():
    # "Frightened Dockworker" — a bystander, not an armed Grunt
    enemies, npcs = build_initial_spawns(
        [{"name": "Frightened Dockworker", "template": "grunt",
          "disposition": "neutral", "position": "Near-PC"}], [])
    assert enemies == []
    assert npcs[0].entity_type == "neutral" and npcs[0].disposition == "neutral"


def test_friendly_routes_to_ally():
    _, npcs = build_initial_spawns(
        [{"name": "Sympathetic Guard", "disposition": "friendly"}], [])
    assert npcs[0].entity_type == "ally" and npcs[0].disposition == "friendly"


def test_hostile_enemy_stays_enemy():
    enemies, npcs = build_initial_spawns(
        [{"name": "ACG Enforcer", "template": "grunt", "faction": "ACG",
          "disposition": "hostile", "position": "Far-Enemy"}], [])
    assert npcs == []
    assert len(enemies) == 1 and isinstance(enemies[0], EnemySpawn)


def test_no_disposition_stays_enemy():
    enemies, npcs = build_initial_spawns(
        [{"name": "Nameless Thug", "template": "grunt"}], [])
    assert npcs == [] and len(enemies) == 1


def test_initial_npcs_still_become_npcs():
    enemies, npcs = build_initial_spawns(
        [], [{"name": "Dock Witness", "faction": "Independent",
              "entity_type": "neutral", "disposition": "fearful",
              "description": "A trembling witness who saw the whole thing happen."}])
    assert enemies == [] and len(npcs) == 1 and npcs[0].name == "Dock Witness"


def test_count_expands_into_multiple_prisoners():
    _, npcs = build_initial_spawns(
        [{"name": "Subdued Operative", "disposition": "prisoner", "count": 3}], [])
    assert len(npcs) == 3
    assert all(n.entity_type == "prisoner" and n.weapons == [] for n in npcs)
    assert len({n.name for n in npcs}) == 3    # distinct names


def test_routed_prisoner_is_schema_valid():
    # the whole point of routing through NPCSpawn is that pydantic validates it
    _, npcs = build_initial_spawns(
        [{"name": "Subdued Operative #1", "disposition": "prisoner"}], [])
    assert len(npcs[0].description) >= 20      # NPCSpawn min_length contract
    # re-validate by round-tripping through the model
    NPCSpawn(**npcs[0].model_dump())


def test_mixed_batch_partitions_correctly():
    enemies, npcs = build_initial_spawns(
        [{"name": "Subdued Operative #1", "disposition": "prisoner"},
         {"name": "ACG Enforcer", "faction": "ACG", "disposition": "hostile"},
         {"name": "Frightened Dockworker", "disposition": "neutral"}], [])
    assert len(enemies) == 1 and enemies[0].archetype == "ACG Enforcer"
    assert {n.entity_type for n in npcs} == {"prisoner", "neutral"}
