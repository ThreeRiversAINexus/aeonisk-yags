"""Tests for contract-gear Soulcredit locks (Gear & Tech Reference v1.2.2).

A weapon tagged `soulcredit_locked` (the Debtbreaker Sidearm) refuses to fire
when the wielder's Soulcredit falls below its floor (SC < 0). This is the pure
predicate; the attack-path enforcement is tested separately.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.weapons import (
    Weapon,
    get_weapon,
    weapon_is_sc_locked,
    weapon_sc_lock_threshold,
)


def _plain_pistol():
    return Weapon(name="Union Heavy Pistol", skill="Guns", attack=0, defence=0,
                  damage=4, damage_type="wound", is_ranged=True,
                  special=["ubiquitous", "legal_most_zones"])


class TestThreshold:

    def test_debtbreaker_threshold_is_zero(self):
        assert weapon_sc_lock_threshold(get_weapon("debtbreaker_sidearm")) == 0

    def test_non_locked_weapon_has_no_threshold(self):
        assert weapon_sc_lock_threshold(_plain_pistol()) is None

    def test_none_weapon_has_no_threshold(self):
        assert weapon_sc_lock_threshold(None) is None


class TestLockPredicate:

    def test_debtbreaker_locks_below_zero(self):
        w = get_weapon("debtbreaker_sidearm")
        assert weapon_is_sc_locked(w, -1) is True
        assert weapon_is_sc_locked(w, -5) is True

    def test_debtbreaker_fires_at_zero_and_above(self):
        w = get_weapon("debtbreaker_sidearm")
        assert weapon_is_sc_locked(w, 0) is False
        assert weapon_is_sc_locked(w, 3) is False

    def test_plain_weapon_never_locks(self):
        w = _plain_pistol()
        assert weapon_is_sc_locked(w, -10) is False
        assert weapon_is_sc_locked(w, 5) is False

    def test_none_weapon_never_locks(self):
        assert weapon_is_sc_locked(None, -10) is False

    def test_registry_debtbreaker_is_tagged(self):
        assert "soulcredit_locked" in get_weapon("debtbreaker_sidearm").special


class TestDamageBackstop:
    """Deterministic: a locked contract weapon deals NO damage, whatever the
    DM narrated (_process_structured_damage_effects short-circuits)."""

    def _mech_with_sc(self, agent_id, score):
        from aeonisk.multiagent.mechanics import MechanicsEngine
        mech = MechanicsEngine()
        mech.get_soulcredit_state(agent_id).adjust(score, "test setup")
        return mech

    def test_locked_weapon_drops_all_damage(self):
        from types import SimpleNamespace
        from aeonisk.multiagent.dm import _process_structured_damage_effects
        mech = self._mech_with_sc("p1", -1)
        effects = [SimpleNamespace(target="tgt_x", dealt=15)]
        out = _process_structured_damage_effects(
            effects, shared_state=None, current_round=1, mechanics=mech,
            attacker_id="p1", attacker_name="Debtor Vex", weapon="Debtbreaker Sidearm")
        assert len(out) == 1 and "LOCKED" in out[0]

    def test_unlocked_weapon_not_short_circuited(self):
        """SC at the floor (0) does not trip the lock guard."""
        from types import SimpleNamespace
        from aeonisk.multiagent import dm as dmmod
        mech = self._mech_with_sc("p1", 0)
        effects = [SimpleNamespace(target="tgt_x", dealt=15)]
        # Real path would resolve targets; stub target resolution to a no-op so
        # we only assert the lock guard did NOT fire.
        out = dmmod._process_structured_damage_effects(
            effects, shared_state=None, current_round=1, mechanics=mech,
            attacker_id="p1", attacker_name="Vex", weapon="Debtbreaker Sidearm")
        # shared_state=None → normal path resolves no target, returns without a
        # LOCKED message.
        assert not any("LOCKED" in m for m in out)


class TestDMDirective:
    """_build_weapon_context emits a lock directive so narration matches."""

    def _shared_state(self, sc):
        from types import SimpleNamespace
        from aeonisk.multiagent.mechanics import MechanicsEngine
        mech = MechanicsEngine()
        mech.get_soulcredit_state("p1").adjust(sc, "setup")
        player = SimpleNamespace(
            agent_id="p1",
            equipped_weapons={"primary": get_weapon("debtbreaker_sidearm"),
                              "sidearm": None})
        return SimpleNamespace(
            player_agents=[player],
            get_mechanics_engine=lambda: mech)

    def test_locked_emits_directive(self):
        from aeonisk.multiagent.dm import _build_weapon_context
        action = {"action_type": "attack", "agent_id": "p1", "skill": "guns"}
        ctx = _build_weapon_context(action, self._shared_state(-1))
        assert "CONTRACT WEAPON LOCKED" in ctx and "NO damage" in ctx
