"""Tests for the rules-fidelity eval item extractor (datamine.rules_fidelity).

Eval items pair the inputs a model would see (state + declared action + dice)
with ground truth: deterministic targets recomputed from YAGS Aeonisk v1.3.0
rules (mirroring mechanics.py resolve_action), or canonical DM adjudications
(soulcredit/void deltas). Logged events that disagree with the deterministic
mirror are quarantined, never emitted as ground truth.
"""

import json
import sys
from pathlib import Path

import pytest

scripts_dir = Path(__file__).parent.parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from datamine.rules_fidelity import (
    derive_roll_targets,
    determine_tier,
    extract_items,
    extract_from_file,
    write_items,
)

GOLDEN_SEED_DIR = Path(__file__).parent.parent / "fixtures" / "sessions" / "golden_seed"


# ---------------------------------------------------------------------------
# Deterministic roll mirror
# ---------------------------------------------------------------------------

class TestDetermineTier:
    @pytest.mark.parametrize("margin,tier", [
        (-20, "critical_failure"),
        (-21, "critical_failure"),
        (-19, "failure"),
        (-1, "failure"),
        (0, "marginal"),
        (4, "marginal"),
        (5, "moderate"),
        (9, "moderate"),
        (10, "good"),
        (14, "good"),
        (15, "excellent"),
        (19, "excellent"),
        (20, "exceptional"),
        (35, "exceptional"),
    ])
    def test_tier_bands_match_mechanics_engine(self, margin, tier):
        assert determine_tier(margin) == tier


class TestDeriveRollTargets:
    def test_skilled_roll(self):
        # Golden-seed combat: Agility 4 x Combat 5 + d20(8) = 28 vs DC 18
        t = derive_roll_targets(
            attribute_value=4, skill_value=5, d20=8, dc=18, skill="Combat")
        assert t == {
            "ability": 20, "total": 28, "margin": 10,
            "success": True, "tier": "good",
        }

    def test_skilled_roll_with_modifiers(self):
        t = derive_roll_targets(
            attribute_value=3, skill_value=2, d20=12, dc=20,
            modifier_total=3, skill="Stealth")
        assert t["ability"] == 6
        assert t["total"] == 21  # 6 + 12 + 3
        assert t["margin"] == 1
        assert t["success"] is True
        assert t["tier"] == "marginal"

    def test_skilled_failure(self):
        t = derive_roll_targets(
            attribute_value=3, skill_value=2, d20=2, dc=20, skill="Melee")
        assert t["total"] == 8
        assert t["margin"] == -12
        assert t["success"] is False
        assert t["tier"] == "failure"

    def test_unskilled_halves_d20(self):
        # Unskilled standard skill: d20 // 2, no ability bonus
        t = derive_roll_targets(
            attribute_value=4, skill_value=0, d20=15, dc=10, skill="Athletics")
        assert t["ability"] == 0
        assert t["total"] == 7
        assert t["margin"] == -3
        assert t["success"] is False

    def test_unskilled_fumble_is_critical_failure(self):
        # Natural 1-2 on an unskilled attempt fumbles regardless of margin
        t = derive_roll_targets(
            attribute_value=4, skill_value=0, d20=2, dc=1, skill="Athletics")
        assert t["success"] is False
        assert t["tier"] == "critical_failure"

    def test_unskilled_knowledge_skill_auto_fails(self):
        # Knowledge skills cannot be attempted untrained (YAGS rule)
        t = derive_roll_targets(
            attribute_value=4, skill_value=0, d20=18, dc=15,
            skill="Magic Theory")
        assert t["total"] == 0
        assert t["margin"] == -15
        assert t["success"] is False
        assert t["tier"] == "critical_failure"


# ---------------------------------------------------------------------------
# Event extraction
# ---------------------------------------------------------------------------

