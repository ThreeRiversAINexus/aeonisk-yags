"""An entity that is harmed must survive into the record (#150).

Session 81125d33 shot a subdued prisoner for 19 wound damage in round one and
logged **no** `character_state` row for him in the whole session. Whether he
died is unanswerable from the authoritative oracle. All twenty-one invariants
passed and the run exited 0; it read as a clean four-round session.

The mechanism is a phase ordering. NPC removal happens in the entity-lifecycle
phase (`session.py`, `npc_departures`), the snapshot loop runs at round end, and
removal *deletes* the NPC from `npc_agents` — so an NPC harmed and removed in the
same round is gone before anything writes it down. That makes the oracle's answer
depend on survival timing, exactly backwards: the identical config on another
model recorded all three captives, purely because there they left a round later.

Enemies were fixed once already (#138) and NPCs carried the lesson in a comment
the whole time — "an entity de-escalated to prisoner vanished from the oracle at
the moment of arrest". That was the lawful outcome going unobserved. This is the
unlawful one.

## Chain replay

Rather than re-run a session to see the fix work, the recorded causal chain is
isolated: ten events from 81125d33 — round_start, the combat_action, the three
npc_departures, entity_lifecycle, the three player character_state rows — carried
verbatim into `tests/fixtures/sessions/harm_unrecorded_chain.jsonl`. The scene is
rebuilt from those events, driven through the real removal and snapshot seams,
and the resulting stream re-checked. The invariant is the oracle, so nothing here
restates the rules.

It is mode 1 (extract) widened from a value to a chain: the corpus supplies the
whole sequence, not one field, and the assertion is about what the sequence
produces.
"""

import json
from pathlib import Path

import pytest

from aeonisk.multiagent.conversion_validation import npcs_to_snapshot
from aeonisk.multiagent.session import character_state_row
from aeonisk.multiagent.shared_state import SharedState
from scripts.session_invariants import (
    ERROR, inv_duplicate_character_state, inv_harm_unrecorded,
)
from tests.factories import FakeAgent

CHAIN = Path(__file__).parent.parent / "fixtures/sessions/harm_unrecorded_chain.jsonl"

VICTIM_ID = "npc_subdued_operative_#1_8640"
VICTIM = "Subdued Operative #1"


def _chain():
    return [json.loads(line) for line in CHAIN.read_text().splitlines() if line.strip()]


def _npcs_from(chain):
    """The three captives, as they stood when the round ended.

    Their state comes from the chain itself: `defender_state_after` for the one
    that was shot, full health for the two that were not. Nothing is invented —
    if the fixture changes, so does the scene.
    """
    hurt = {}
    for e in chain:
        if e.get("event_type") == "combat_action":
            hurt[e["defender"]["id"]] = e["defender_state_after"]
    out = []
    for e in chain:
        if e.get("event_type") != "npc_departure":
            continue
        s = hurt.get(e["npc_id"], {})
        out.append(FakeAgent(
            agent_id=e["npc_id"], name=e["npc_name"],
            health=s.get("health", 20), max_health=s.get("max_health", 20),
            wounds=s.get("wounds", 0), stuns=s.get("stuns", 0)))
    return out


def _snapshot_rows(chain, npcs, *, keep_departed=True):
    """What the round-end loop writes, given this roster."""
    state = SharedState()
    state.npc_agents.extend(npcs)
    for e in chain:
        if e.get("event_type") == "npc_departure":
            state.remove_npc(e["npc_id"])

    departed = state.departed_npcs if keep_departed else None
    return [
        {"event_type": "character_state", "round": 1,
         **character_state_row(npc, None, agent="npc")}
        for npc in npcs_to_snapshot(state.npc_agents, departed)
    ]


