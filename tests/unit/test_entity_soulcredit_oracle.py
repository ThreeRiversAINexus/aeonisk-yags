"""Non-player Soulcredit must reach the character_state oracle.

Regression origin (session a8ca2b7f, 2026-08-09): once the enforce magistrate
could name enemies and NPCs, it wrote them real ledgers — the Matron accrued
-2/-3/-3 across the session (III.3, II.1) and the acolyte -2/-3/-1/-2, both
landing near -8. Every `character_state` row for those entities still reported
`soulcredit: 0`, because the logger hardcoded it:

    soulcredit=0,  # Enemies don't track soulcredit

That comment was true until the roster fix; now it makes the authoritative
life-state oracle contradict the ledger. Research extraction reads
character_state, so the coven's entire transgression record read as zero.
"""

import pytest

from scripts.aeonisk.multiagent.session import entity_soulcredit
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


def make_mechanics():
    m = MechanicsEngine.__new__(MechanicsEngine)
    m.void_states = {}
    m.soulcredit_states = {}
    return m


class TestEntitySoulcredit:

    def test_reads_the_ledger(self):
        mechanics = make_mechanics()
        mechanics.get_soulcredit_state("enemy_boss_1").adjust(-3, "III.3", round_num=1)

        assert entity_soulcredit(mechanics, "enemy_boss_1") == -3

    def test_accumulates_across_rounds(self):
        """The observed Matron trajectory: -2, then -3, then -3."""
        mechanics = make_mechanics()
        sc = mechanics.get_soulcredit_state("enemy_boss_1")
        for delta in (-2, -3, -3):
            sc.adjust(delta, "reason", round_num=1)

        assert entity_soulcredit(mechanics, "enemy_boss_1") == -8

    def test_unknown_entity_is_zero_not_an_error(self):
        """An entity the magistrate never ruled on has no ledger yet."""
        assert entity_soulcredit(make_mechanics(), "never_judged") == 0

    def test_does_not_create_a_ledger_as_a_side_effect(self):
        """Reading must not mint an entry — that would put phantom entities in
        the ledger just by logging their state."""
        mechanics = make_mechanics()

        entity_soulcredit(mechanics, "some_enemy")

        assert "some_enemy" not in mechanics.soulcredit_states

    def test_missing_mechanics_is_zero(self):
        assert entity_soulcredit(None, "enemy_1") == 0
