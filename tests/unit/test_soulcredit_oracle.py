"""The Soulcredit in the oracle must be the Soulcredit the engine applied (#153).

`character_state` is the authoritative life-state oracle, and for the one field
the ethics work is built on it was a round behind in every session. Ten of the
twelve corpus sessions carrying both `end_state_snapshot` and player rows
disagreed, always by exactly the final round's applied change.

Walking `3de9e609`: Hard Vane executes three bound captives in round 1 and the
magistrate applies `-1 → -4` under Articles II.1 and IV.3. The round-1 row says
**-1**. Round 2 he stands down, `-4 → -3`; the round-2 row says **-4**. Read the
oracle literally and a player shoots three kneeling prisoners and loses nothing
for it that round. Health in those same rows is correct — the prisoners show
8/20 with 2 wounds in the round they were shot. Only Soulcredit lagged.

Two stores caused it. Post-resolution adjudication writes
`mechanics.soulcredit_states`; the snapshot read `player.character_state.soulcredit`,
a cache refreshed when the player *receives its resolution* — before the
post-resolution ENFORCE pass runs. Hence exactly one round of lag, and the last
round's judgment landing in no row at all.

`character_state_row` already reads the ledger, and its docstring says it exists
"so the three loops cannot drift apart". Enemies and NPCs went through it.
Players — the only entities that have a Soulcredit — did not.
"""

import json
from pathlib import Path

import pytest

from aeonisk.multiagent.session import (
    character_state_row, entity_soulcredit, player_state_row,
)
from scripts.session_invariants import ERROR, _body, inv_soulcredit_oracle_lag
from tests.factories import FakeAgent, FakeCharacterState

CHAIN = Path(__file__).parent.parent / "fixtures/sessions/soulcredit_lag_chain.jsonl"


class FakeLedger:
    """The mechanics engine's Soulcredit store, and nothing else.

    A real `SoulcreditState` is a dataclass with a `.score`; that is the whole
    surface the snapshot reads, so this is the seam and not a stand-in for it.
    """

    def __init__(self, **scores):
        self.soulcredit_states = {k: type("S", (), {"score": v})() for k, v in scores.items()}
        self.conditions = {}


def _chain():
    return [json.loads(l) for l in CHAIN.read_text().splitlines() if l.strip()]


def _player(cached_sc, **kw):
    """A player whose cached Soulcredit is stale, which is the normal case at
    snapshot time — the cache is written a phase earlier than the judgment."""
    char = FakeCharacterState(name="Hard Vane", soulcredit=cached_sc, void_score=3)
    return FakeAgent(agent_id="player_01", character_state=char, **kw)


class TestTheRecordedChainStillShowsTheBug:
    """Real rows out of 3de9e609, so this is the finding rather than a
    construction."""

    def test_the_final_row_disagrees_with_the_end_state(self):
        v = inv_soulcredit_oracle_lag(_chain(), {})

        assert [x.entity for x in v] == ["player_02"]
        assert v[0].severity == ERROR
        assert "5" in v[0].message and "4" in v[0].message

    def test_the_lag_is_exactly_one_round_of_judgment(self):
        """Each row carries the value from before its own round's adjudication."""
        rows = [e for e in _chain() if e["event_type"] == "character_state"]

        assert [(e["round"], e["soulcredit"]) for e in rows] == [(1, 2), (2, 3), (3, 4)]

    def test_the_end_state_knows_the_true_score(self):
        """`end_state_snapshot` syncs from the ledger at session end, which is
        why it is right and the rows are not — and why this is checkable.

        Read through `_body`: this event nests its payload under `data` while
        the `character_state` rows beside it are flat, which is exactly the
        two-shape trap the standing rule warns about.
        """
        end = _body(next(e for e in _chain()
                         if e["event_type"] == "end_state_snapshot"))

        assert end["state_summary"]["soulcredit_states"]["player_02"]["score"] == 5


class TestThePlayerRowReadsTheLedger:

    def test_the_ledger_wins_over_the_cache(self):
        row = player_state_row(_player(cached_sc=-1), FakeLedger(player_01=-4))

        assert row["soulcredit"] == -4

    def test_it_wins_in_the_other_direction_too(self):
        """Not 'prefer the smaller number' — prefer the authority."""
        row = player_state_row(_player(cached_sc=-4), FakeLedger(player_01=2))

        assert row["soulcredit"] == 2

    def test_an_unjudged_player_reports_zero_not_the_cache(self):
        """`entity_soulcredit` never mints a ledger entry, so a player nobody
        has judged reads 0 — and the seeding at session start means this shape
        does not occur in a real session."""
        row = player_state_row(_player(cached_sc=7), FakeLedger())

        assert row["soulcredit"] == 0

    def test_no_mechanics_engine_is_not_a_crash(self):
        assert player_state_row(_player(cached_sc=-1), None)["soulcredit"] == 0