class TestTheRecordedChainStillShowsTheBug:
    """The fixture is real data, so this is the finding, not a construction."""

    def test_the_chain_reproduces_it_in_ten_events(self):
        v = inv_harm_unrecorded(_chain(), {})

        assert [x.entity for x in v] == [VICTIM]
        assert v[0].severity == ERROR

    def test_the_victim_took_damage_and_departed_in_the_same_round(self):
        """The ordering that causes it, asserted rather than assumed."""
        chain = _chain()
        hit = next(e for e in chain if e["event_type"] == "combat_action")
        gone = next(e for e in chain
                    if e.get("event_type") == "npc_departure"
                    and e["npc_id"] == hit["defender"]["id"])

        assert hit["damage"]["dealt"] == 19
        assert hit["round"] == gone["round"] == 1
        assert gone["departure_reason"] == "entity_lifecycle_removal"

    def test_no_snapshot_names_the_victim(self):
        names = {e.get("character_name") for e in _chain()
                 if e.get("event_type") == "character_state"}

        assert VICTIM not in names
        assert names == {"Hard Vane", "Oathkeeper Sela", "Cold Tarn"}


class TestRemovalRetiresRatherThanErases:
    """`remove_npc` is the seam: it takes an entity out of play, and the record
    has to outlive that."""

    def test_a_removed_npc_is_retired_not_lost(self):
        state = SharedState()
        npc = FakeAgent(agent_id="npc_a", name="A")
        state.npc_agents.append(npc)

        assert state.remove_npc("npc_a") is True
        assert state.npc_agents == []
        assert state.departed_npcs == [npc]

    def test_removal_by_object_retires_too(self):
        """Both paths, because a caller may hold the object rather than the id."""
        state = SharedState()
        npc = FakeAgent(agent_id="npc_a", name="A")
        state.npc_agents.append(npc)

        assert state.remove_npc_object(npc) is True
        assert state.departed_npcs == [npc]

    def test_a_failed_removal_retires_nobody(self):
        state = SharedState()

        assert state.remove_npc("npc_missing") is False
        assert state.remove_npc_object(FakeAgent(agent_id="npc_other")) is False
        assert state.departed_npcs == []

    def test_the_same_npc_is_retired_once(self):
        """A double departure must not double the entity's rows."""
        state = SharedState()
        npc = FakeAgent(agent_id="npc_a", name="A")
        state.npc_agents.append(npc)
        state.remove_npc("npc_a")
        state.npc_agents.append(npc)
        state.remove_npc_object(npc)

        assert state.departed_npcs == [npc]


class TestTheSnapshotRoster:
    """`npcs_to_snapshot` — the other seam, and the one #138 got right for
    enemies."""

    def test_departed_npcs_are_included(self):
        live, gone = FakeAgent(agent_id="npc_a"), FakeAgent(agent_id="npc_b")

        assert npcs_to_snapshot([live], [gone]) == [live, gone]

    def test_an_inactive_npc_is_still_snapshotted(self):
        """The #138 half: `is_active` going False was the point at which the
        entity became worth recording, and it was the point it stopped being
        recorded."""
        npc = FakeAgent(agent_id="npc_a", is_active=False)

        assert npcs_to_snapshot([npc], []) == [npc]

    def test_an_npc_in_both_lists_appears_once(self):
        npc = FakeAgent(agent_id="npc_a")

        assert npcs_to_snapshot([npc], [npc]) == [npc]

    def test_missing_rosters_are_not_an_error(self):
        assert npcs_to_snapshot(None, None) == []


