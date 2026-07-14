"""Tests for the VIII.1 vendor access gate (faction + standing).

Nexus-aligned institutions (Arcane Genetics/ArcGen, Pantheon Security, Astral
Commerce Group/ACG, Aether Dynamics, Sovereign Nexus) check the Codex ledger:
Soulcredit -2 and under is cut off from their markets. Freeborn / Tempest /
Independent markets do not ask. Per-item soulcredit_requirement gates sanctioned
gear at aligned vendors. Additive to the existing vendor-type rules.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.energy_economy import (
    EnergyPurse, Vendor, VendorItem, VendorType, is_nexus_aligned,
)
from aeonisk.multiagent.mechanics import MechanicsEngine
from aeonisk.multiagent.player import CharacterState
from aeonisk.multiagent.shared_state import SharedState


def _char(sc):
    c = CharacterState(
        name="Debtor Vex", faction="Freeborn",
        attributes={"strength": 2, "agility": 3, "endurance": 3,
                    "perception": 4, "intelligence": 4, "empathy": 3,
                    "willpower": 3, "charisma": 2, "size": 10},
        skills={"charm": 2}, void_score=0, soulcredit=sc, bonds=[],
        goals=["Survive"], pronouns="they/them")
    c.energy_purse = EnergyPurse()
    c.energy_purse.drip = 100
    c.energy_purse.spark = 100
    return c


def _vendor(faction, item_req=0, vtype=VendorType.HUMAN_TRADER, vid="vnd_1"):
    item = VendorItem(name="Med Kit", description="Restores HP",
                      item_id="itm_medkit", price_drip=5,
                      soulcredit_requirement=item_req)
    v = Vendor(vendor_id=vid, name=f"{faction} Outpost", faction=faction,
               vendor_type=vtype, inventory=[item])
    return v


def _validate(sc, vendor):
    ss = SharedState()
    ss.add_vendor(vendor)
    mech = MechanicsEngine(shared_state=ss)
    return mech.validate_purchase(_char(sc), vendor.vendor_id, "itm_medkit")


class TestIsNexusAligned:

    @pytest.mark.parametrize("faction", [
        "Arcane Genetics", "ArcGen", "Pantheon Security", "Astral Commerce Group",
        "ACG", "Aether Dynamics", "Sovereign Nexus", "Nexus",
    ])
    def test_aligned(self, faction):
        assert is_nexus_aligned(faction) is True

    @pytest.mark.parametrize("faction", [
        "Freeborn", "Tempest Industries", "Independent", "Resonance Communes",
        "Neutral", None, "",
    ])
    def test_not_aligned(self, faction):
        assert is_nexus_aligned(faction) is False


class TestStandingGate:

    def test_aligned_blocks_at_negative_two(self):
        v = _vendor("Arcane Genetics")
        for sc in (-2, -5):
            res = _validate(sc, v)
            assert res.is_valid is False and res.sc_blocked is True

    def test_aligned_allows_at_minus_one_and_above(self):
        v = _vendor("Pantheon Security")
        for sc in (-1, 0, 3):
            res = _validate(sc, v)
            assert res.is_valid is True, f"SC {sc} should pass"

    def test_non_aligned_never_gates(self):
        v = _vendor("Freeborn")
        res = _validate(-5, v)
        assert res.is_valid is True, "Freeborn markets do not ask"

    def test_block_message_names_soulcredit_and_value(self):
        res = _validate(-4, _vendor("Astral Commerce Group"))
        assert "Soulcredit" in res.failure_reason and "-4" in res.failure_reason


class TestItemRequirement:

    def test_sanctioned_item_requires_standing_at_aligned_vendor(self):
        v = _vendor("Arcane Genetics", item_req=6)
        assert _validate(3, v).is_valid is False   # below +6 Trusted
        assert _validate(6, v).is_valid is True     # meets Trusted floor

    def test_item_requirement_ignored_at_non_aligned_vendor(self):
        # Freeborn does not ask, even for a nominally sanctioned item.
        v = _vendor("Freeborn", item_req=6)
        assert _validate(0, v).is_valid is True
