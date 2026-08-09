"""The terminal event must carry the Soulcredit ledger.

Regression origin (session a8ca2b7f, 2026-08-09): `get_state_summary()` returned
`scene_clocks`, `void_states` and `recent_actions` — no Soulcredit at all. That
was harmless while only players had standing and it barely moved. It stopped
being harmless once the enforce magistrate could name every entity: the Matron
accrued -2/-3/-3 and the acolyte -2/-3/-1/-2, both finishing near -8, and none of
it reached `session_end`.

For an ethics testbed, where each soul's standing ended is close to the headline
result. Reconstructing it by replaying every post_resolution_adjudication and
summing deltas is possible, but a terminal snapshot should simply say.
"""

import pytest

from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


def make_engine():
    engine = MechanicsEngine.__new__(MechanicsEngine)
    engine.scene_clocks = {}
    engine.void_states = {}
    engine.soulcredit_states = {}
    engine.action_history = []
    return engine


class TestSoulcreditInStateSummary:

    def test_summary_includes_soulcredit_states(self):
        engine = make_engine()
        engine.get_soulcredit_state("player_01").adjust(1, "II.8", round_num=1)

        assert "soulcredit_states" in engine.get_state_summary()

    def test_reports_the_score(self):
        engine = make_engine()
        engine.get_soulcredit_state("player_01").adjust(4, "merit", round_num=1)

        summary = engine.get_state_summary()

        assert summary["soulcredit_states"]["player_01"]["score"] == 4

    def test_covers_non_players(self):
        """The whole point: the antagonists' ledger is the measurement."""
        engine = make_engine()
        boss = engine.get_soulcredit_state("enemy_boss_1")
        for delta in (-2, -3, -3):
            boss.adjust(delta, "III.3", round_num=1)

        summary = engine.get_state_summary()

        assert summary["soulcredit_states"]["enemy_boss_1"]["score"] == -8

    def test_reports_change_count_like_void_states(self):
        """Same shape as void_states so consumers can treat them alike."""
        engine = make_engine()
        sc = engine.get_soulcredit_state("player_01")
        sc.adjust(1, "a", round_num=1)
        sc.adjust(1, "b", round_num=2)

        entry = engine.get_state_summary()["soulcredit_states"]["player_01"]

        assert entry["changes"] == 2

    def test_empty_ledger_is_an_empty_dict_not_a_missing_key(self):
        """Consumers should never have to guard the key itself."""
        assert make_engine().get_state_summary()["soulcredit_states"] == {}

    def test_existing_keys_are_untouched(self):
        summary = make_engine().get_state_summary()

        for key in ("scene_clocks", "void_states", "recent_actions"):
            assert key in summary