class TestTheRestOfTheRowIsUnchanged:
    """The regression risk: players keep name, Void and economy on
    `character_state`, which is why they could not go through
    `character_state_row` unchanged in the first place."""

    def test_the_name_comes_from_character_state(self):
        row = player_state_row(_player(cached_sc=0), FakeLedger(player_01=0))

        assert row["character_name"] == "Hard Vane"

    def test_void_still_comes_from_the_cache(self):
        """Deliberate: Void is applied during resolution, before the cache is
        refreshed, so the cache is current. Measured, not assumed — 1 of 236
        corpus sessions disagrees on Void against 10 of 12 on Soulcredit."""
        row = player_state_row(_player(cached_sc=0), FakeLedger(player_01=0))

        assert row["void_score"] == 3

    def test_life_state_comes_from_the_agent(self):
        p = _player(cached_sc=0, health=8, max_health=26, wounds=2, stuns=1)

        row = player_state_row(p, FakeLedger(player_01=0))

        assert (row["health"], row["max_health"]) == (8, 26)
        assert (row["wounds"], row["stuns"]) == (2, 1)
        assert row["death_state"] == "alive"
        assert row["agent"] == "player"

    def test_the_economy_is_carried(self):
        p = _player(cached_sc=0)
        p.character_state.energy_purse = _FakePurse()

        row = player_state_row(p, FakeLedger(player_01=0))

        assert row["energy"] == {"breath": 10, "drip": 4, "grain": 0,
                                 "spark": 0, "hollow": 0}
        assert row["seeds"] == {"raw": 1, "attuned": 0, "hollow": 0}

    def test_a_player_without_a_purse_reports_empty_not_missing(self):
        row = player_state_row(_player(cached_sc=0), FakeLedger(player_01=0))

        assert row["energy"] == {} and row["seeds"] == {}

    def test_it_agrees_with_the_shared_row_on_every_shared_field(self):
        """The point of the helper: no field may drift between the two paths."""
        p, led = _player(cached_sc=-1), FakeLedger(player_01=-4)

        shared = character_state_row(p, led, agent="player")
        mine = player_state_row(p, led)

        assert {k: mine[k] for k in shared if k not in
                ("character_name", "void_score")} == {
                k: v for k, v in shared.items() if k not in
                ("character_name", "void_score")}


class TestTheInvariant:
    """It has to be able to stay quiet, and it has to be able to fire."""

    def test_agreement_is_silent(self):
        chain = [e for e in _chain() if e["event_type"] != "character_state"]
        chain.append({"event_type": "character_state", "round": 3,
                      "character_id": "player_02", "character_name": "Sela",
                      "soulcredit": 5})

        assert inv_soulcredit_oracle_lag(chain, {}) == []

    def test_only_the_final_row_is_judged(self):
        """Earlier rounds legitimately differ from the end state; flagging them
        would report the same defect three times and bury the one that counts."""
        chain = _chain() + [{"event_type": "character_state", "round": 4,
                             "character_id": "player_02", "soulcredit": 5}]

        assert inv_soulcredit_oracle_lag(chain, {}) == []

    def test_a_session_without_an_end_state_is_left_alone(self):
        chain = [e for e in _chain() if e["event_type"] != "end_state_snapshot"]

        assert inv_soulcredit_oracle_lag(chain, {}) == []

    def test_an_entity_the_end_state_never_names_is_not_invented(self):
        chain = _chain() + [{"event_type": "character_state", "round": 3,
                             "character_id": "npc_07", "soulcredit": -2}]

        assert [x.entity for x in inv_soulcredit_oracle_lag(chain, {})] == ["player_02"]

    def test_a_missing_soulcredit_field_is_not_a_disagreement(self):
        """Enemy and NPC rows predating the ledger carry no score; absence is
        not a wrong answer."""
        chain = [e for e in _chain() if e["event_type"] != "character_state"]
        chain.append({"event_type": "character_state", "round": 3,
                      "character_id": "player_02"})

        assert inv_soulcredit_oracle_lag(chain, {}) == []


class _FakePurse:
    breath, drip, grain, spark, hollow = 10, 4, 0, 0, 0

    def count_seeds(self, seed_type):
        return 1 if getattr(seed_type, "name", str(seed_type)).upper().endswith("RAW") else 0
