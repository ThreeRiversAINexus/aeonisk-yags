"""TDD spec for the session-invariant checker (scripts/session_invariants.py).

Cross-event / cross-subsystem rules that unit tests on individual functions
structurally cannot see (a stun-KO'd actor still acting; a "subdued" prisoner
spawning armed; combat_action and character_state disagreeing about who's down).

Two obligations for every invariant:
  1. it FIRES on a minimal session that violates it, and
  2. it stays SILENT on a clean session (no false positives — trust is the
     whole point; a checker that cries wolf gets ignored like keyword grep did).
"""
import pytest

from scripts.session_invariants import check, Violation, ids


# --- synthetic event builders (match the real JSONL field shapes) -----------
def cstate(round, name, health=26, max_health=26, wounds=0, stuns=0,
           is_defeated=False, death_state="alive", void=3, sc=0, agent="player"):
    return {"event_type": "character_state", "round": round, "character_name": name,
            "health": health, "max_health": max_health, "wounds": wounds, "stuns": stuns,
            "is_defeated": is_defeated, "death_state": death_state,
            "void_score": void, "soulcredit": sc, "agent": agent}

def combat(round, atk, dfn, dealt=5, health_after=20, stuns_after=0, alive=True,
           did=None, wounds_after=1, status="active"):
    return {"event_type": "combat_action", "round": round,
            "attacker": {"id": atk, "name": atk}, "defender": {"id": did or dfn, "name": dfn},
            "damage": {"dealt": dealt, "damage_type": "wound"},
            "defender_state_after": {"health": health_after, "max_health": 30,
                                     "wounds": wounds_after, "stuns": stuns_after,
                                     "alive": alive, "status": status}}

def declare(round, pid, name, major="Attack", target="tgt_x"):
    return {"event_type": "action_declaration", "round": round, "player_id": pid,
            "character_name": name, "action": {"major_action": major, "target": target}}

def spawn(eid, name, weapons=("Pistol",)):
    return {"event_type": "enemy_spawn", "round": 0, "enemy_id": eid, "enemy_name": name,
            "stats": {"health": 30, "weapons": [{"name": w} for w in weapons]}}

def convert(round, ids_):
    return {"event_type": "entity_lifecycle", "round": round, "enemies_converted": list(ids_)}

def adjud(round, applied, regime="enforce"):
    return {"event_type": "post_resolution_adjudication", "round": round,
            "regime": regime, "applied": applied}

def clean_session():
    """A minimal well-formed 2-round combat that should raise zero violations."""
    return [
        {"event_type": "session_start"},
        cstate(1, "Vane", health=26, stuns=0),
        combat(1, "Vane", "Grunt", dealt=8, health_after=22, alive=True),
        cstate(1, "Grunt", health=22, agent="enemy"),
        declare(2, "player_01", "Vane"),
        combat(2, "Vane", "Grunt", dealt=9, health_after=13, alive=True),
        cstate(2, "Vane", health=26),
        cstate(2, "Grunt", health=13, agent="enemy"),
        {"event_type": "session_end"},
    ]


def fired(violations):
    return set(ids(violations))


class TestCleanSessionIsSilent:
    def test_no_violations_on_clean_session(self):
        assert check(clean_session()) == []


