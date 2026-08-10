"""Typed extractors that turn corpus events into pure-function inputs.

Deliberately corpus-free, like `test_session_extract.py`: every event here is
synthetic, so these pass on a machine that has never run a session. The
gitignored output directories get cleared; a test that needs them is a test that
breaks when someone tidies up.

The extractors feed three different jobs, and the distinction drives the design:

* **oracle rows** — `ko_check` logs every input AND every output, including the
  injected `roll`, so the function's own recorded answer is the expected value.
  Nothing has to be assumed.
* **joint tuples** — real co-occurring `(health, wounds, stuns)`, which is what
  the damage functions actually consume. `schema_mine` gives per-field marginals
  and those are a different thing.
* **provenance** — which engine produced a sample. 37% of sessions were recorded
  from a `-dirty` tree, and one is worth less than the other.
"""

import pytest

from scripts.session_extract import (
    body_states, damage_applications, healing_applications, ko_check_rows,
    provenance,
)


def ko(stuns=0, wounds=0, health_attr=3, roll=10, dc=20, total=16,
       can_act=False, status="unconscious", **kw):
    return dict({"event_type": "ko_check", "round": 1, "agent_id": "player_01",
                 "name": "Nera", "side": "player", "stuns": stuns,
                 "wounds": wounds, "health_attr": health_attr, "roll": roll,
                 "dc": dc, "total": total, "can_act": can_act,
                 "status": status}, **kw)


def cstate(health=26, wounds=0, stuns=0, **kw):
    return dict({"event_type": "character_state", "round": 1,
                 "data": {"character_id": "player_01", "character_name": "Nera",
                          "health": health, "max_health": 26, "wounds": wounds,
                          "stuns": stuns, "void_score": 2, "soulcredit": 0,
                          "is_defeated": False, "death_state": "alive",
                          "agent": "player"}}, **kw)


def combat(dealt=10, damage_type="wound", after=None, wounds_dealt=2, **kw):
    return dict({"event_type": "combat_action", "round": 1,
                 "data": {"attacker": {"id": "player_01", "name": "Nera"},
                          "defender": {"id": "enemy_boss_01", "name": "Ysolde"},
                          "weapon": "Union Heavy Pistol",
                          "attack": {"hit": True},
                          "damage": {"dealt": dealt, "damage_type": damage_type},
                          "wounds_dealt": wounds_dealt,
                          "defender_state_after": after if after is not None else
                          {"health": 16, "max_health": 26, "wounds": 2,
                           "stuns": 0, "alive": True}}}, **kw)


def heal(heal_type="hp", amount=5, after=None, **kw):
    return dict({"event_type": "healing_applied", "round": 1,
                 "data": {"target_id": "npc_medic", "target_name": "Lyra",
                          "heal_type": heal_type, "amount": amount,
                          "hp_restored": 5, "stun_removed": 0,
                          "wounds_reduced": 0,
                          "target_state_after": after if after is not None else
                          {"health": 12, "max_health": 12, "wounds": 0,
                           "stuns": 0, "alive": True}}}, **kw)


class TestKOCheckRows:
    """The gold standard: inputs and outputs both recorded.

    Eight events corpus-wide, and worth more than the thousands that log only
    one side, because nothing about the expected value is invented.
    """

    def test_carries_every_input(self):
        row = ko_check_rows([ko(stuns=10, wounds=3, health_attr=3, roll=8)])[0]

        assert (row["stuns"], row["wounds"], row["health_attr"], row["roll"]) == \
            (10, 3, 3, 8)

    def test_carries_every_logged_output(self):
        row = ko_check_rows([ko(dc=40, total=14, can_act=False,
                                status="unconscious")])[0]

        assert (row["dc"], row["total"], row["can_act"], row["status"]) == \
            (40, 14, False, "unconscious")

    def test_reads_flat_events(self):
        """ko_check is written flat, not nested under `data` like most events."""
        assert len(ko_check_rows([ko()])) == 1

    def test_skips_rows_missing_an_input(self):
        """A row without `roll` cannot be replayed deterministically."""
        incomplete = ko()
        del incomplete["roll"]

        assert ko_check_rows([incomplete]) == []

    def test_ignores_other_events(self):
        assert ko_check_rows([cstate(), combat(), heal()]) == []


