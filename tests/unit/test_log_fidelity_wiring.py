"""The oracle must fire through the real wiring, not just in isolation.

The plan's acceptance criterion, and the point of the whole exercise: a
telemetry check that cannot fail is exactly what this work exists to eliminate.
So these tests break a writer on purpose — reinstating the hardcoded
`soulcredit=0` that shipped as part of #80's fallout — and assert the oracle
reports it end to end: buffered row -> comparison -> WARNING -> typed event ->
invariant ERROR.
"""

import json

import pytest

from scripts.aeonisk.multiagent.mechanics import JSONLLogger
from scripts.aeonisk.multiagent.session import SelfPlayingSession
from scripts.session_invariants import ERROR, inv_log_fidelity


class Entity:
    def __init__(self, agent_id, name, health=20, wounds=0, stuns=0,
                 void_score=0, is_active=True):
        self.agent_id = agent_id
        self.name = name
        self.health = health
        self.max_health = 20
        self.wounds = wounds
        self.stuns = stuns
        self.void_score = void_score
        self.is_active = is_active


class Ledger:
    def __init__(self, score):
        self.score = score
        self.history = []


class Mechanics:
    """Minimal stand-in exposing what the fidelity hook touches."""

    def __init__(self, logger, current_round=1, **scores):
        self.jsonl_logger = logger
        self.current_round = current_round
        self.soulcredit_states = {k: Ledger(v) for k, v in scores.items()}

    def character_rows_for_round(self, round_num):
        return self.jsonl_logger.character_rows_for_round(round_num)


class SharedState:
    def __init__(self, npcs=()):
        self.npc_agents = list(npcs)


class EnemyCombat:
    def __init__(self, enemies=()):
        self.enemy_agents = list(enemies)


@pytest.fixture
def logger(tmp_path):
    return JSONLLogger("wiring-test", str(tmp_path))


def make_session(shared_state, enemy_combat):
    session = SelfPlayingSession.__new__(SelfPlayingSession)
    session.shared_state = shared_state
    session.enemy_combat = enemy_combat
    return session


def emitted_events(logger):
    if not logger.log_file.exists():
        return []
    out = []
    for line in logger.log_file.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def log_row(logger, entity, round_num=1, agent="enemy", **overrides):
    fields = dict(
        round_num=round_num,
        character_id=entity.agent_id,
        character_name=entity.name,
        health=entity.health,
        max_health=entity.max_health,
        wounds=entity.wounds,
        void_score=entity.void_score,
        soulcredit=0,
        position="Near-Enemy",
        is_defeated=False,
        death_state="alive",
        stuns=entity.stuns,
        agent=agent,
    )
    fields.update(overrides)
    logger.log_character_state(**fields)


class TestTheOracleFiresThroughTheRealWiring:

    def test_hardcoded_soulcredit_is_caught(self, logger):
        """Reinstate the exact bug from #80's fallout and prove it is reported."""
        boss = Entity("enemy_boss_1", "Matron Ysolde Xalith")
        mechanics = Mechanics(logger, enemy_boss_1=-8)
        log_row(logger, boss, soulcredit=0)          # <- the writer bug

        session = make_session(SharedState(), EnemyCombat([boss]))
        session._check_log_fidelity(mechanics, player_agents=[])

        events = [e for e in emitted_events(logger)
                  if e.get("event_type") == "log_fidelity_divergence"]
        assert len(events) == 1, "the oracle did not fire on a divergent row"

        divergences = events[0]["data"]["divergences"]
        assert any(d["field"] == "soulcredit" and d["expected"] == -8
                   and d["logged"] == 0 for d in divergences)

    def test_the_emitted_event_trips_the_invariant(self, logger):
        """Runtime warns; the corpus gate must ERROR."""
        boss = Entity("enemy_boss_1", "Matron Ysolde Xalith")
        mechanics = Mechanics(logger, enemy_boss_1=-8)
        log_row(logger, boss, soulcredit=0)
        make_session(SharedState(), EnemyCombat([boss]))._check_log_fidelity(
            mechanics, player_agents=[])

        violations = inv_log_fidelity(emitted_events(logger), {})

        assert violations and violations[0].severity == ERROR
        assert "soulcredit" in violations[0].message

    def test_missing_npc_rows_are_caught(self, logger):
        """#89: NPCs alive in the engine, absent from the log."""
        seen = Entity("enemy_1", "Void Cultist")
        unlogged = Entity("npc_1", "Kneeling Cultist")
        mechanics = Mechanics(logger)
        log_row(logger, seen)                        # only the enemy is written

        session = make_session(SharedState([unlogged]), EnemyCombat([seen]))
        session._check_log_fidelity(mechanics, player_agents=[])

        divergences = [e for e in emitted_events(logger)
                       if e.get("event_type") == "log_fidelity_divergence"]
        kinds = {d["kind"] for d in divergences[0]["data"]["divergences"]}

        assert "missing_row" in kinds

    def test_a_faithful_round_emits_nothing(self, logger):
        """It must not cry wolf — otherwise the warning becomes noise."""
        boss = Entity("enemy_boss_1", "Matron", health=12, wounds=2)
        mechanics = Mechanics(logger, enemy_boss_1=-3)
        log_row(logger, boss, soulcredit=-3, health=12, wounds=2)

        session = make_session(SharedState(), EnemyCombat([boss]))
        session._check_log_fidelity(mechanics, player_agents=[])

        assert [e for e in emitted_events(logger)
                if e.get("event_type") == "log_fidelity_divergence"] == []

    def test_no_rows_logged_is_a_noop(self, logger):
        """Rounds that log nothing (setup phases) must not fabricate findings."""
        mechanics = Mechanics(logger)
        session = make_session(SharedState(), EnemyCombat([Entity("e1", "X")]))

        session._check_log_fidelity(mechanics, player_agents=[])

        assert [e for e in emitted_events(logger)
                if e.get("event_type") == "log_fidelity_divergence"] == []

    def test_a_broken_oracle_cannot_break_the_session(self, logger):
        """Telemetry must never gate play."""
        class Exploding(Mechanics):
            def character_rows_for_round(self, round_num):
                raise RuntimeError("boom")

        session = make_session(SharedState(), EnemyCombat())

        session._check_log_fidelity(Exploding(logger), player_agents=[])  # must not raise


class TestRowBuffer:

    def test_buffer_holds_what_was_written(self, logger):
        entity = Entity("e1", "X")
        log_row(logger, entity, round_num=3, soulcredit=0)

        rows = logger.character_rows_for_round(3)

        assert rows["e1"]["soulcredit"] == 0

    def test_buffer_resets_between_rounds(self, logger):
        log_row(logger, Entity("e1", "X"), round_num=1)
        log_row(logger, Entity("e2", "Y"), round_num=2)

        assert logger.character_rows_for_round(1) == {}
        assert set(logger.character_rows_for_round(2)) == {"e2"}