class TestReplayingTheChainThroughTheFix:
    """Drive the recorded chain through the real seams and re-check it."""

    def test_the_repaired_stream_is_clean(self):
        chain = _chain()
        repaired = chain + _snapshot_rows(chain, _npcs_from(chain))

        assert inv_harm_unrecorded(repaired, {}) == []
        assert inv_duplicate_character_state(repaired, {}) == []

    def test_the_retirement_roster_is_what_fixes_it(self):
        """Falsifiability: rebuild the scene identically but drop the departed
        roster, and the violation comes straight back. Without this the test
        above would pass on any reconstruction that merely mentioned the victim.
        """
        chain = _chain()
        without = chain + _snapshot_rows(chain, _npcs_from(chain),
                                         keep_departed=False)

        assert [v.entity for v in inv_harm_unrecorded(without, {})] == [VICTIM]

    def test_the_recovered_row_carries_the_harm(self):
        """Presence is not the point — the wound is."""
        chain = _chain()
        row = next(r for r in _snapshot_rows(chain, _npcs_from(chain))
                   if r["character_name"] == VICTIM)

        assert (row["health"], row["max_health"]) == (1, 20)
        assert row["wounds"] == 3
        assert row["death_state"] == "alive"
        assert row["agent"] == "npc"

    def test_the_unharmed_captives_are_recorded_too(self):
        chain = _chain()
        rows = {r["character_name"]: r for r in _snapshot_rows(chain, _npcs_from(chain))}

        assert set(rows) == {VICTIM, "Subdued Operative #2", "Subdued Operative #3"}
        assert rows["Subdued Operative #2"]["wounds"] == 0


class TestTheInvariantItself:
    """It has to be able to stay quiet, and it has to be able to fire."""

    def test_a_recorded_victim_does_not_fire(self):
        chain = _chain() + [{"event_type": "character_state", "round": 1,
                             "character_id": VICTIM_ID, "character_name": VICTIM,
                             "health": 1, "wounds": 3, "death_state": "alive"}]

        assert inv_harm_unrecorded(chain, {}) == []

    def test_matching_on_id_alone_is_enough(self):
        """Prose renames an entity between phases more often than it should;
        identity is the id."""
        chain = _chain() + [{"event_type": "character_state", "round": 1,
                             "character_id": VICTIM_ID,
                             "character_name": "the operative"}]

        assert inv_harm_unrecorded(chain, {}) == []

    def test_a_miss_is_not_harm(self):
        chain = [e for e in _chain() if e.get("event_type") != "combat_action"]
        chain.append({"event_type": "combat_action", "round": 1,
                      "attacker": {"id": "player_01", "name": "Hard Vane"},
                      "defender": {"id": VICTIM_ID, "name": VICTIM},
                      "damage": {"dealt": 0}})

        assert inv_harm_unrecorded(chain, {}) == []

    def test_a_session_with_no_snapshots_at_all_is_left_to_other_checks(self):
        """Zero rows is a louder failure than a missing one, and flagging every
        defender in a truncated extract would bury it."""
        chain = [e for e in _chain() if e.get("event_type") != "character_state"]

        assert inv_harm_unrecorded(chain, {}) == []

    def test_environmental_objects_are_not_entities(self):
        chain = [e for e in _chain() if e.get("event_type") != "combat_action"]
        chain.append({"event_type": "combat_action", "round": 2,
                      "attacker": {"id": "player_01", "name": "Hard Vane"},
                      "defender": {"id": "env_crate_01", "name": "Supply Crate"},
                      "damage": {"dealt": 12}})

        assert inv_harm_unrecorded(chain, {}) == []


class TestDuplicateRowsAreTheMirrorFailure:
    """The retirement roster's own risk: an entity that moves between rosters
    (an escalating NPC keeps its `agent_id` by design) could be written twice."""

    def test_two_rows_for_one_entity_in_one_round_is_an_error(self):
        row = {"event_type": "character_state", "round": 1,
               "character_id": VICTIM_ID, "character_name": VICTIM}

        v = inv_duplicate_character_state([row, dict(row)], {})

        assert [x.entity for x in v] == [VICTIM_ID]
        assert v[0].severity == ERROR

    def test_the_same_entity_across_rounds_is_ordinary(self):
        rows = [{"event_type": "character_state", "round": r,
                 "character_id": VICTIM_ID, "character_name": VICTIM}
                for r in (1, 2, 3)]

        assert inv_duplicate_character_state(rows, {}) == []

    def test_the_recorded_chain_has_none(self):
        assert inv_duplicate_character_state(_chain(), {}) == []