class TestLifeStateInvariants:
    def test_zombie_actor_via_combat(self):
        ev = [cstate(1, "Vane", health=15, stuns=12, is_defeated=True, death_state="unconscious"),
              combat(2, "Vane", "Grunt", dealt=9)]  # defeated in r1, deals damage in r2
        assert "zombie_actor" in fired(check(ev))

    def test_zombie_actor_via_declaration(self):
        ev = [cstate(1, "Vane", is_defeated=True, death_state="unconscious"),
              declare(2, "player_01", "Vane", major="Attack")]
        assert "zombie_actor" in fired(check(ev))

    def test_zombie_silent_after_revive(self):
        ev = [cstate(1, "Vane", is_defeated=True, death_state="unconscious"),
              cstate(2, "Vane", is_defeated=False, death_state="alive"),
              combat(3, "Vane", "Grunt", dealt=9)]
        assert "zombie_actor" not in fired(check(ev))

    def test_defeat_state_disagreement_dead_but_active(self):
        # past the wound-death threshold yet still reported able to act
        ev = [combat(1, "Vane", "Grunt", wounds_after=6, status="active")]
        assert "defeat_state_disagreement" in fired(check(ev))

    def test_defeat_state_disagreement_not_alive_but_active(self):
        ev = [combat(1, "Vane", "Grunt", alive=False, status="active")]
        assert "defeat_state_disagreement" in fired(check(ev))

    def test_defeat_state_silent_on_stun_ko(self):
        # a stun-KO'd defender IS alive (just unconscious) — must NOT fire here
        ev = [combat(1, "Grunt", "Vane", stuns_after=12, alive=True, status="active")]
        assert "defeat_state_disagreement" not in fired(check(ev))

    def test_dead_targetable_fires_on_true_death(self):
        ev = [combat(1, "Vane", "Grunt", dealt=20, wounds_after=6, did="g1"),
              combat(2, "Vane", "Grunt", dealt=9, wounds_after=6, did="g1")]
        assert "dead_targetable" in fired(check(ev))

    def test_dead_targetable_silent_on_unconscious(self):
        # 0 HP but wounds < 6 = unconscious, not dead; a finishing blow is legal
        ev = [combat(1, "Vane", "Grunt", dealt=20, health_after=0, wounds_after=3, did="g1"),
              combat(2, "Vane", "Grunt", dealt=9, health_after=0, wounds_after=4, did="g1")]
        assert "dead_targetable" not in fired(check(ev))

    def test_defeat_flag_internal_mismatch(self):
        # death_state unconscious but is_defeated False — self-contradictory snapshot
        ev = [cstate(1, "Vane", is_defeated=False, death_state="unconscious")]
        assert "defeat_flag_internal" in fired(check(ev))

    def test_hp_exceeds_max_is_warned(self):
        ev = [cstate(1, "Vane", health=40, max_health=26)]
        assert "hp_exceeds_max" in fired(check(ev))


class TestEntityLifecycleInvariants:
    def test_prisoner_spawned_armed(self):
        ev = [spawn("g1", "Independent Subdued Operative #1", weapons=("Pistol", "Baton"))]
        assert "prisoner_armed" in fired(check(ev))

    def test_prisoner_attacks_round_one(self):
        ev = [spawn("g1", "Subdued Operative #1", weapons=("Baton",)),
              declare(1, "g1", "Subdued Operative #1", major="Attack")]
        assert "prisoner_attacks" in fired(check(ev))

    def test_converted_npc_taking_tactical_action(self):
        # after conversion to prisoner NPC, Attack is off the NPC whitelist
        ev = [spawn("g1", "Operative", weapons=()),
              convert(1, ["g1"]),
              declare(2, "g1", "Operative", major="Attack")]
        assert "npc_tactical_action" in fired(check(ev))

    def test_unarmed_nonprisoner_is_silent(self):
        ev = [spawn("g1", "ACG Enforcer", weapons=("Pistol",))]
        assert "prisoner_armed" not in fired(check(ev))


class TestEconomyInvariants:
    def test_void_out_of_bounds(self):
        assert "void_out_of_bounds" in fired(check([cstate(1, "Vane", void=11)]))
        assert "void_out_of_bounds" in fired(check([cstate(1, "Vane", void=-1)]))

    def test_negative_damage(self):
        ev = [combat(1, "Vane", "Grunt", dealt=-3)]
        assert "damage_negative" in fired(check(ev))


class TestViolationShape:
    def test_violation_has_fields(self):
        v = check([cstate(1, "Vane", void=11)])[0]
        assert isinstance(v, Violation)
        assert v.invariant and v.severity in ("error", "warn")
        assert v.message
