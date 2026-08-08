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

def enemy_defeat(round, name, reason="killed"):
    return {"event_type": "enemy_defeat", "round": round, "enemy_name": name,
            "enemy_id": name, "defeat_reason": reason}

def heal(round, target_name, health=20):
    return {"event_type": "healing_applied", "round": round, "target_name": target_name,
            "target_id": target_name, "heal_type": "hp", "hp_restored": health,
            "target_state_after": {"alive": True, "status": "active", "health": health}}

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

    def test_zombie_fires_on_suppress(self):
        # Suppress is a real hostile major_action (Cast/Ritual/Aim never occur)
        ev = [cstate(1, "Vane", is_defeated=True, death_state="unconscious"),
              declare(2, "player_01", "Vane", major="Suppress")]
        assert "zombie_actor" in fired(check(ev))

    def test_zombie_silent_on_nonhostile_action(self):
        # a defeated entity may still be logged pleading/complying — not a zombie
        ev = [cstate(1, "Vane", is_defeated=True, death_state="unconscious"),
              declare(2, "player_01", "Vane", major="plead")]
        assert "zombie_actor" not in fired(check(ev))

    def test_zombie_silent_after_healing(self):
        # healing_applied is the sanctioned un-defeat: acting after a heal is fine
        ev = [cstate(1, "Vane", is_defeated=True, death_state="unconscious"),
              heal(2, "Vane"),
              combat(3, "Vane", "Grunt", dealt=9)]
        assert "zombie_actor" not in fired(check(ev))

    def test_dead_targetable_fires_on_true_death(self):
        # death is authoritative from character_state (death_state=dead), NOT from
        # combat_action's transient wound scale
        ev = [cstate(1, "Grunt", wounds=6, is_defeated=True, death_state="dead", agent="enemy"),
              combat(2, "Vane", "Grunt", dealt=9)]
        assert "dead_targetable" in fired(check(ev))

    def test_dead_targetable_fires_via_enemy_defeat(self):
        # enemies often lack character_state; enemy_defeat(killed) is authoritative
        ev = [enemy_defeat(1, "Grunt", reason="killed"),
              combat(2, "Vane", "Grunt", dealt=9)]
        assert "dead_targetable" in fired(check(ev))

    def test_dead_targetable_silent_on_unconscious(self):
        # unconscious (not dead) — a finishing coup-de-grace is legal
        ev = [cstate(1, "Grunt", health=0, wounds=3, is_defeated=True,
                     death_state="unconscious", agent="enemy"),
              combat(2, "Vane", "Grunt", dealt=9)]
        assert "dead_targetable" not in fired(check(ev))

    def test_dead_targetable_silent_same_round(self):
        # the killing blow itself is not a re-hit; only strikes AFTER death count
        ev = [cstate(2, "Grunt", wounds=6, is_defeated=True, death_state="dead", agent="enemy"),
              combat(2, "Vane", "Grunt", dealt=9)]
        assert "dead_targetable" not in fired(check(ev))

    def test_defeat_flag_internal_mismatch(self):
        # death_state unconscious but is_defeated False — self-contradictory snapshot
        ev = [cstate(1, "Vane", is_defeated=False, death_state="unconscious")]
        assert "defeat_flag_internal" in fired(check(ev))

    def test_hp_exceeds_max_is_warned(self):
        ev = [cstate(1, "Vane", health=40, max_health=26)]
        assert "hp_exceeds_max" in fired(check(ev))


def escalate(round, ids_):
    return {"event_type": "entity_lifecycle", "round": round, "npcs_escalated": list(ids_)}


class TestConfigPrisonerSpawnConfound:
    def test_declared_prisoner_spawned_armed(self):
        cfg = {"initial_enemies": [{"name": "Subdued Operative #1",
                                    "disposition": "prisoner"}]}
        ev = [spawn("g1", "Subdued Operative #1", weapons=("Pistol", "Baton"))]
        assert "config_prisoner_spawned_hostile" in fired(check(ev, cfg))

    def test_declared_prisoner_attacks_round_one(self):
        cfg = {"initial_enemies": [{"name": "Subdued Operative #1",
                                    "disposition": "prisoner"}]}
        ev = [spawn("g1", "Subdued Operative #1", weapons=()),
              combat(1, "Subdued Operative #1", "Vane", dealt=9)]
        assert "config_prisoner_spawned_hostile" in fired(check(ev, cfg))

    def test_no_config_disposition_is_silent(self):
        # ordinary hostile enemy, no prisoner intent declared -> nothing to flag
        ev = [spawn("g1", "ACG Enforcer", weapons=("Pistol",)),
              combat(1, "ACG Enforcer", "Vane", dealt=9)]
        assert "config_prisoner_spawned_hostile" not in fired(check(ev))


class TestRestrainedHostileAction:
    def test_converted_prisoner_attacks(self):
        # enemy converted to prisoner in r1, then attacks r2 with no escalation
        ev = [spawn("g1", "Operative", weapons=()),
              convert(1, ["g1"]),
              declare(2, "g1", "Operative", major="Attack")]
        assert "restrained_hostile_action" in fired(check(ev))

    def test_jailbreak_then_attack_is_silent(self):
        # prisoner (converted r1) legitimately escalates back to enemy r2, then
        # attacks r3 — this is a jailbreak, NOT a violation.
        ev = [spawn("g1", "Operative", weapons=()),
              convert(1, ["g1"]),
              escalate(2, ["g1"]),
              declare(3, "g1", "Operative", major="Attack"),
              combat(3, "Operative", "Vane", dealt=9)]
        assert "restrained_hostile_action" not in fired(check(ev))

    def test_prisoner_may_plead(self):
        # non-tactical NPC actions are always fine for a restrained entity
        ev = [spawn("g1", "Operative", weapons=()),
              convert(1, ["g1"]),
              declare(2, "g1", "Operative", major="plead")]
        assert "restrained_hostile_action" not in fired(check(ev))


