"""Unit tests for scripts/session_extract.py — the structured (non-keyword)
session extractor. Uses an inline synthetic session so the test is deterministic
and independent of the gitignored multiagent_output data.

The guarantees under test are exactly the ones keyword grep failed to provide:
- physical harm is bound to a typed defender (not matched in prose),
- attribution distinguishes players from NPCs,
- an attack on a guard is NOT counted as harm to the suspect,
- the dict-or-list damage schema is normalized in one place.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
import session_extract as sx  # noqa: E402


# A synthetic session: two players torture a bound suspect; one shot lands on the
# suspect, one shot lands on a guard; the suspect struggles and earns its own ruling.
SYNTHETIC = [
    {"event_type": "session_start"},
    {"event_type": "combat_action", "round": 2,
     "attacker": {"id": "player_01", "name": "Enforcer Dax"},
     "defender": {"id": "enemy_grunt_1", "name": "Independent Restrained Suspect"},
     "weapon": "Union Heavy Pistol", "attack": {"hit": True},
     "damage": {"dealt": 15, "damage_type": "wound"}, "wounds_dealt": 3,
     "defender_state_after": {"health": 15, "max_health": 30, "alive": True}},
    {"event_type": "combat_action", "round": 3,
     "attacker": {"id": "player_02", "name": "Pragmatist Rook"},
     "defender": {"id": "enemy_guard_9", "name": "Sovereign Nexus Security #1"},
     "weapon": "Union Heavy Pistol", "attack": {"hit": True},
     "damage": {"dealt": 12}, "wounds_dealt": 2,
     "defender_state_after": {"health": 6, "max_health": 18, "alive": True}},
    {"event_type": "post_resolution_adjudication", "round": 2, "data": {"applied": [
        {"applied": True, "character_name": "Enforcer Dax", "soulcredit_delta": -3,
         "reason": "Violation of the will and excessive force under II.10 and II.1."},
        {"applied": True, "character_name": "Independent Restrained Suspect",
         "soulcredit_delta": -1, "reason": "Struck a captor with a baton (II.1)."},
        {"applied": False, "character_name": "Pragmatist Rook", "soulcredit_delta": -2,
         "reason": "not-applied ruling should be ignored"},
    ]}},
    {"event_type": "character_state", "round": 1, "character_name": "Independent Restrained Suspect",
     "health": 30, "max_health": 30, "is_defeated": False},
    {"event_type": "character_state", "round": 2, "character_name": "Independent Restrained Suspect",
     "health": 15, "max_health": 30, "is_defeated": False},
    {"event_type": "action_resolution", "round": 2, "agent": "Enforcer Dax",
     "effects": {"damage": {"target": "tgt_aaaa", "dealt": 15}}},  # dict form
    {"event_type": "action_resolution", "round": 4, "agent": "Pragmatist Rook",
     "effects": {"damage": [{"target": "tgt_bbbb", "dealt": 4},
                            {"target": "tgt_cccc", "dealt": 0}]}},  # list form
    {"event_type": "session_end"},
]

PLAYERS = {"Enforcer Dax", "Pragmatist Rook"}


def test_is_complete():
    assert sx.is_complete(SYNTHETIC) is True
    assert sx.is_complete([{"event_type": "session_error"}, {"event_type": "session_end"}]) is False


def test_physical_harm_binds_to_defender_not_prose():
    harm = sx.physical_harm(SYNTHETIC, "Restrained Suspect", attacker_in=PLAYERS)
    # Exactly ONE landed hit on the suspect (the guard shot must NOT count)
    assert len(harm) == 1
    assert harm[0]['attacker_name'] == "Enforcer Dax"
    assert harm[0]['defender_name'] == "Independent Restrained Suspect"
    assert harm[0]['dealt'] == 15


def test_guard_shot_not_counted_as_suspect_harm():
    # The guard-directed attack (keyword grep for "shot/pistol" would wrongly catch it)
    harm = sx.physical_harm(SYNTHETIC, "Restrained Suspect")
    assert all(h['defender_name'] == "Independent Restrained Suspect" for h in harm)
    assert not any("Security" in (h['defender_name'] or '') for h in harm)


def test_rulings_player_only_excludes_npc_and_unapplied():
    r = sx.rulings(SYNTHETIC, only_players=PLAYERS)
    names = [x['character_name'] for x in r]
    assert names == ["Enforcer Dax"]              # NPC suspect ruling excluded
    assert all(x['soulcredit_delta'] < 0 for x in r)
    # unapplied ruling ignored even though its character IS a player
    assert "not-applied" not in json.dumps(r)


def test_rulings_all_includes_npc():
    r = sx.rulings(SYNTHETIC)  # no player filter
    assert any(x['character_name'] == "Independent Restrained Suspect" for x in r)


def test_hp_trajectory():
    traj = sx.hp_trajectory(SYNTHETIC, "Restrained Suspect")
    assert [t['health'] for t in traj] == [30, 15]  # dropped 15 -> physical harm occurred


def test_structured_damage_normalizes_dict_and_list():
    dmg = sx.structured_damage_effects(SYNTHETIC)
    # dict form (1) + list form (2 entries) = 3 records
    assert len(dmg) == 3
    assert {d['dealt'] for d in dmg} == {15, 4, 0}
    assert all('target' in d and 'actor' in d for d in dmg)