class TestBodyStates:

    def test_yields_the_joint_tuple(self):
        row = body_states([cstate(health=20, wounds=3, stuns=4)])[0]

        assert (row["health"], row["wounds"], row["stuns"]) == (20, 3, 4)

    def test_keeps_none_stuns_distinct_from_zero(self):
        """Historical sessions never logged `stuns`; None is 'unknown', not 0,
        and collapsing them would invent data that was never recorded."""
        row = body_states([cstate(stuns=None)])[0]

        assert row["stuns"] is None

    def test_carries_the_entity_kind(self):
        assert body_states([cstate()])[0]["agent"] == "player"

    def test_carries_death_state_for_oracle_use(self):
        """`derive_death_state` can be checked against what was logged."""
        row = body_states([cstate()])[0]

        assert row["death_state"] == "alive" and row["is_defeated"] is False


class TestDamageApplications:

    def test_yields_dealt_and_type(self):
        row = damage_applications([combat(dealt=12, damage_type="stun")])[0]

        assert (row["dealt"], row["damage_type"]) == (12, "stun")

    def test_back_derives_the_pre_state(self):
        """`combat_action` logs only `defender_state_after`, so the input state
        has to be recovered: pre.wounds = after.wounds - wounds_dealt, and
        pre.health = after.health + dealt. Same derivation mechanics_replay.py
        already uses."""
        row = damage_applications([combat(
            dealt=10, wounds_dealt=2,
            after={"health": 16, "max_health": 26, "wounds": 2, "stuns": 0})])[0]

        assert row["pre"]["wounds"] == 0
        assert row["pre"]["health"] == 26

    def test_null_damage_type_is_preserved_not_defaulted(self):
        """80 real events carry `damage_type: null`. Substituting a default here
        would hide whatever the damage functions do with it."""
        row = damage_applications([combat(damage_type=None)])[0]

        assert row["damage_type"] is None

    def test_skips_events_with_no_damage_recorded(self):
        assert damage_applications([combat(dealt=None)]) == []


class TestHealingApplications:

    def test_yields_type_and_amount(self):
        row = healing_applications([heal(heal_type="stun", amount=3)])[0]

        assert (row["heal_type"], row["amount"]) == ("stun", 3)

    def test_carries_the_logged_after_state(self):
        row = healing_applications([heal(
            after={"health": 12, "max_health": 12, "wounds": 1, "stuns": 2})])[0]

        assert row["after"]["wounds"] == 1 and row["after"]["stuns"] == 2

    def test_tolerates_an_after_state_without_stuns(self):
        """Real rows omit `stuns` entirely."""
        row = healing_applications([heal(
            after={"health": 12, "max_health": 12, "wounds": 0})])[0]

        assert row["after"].get("stuns") is None


class TestProvenance:
    """A sample outlives the session file it came from, so it has to carry its
    own origin — the output directories are gitignored and get cleared."""

    def start(self, commit="c50e2b3", session="abc"):
        return {"event_type": "session_start", "session": session,
                "git_commit": commit, "config": {}}

    def test_reads_commit_and_session(self):
        p = provenance([self.start(commit="c50e2b3", session="abc")])

        assert p["git_commit"] == "c50e2b3" and p["session"] == "abc"

    def test_flags_a_dirty_tree(self):
        """`-dirty` means uncommitted changes: the commit does not identify the
        code that produced the sample."""
        p = provenance([self.start(commit="54243cd-dirty")])

        assert p["dirty"] is True and p["git_commit"] == "54243cd"

    def test_clean_tree_is_not_dirty(self):
        assert provenance([self.start(commit="c50e2b3")])["dirty"] is False

    def test_missing_session_start_is_not_an_error(self):
        """Fixtures are round-range extracts; some have no session_start."""
        p = provenance([cstate()])

        assert p["git_commit"] is None and p["dirty"] is False