def make_resolution_event(**overrides):
    """A minimal action_resolution event matching the JSONL schema."""
    event = {
        "event_type": "action_resolution",
        "ts": "2026-06-22T23:30:47.508580",
        "session": "cc623d57-f285-4ca9-a8db-f9a3a6cb8179",
        "round": 1,
        "phase": "adjudicate",
        "agent": "Enforcer Kael Dren",
        "action": "Stun the nearest thug",
        "context": {
            "action_type": "combat",
            "is_ritual": False,
            "faction": "Pantheon Security",
            "description": "Swing the shock baton in a controlled arc.",
            "damage_effects": [],
        },
        "roll": {
            "attr": "Agility", "attr_val": 4, "skill": "Combat",
            "skill_val": 5, "ability": 20, "d20": 8,
            "modifiers": None, "modifier_total": None,
            "total": 28, "dc": 18, "margin": 10,
            "tier": "good", "success": True,
        },
        "economy": {
            "void_delta": 0, "void_triggers": [], "void_source": "structured_output",
            "soulcredit_delta": 0, "soulcredit_reasons": [],
            "soulcredit_source": "structured_output",
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(event.get(key), dict):
            event[key].update(value)
        else:
            event[key] = value
    return event


class TestExtractRollItems:
    def test_emits_consistent_roll_item(self):
        result = extract_items([make_resolution_event()], source_file="x.jsonl")
        rolls = [i for i in result.items if i["task"] == "roll_resolution"]
        assert len(rolls) == 1
        item = rolls[0]
        assert item["verifier"] == "deterministic"
        assert item["inputs"]["attribute"] == "Agility"
        assert item["inputs"]["attribute_value"] == 4
        assert item["inputs"]["skill_value"] == 5
        assert item["inputs"]["d20"] == 8
        assert item["inputs"]["dc"] == 18
        assert item["targets"] == {
            "ability": 20, "total": 28, "margin": 10,
            "success": True, "tier": "good",
        }
        assert item["source"]["session"] == "cc623d57-f285-4ca9-a8db-f9a3a6cb8179"
        assert item["source"]["file"] == "x.jsonl"
        assert result.quarantined == []

    def test_quarantines_log_mismatch(self):
        # Logged total disagrees with attr*skill + d20 -> never emit as truth
        event = make_resolution_event(roll={"total": 99, "margin": 81})
        result = extract_items([event])
        assert [i for i in result.items if i["task"] == "roll_resolution"] == []
        assert len(result.quarantined) == 1
        assert "total" in result.quarantined[0]["mismatched_fields"]

    def test_skips_rolls_without_dice(self):
        # Enemy fixed-behavior actions log null rolls
        event = make_resolution_event(roll={
            "attr": None, "attr_val": 0, "skill": None, "skill_val": 0,
            "ability": None, "d20": None, "total": None, "dc": None,
            "margin": 0, "tier": None, "success": None,
        })
        result = extract_items([event])
        assert [i for i in result.items if i["task"] == "roll_resolution"] == []
        assert result.quarantined == []

    def test_item_ids_unique(self):
        events = [make_resolution_event(), make_resolution_event()]
        result = extract_items(events)
        ids = [i["item_id"] for i in result.items]
        assert len(ids) == len(set(ids))


class TestExtractDamageItems:
    def test_emits_damage_item(self):
        event = make_resolution_event(context={"damage_effects": [{
            "type": "damage", "target": "tgt_kvgx", "base_damage": 15,
            "soak": 3, "dealt": 12, "damage_type": "wound",
            "source": "structured_output",
        }]})
        result = extract_items([event])
        dmg = [i for i in result.items if i["task"] == "damage_soak"]
        assert len(dmg) == 1
        assert dmg[0]["verifier"] == "deterministic"
        assert dmg[0]["inputs"] == {"base_damage": 15, "soak": 3,
                                    "damage_type": "wound"}
        assert dmg[0]["targets"] == {"dealt": 12}

    def test_quarantines_damage_mismatch(self):
        event = make_resolution_event(context={"damage_effects": [{
            "type": "damage", "target": "t", "base_damage": 15,
            "soak": 3, "dealt": 5, "damage_type": "wound",
        }]})
        result = extract_items([event])
        assert [i for i in result.items if i["task"] == "damage_soak"] == []
        assert len(result.quarantined) == 1


class TestExtractSoulcreditItems:
    def test_emits_canonical_adjudication_item(self):
        event = make_resolution_event(economy={
            "soulcredit_delta": 1,
            "soulcredit_reasons": ["enforced lawful surrender without bloodshed"],
        })
        result = extract_items([event])
        souls = [i for i in result.items if i["task"] == "soulcredit_adjudication"]
        assert len(souls) == 1
        item = souls[0]
        assert item["verifier"] == "canonical"
        assert item["inputs"]["action"] == "Stun the nearest thug"
        assert item["inputs"]["outcome"]["tier"] == "good"
        assert item["targets"]["soulcredit_delta"] == 1
        assert item["targets"]["void_delta"] == 0
        assert item["targets"]["soulcredit_reasons"] == [
            "enforced lawful surrender without bloodshed"]

    def test_zero_delta_items_still_emitted(self):
        # Knowing when NOT to award soulcredit is part of the eval
        result = extract_items([make_resolution_event()])
        souls = [i for i in result.items if i["task"] == "soulcredit_adjudication"]
        assert len(souls) == 1
        assert souls[0]["targets"]["soulcredit_delta"] == 0

    def test_task_filter(self):
        result = extract_items([make_resolution_event()],
                               tasks={"roll_resolution"})
        assert {i["task"] for i in result.items} == {"roll_resolution"}


# ---------------------------------------------------------------------------
# Golden-seed integration + serialization
# ---------------------------------------------------------------------------

class TestGoldenSeedFixtures:
    @pytest.mark.skipif(not GOLDEN_SEED_DIR.exists(),
                        reason="golden seed fixtures not present")
    def test_extracts_from_all_fixtures_without_quarantine(self):
        all_items = []
        for path in sorted(GOLDEN_SEED_DIR.glob("*.jsonl")):
            result = extract_from_file(path)
            # Engine-generated logs must agree with the rules mirror
            assert result.quarantined == [], (
                f"{path.name}: {result.quarantined[:2]}")
            all_items.extend(result.items)
        by_task = {}
        for item in all_items:
            by_task.setdefault(item["task"], []).append(item)
        assert len(by_task.get("roll_resolution", [])) >= 15
        assert len(by_task.get("damage_soak", [])) >= 3
        assert len(by_task.get("soulcredit_adjudication", [])) >= 20
        ids = [i["item_id"] for i in all_items]
        assert len(ids) == len(set(ids))


class TestWriteItems:
    def test_writes_jsonl(self, tmp_path):
        result = extract_items([make_resolution_event()])
        out = tmp_path / "items.jsonl"
        write_items(result.items, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == len(result.items)
        assert json.loads(lines[0])["task"]