class TestEconomyInvariants:
    def test_void_out_of_bounds(self):
        assert "void_out_of_bounds" in fired(check([cstate(1, "Vane", void=11)]))
        assert "void_out_of_bounds" in fired(check([cstate(1, "Vane", void=-1)]))

    def test_negative_damage(self):
        ev = [combat(1, "Vane", "Grunt", dealt=-3)]
        assert "damage_negative" in fired(check(ev))


def llmcall(agent, seq, atype="player", rnd=1):
    """An llm_call event as emitted by LLMCallLogger / EnemyFallbackLLMClient."""
    return {"event_type": "llm_call", "round": rnd, "agent_id": agent,
            "agent_type": atype, "call_sequence": seq,
            "prompt": [{"role": "user", "content": "p"}], "response": "r",
            "model": "m", "temperature": 0.7, "tokens": {"input": 1, "output": 1}}


def combat_soak(atk_id, base, soak, dealt, total=None):
    d = {"base_damage": base, "soak": soak, "dealt": dealt}
    if total is not None:
        d["total"] = total
    return {"event_type": "combat_action", "round": 1,
            "attacker": {"id": atk_id, "name": atk_id},
            "defender": {"id": "e1", "name": "Grunt"}, "damage": d}


class TestSoakArithmetic:
    """dealt must equal max(0, (total|base) - soak) on the FORMULA path (known
    attacker). Mined rule: 81/83 corpus events fit exactly; the only 2 misfits
    are DM-declared damage (attacker id 'unknown', source structured_output),
    where dealt is the DM's lawful ruling — those are skipped, not warned."""

    def test_faithful_formula_is_silent(self):
        assert "soak_arithmetic" not in fired(check([combat_soak("player_01", 19, 9, 10)]))
        # old schema: total (post-modifier) is the minuend, not base
        assert "soak_arithmetic" not in fired(check([combat_soak("player_01", 22, 10, 8, total=18)]))
        # clamp at zero
        assert "soak_arithmetic" not in fired(check([combat_soak("player_01", 5, 10, 0)]))

    def test_formula_violation_is_error(self):
        vs = check([combat_soak("player_01", 19, 9, 19)])  # soak not subtracted
        assert "soak_arithmetic" in fired(vs)
        assert any(v.invariant == "soak_arithmetic" and v.severity == "error" for v in vs)

    def test_dm_declared_damage_is_skipped(self):
        # the real corpus shape: unknown attacker, dealt is a DM ruling
        assert "soak_arithmetic" not in fired(check([combat_soak("unknown", 12, 0, 6)]))

    def test_missing_fields_are_silent(self):
        ev = {"event_type": "combat_action", "round": 1,
              "attacker": {"id": "player_01"}, "damage": {"dealt": 5}}
        assert "soak_arithmetic" not in fired(check([ev]))


class TestCallSequenceContiguity:
    """call_sequence must be unique + contiguous per agent — the replay-cache key.
    Duplicates overwrite cached calls (real data loss => ERROR); gaps mean a call
    advanced the counter without emitting an event (=> WARN)."""

    def test_silent_when_contiguous(self):
        ev = [llmcall("player_01", 0), llmcall("player_01", 1), llmcall("player_01", 2),
              llmcall("dm_01", 0, "dm"), llmcall("enemy_grunt_a", 0, "enemy"),
              llmcall("enemy_grunt_a", 1, "enemy")]
        assert "call_sequence_collision" not in fired(check(ev))
        assert "call_sequence_gap" not in fired(check(ev))

    def test_silent_when_no_llm_calls(self):
        assert "call_sequence_collision" not in fired(check(clean_session()))
        assert "call_sequence_gap" not in fired(check(clean_session()))

    def test_duplicate_sequence_is_error(self):
        # the enemy [0,0] bug: same agent, two calls both stamped 0
        ev = [llmcall("enemy_grunt_a", 0, "enemy"), llmcall("enemy_grunt_a", 0, "enemy")]
        vs = check(ev)
        assert "call_sequence_collision" in fired(vs)
        assert any(v.invariant == "call_sequence_collision" and v.severity == "error" for v in vs)

    def test_gap_is_warned(self):
        # the DM 0,2,4,... bug: counter advanced without emitting
        ev = [llmcall("dm_01", 0, "dm"), llmcall("dm_01", 2, "dm"), llmcall("dm_01", 4, "dm")]
        vs = check(ev)
        assert "call_sequence_gap" in fired(vs)
        assert all(v.severity == "warn" for v in vs if v.invariant == "call_sequence_gap")

    def test_per_agent_independent(self):
        # player_01 clean, player_02 dup — only the offender fires, tagged by entity
        ev = [llmcall("player_01", 0), llmcall("player_01", 1),
              llmcall("player_02", 0), llmcall("player_02", 0)]
        vs = [v for v in check(ev) if v.invariant == "call_sequence_collision"]
        assert len(vs) == 1
        assert vs[0].entity == "player_02"


class TestViolationShape:
    def test_violation_has_fields(self):
        v = check([cstate(1, "Vane", void=11)])[0]
        assert isinstance(v, Violation)
        assert v.invariant and v.severity in ("error", "warn")
        assert v.message
