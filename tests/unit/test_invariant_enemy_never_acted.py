"""A mute opposition must not read as a clean session (#136).

`agent_id` leaked from `extra_params` into `messages.create()`, so every enemy
tactical declaration raised and returned None. Both enemies in session 9e9ad880
were silent for four rounds; the run exited 0 and every other invariant passed.
The log read as an ordinary game in which nobody happened to fight back.

That shape is worse than a crash. A violence probe whose opposition cannot act
still looks like a probe, and the restraint it appears to measure is an artefact
of the harness — the exact confound the always-on tactical rule exists to
prevent. The bug passed through two smoke runs before anyone read the enemy
lines.

The load-bearing half is the opportunity guard. Silence alone is not a defect:
two corpus sessions spawn enemies too late to ever declare, and flagging those
would make the check noise.
"""

import pytest

from scripts.session_invariants import ERROR, inv_enemy_never_acted


def spawn(enemy_id="enemy_01", round_num=0):
    return {"event_type": "enemy_spawn", "enemy_id": enemy_id, "round": round_num,
            "enemy_name": "Threshold Acolyte", "stats": {"health": 40}}


def round_start(n):
    return {"event_type": "round_start", "round": n}


def enemy_call(enemy_id="enemy_01"):
    return {"event_type": "llm_call", "agent_type": "enemy", "agent_id": enemy_id,
            "call_sequence": 0, "prompt": "p", "response": "r"}


def enemy_attack(enemy_id="enemy_01"):
    return {"event_type": "combat_action", "round": 1,
            "attacker": {"id": enemy_id, "name": "Threshold Acolyte"},
            "defender": {"id": "player_01", "name": "Corin"}}


def fired(events, cfg=None):
    return [v.invariant for v in inv_enemy_never_acted(events, cfg or {})]


class TestTheMuteSession:

    def test_the_9e9ad880_shape_is_caught(self):
        """Two enemies at session start, four rounds, no enemy call at all."""
        events = [spawn("enemy_boss_01"), spawn("enemy_void_cultist_01")]
        events += [round_start(n) for n in (1, 2, 3, 4)]
        events += [
            {"event_type": "llm_call", "agent_type": "dm"},
            {"event_type": "llm_call", "agent_type": "player"},
        ]

        assert fired(events) == ["enemy_never_acted"]

    def test_severity_is_error(self):
        events = [spawn(), round_start(1), round_start(2)]

        assert inv_enemy_never_acted(events, {})[0].severity == ERROR


class TestItStaysQuietWhenItShould:

    def test_an_enemy_that_spoke_is_fine(self):
        events = [spawn(), round_start(1), round_start(2), enemy_call()]

        assert fired(events) == []

    def test_an_enemy_that_attacked_is_fine(self):
        """Replay and scripted runs may not log an enemy llm_call, but an
        attack is unambiguous evidence the enemy acted."""
        events = [spawn(), round_start(1), round_start(2), enemy_attack()]

        assert fired(events) == []

    def test_spawned_in_the_final_round(self):
        """ea966861: five enemies spawn at round 6 of 6 and never get a
        declaration phase. A real corpus session, and not a defect."""
        events = [round_start(n) for n in range(1, 7)] + [spawn(round_num=6)]

        assert fired(events) == []

    def test_spawned_after_the_last_round(self):
        """e94320fb: spawn recorded at round 7, last round_start is 6."""
        events = [round_start(n) for n in range(1, 7)] + [spawn(round_num=7)]

        assert fired(events) == []

    def test_no_enemies_at_all(self):
        assert fired([round_start(1), round_start(2)]) == []

    def test_no_rounds_ran(self):
        assert fired([spawn()]) == []

    def test_enemy_agents_explicitly_disabled(self):
        """Silence is the configured behaviour, not a defect."""
        events = [spawn(), round_start(1), round_start(2)]

        assert fired(events, {"enemy_agents_enabled": False}) == []


class TestOnTheRealSessions:
    """Against the two recorded sessions this was written from."""

    @pytest.mark.parametrize("path,expected", [
        ("multiagent_output/transmedia/"
         "session_9e9ad880-c33c-4a2b-8a2e-9d3157ff57de.jsonl", True),
    ])
    def test_recorded_mute_session_fires(self, path, expected):
        import os
        if not os.path.exists(path):
            pytest.skip("corpus session not present")
        from scripts.session_invariants import load
        assert bool(fired(load(path))) is expected
