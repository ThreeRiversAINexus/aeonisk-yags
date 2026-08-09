"""Dynamic maps are values, not schema.

#104. `schema_mine` records every key of a dict as a distinct schema field. For
a fixed record that is right. For a map keyed by item name or agent id it means
the frozen contract fills with things that change every session:

    applied_outcome:     NEW field applied_effects.item_discovery.items_added.void_lattice_samples
    applied_outcome:     NEW field applied_effects.item_discovery.items_added.physical_ledger_core
    end_state_snapshot:  NEW field state_summary.soulcredit_states.enemy_void_cultist_fd9f7bb5

Every new item the DM invents, and every per-session agent id, becomes permanent
drift. That matters beyond noise: `test_schema_drift` is meant to make a schema
change *a deliberate reviewed act*, and a gate that cries wolf gets regenerated
reflexively — which is how a real change slips through unread.

`DYNAMIC_KEY_PARENTS` already exists for exactly this and collapses such keys to
`*`. These maps were simply never registered.
"""

import json
from pathlib import Path

import pytest

from scripts.schema_mine import DYNAMIC_KEY_PARENTS, _walk

_CONTRACT = Path(__file__).resolve().parents[2] / "scripts" / "schema_contract.json"

# Maps whose keys are data. Event-relative paths, matching the existing entries.
EXPECTED_DYNAMIC = {
    "applied_effects.item_discovery.items_added",
    "applied_effects.item_discovery.items_removed",
    "state_summary.soulcredit_states",
    "state_summary.void_states",
    "final_state.soulcredit_states",
    "final_state.void_states",
}


class TestRegistry:

    @pytest.mark.parametrize("path", sorted(EXPECTED_DYNAMIC))
    def test_map_is_registered_as_dynamic(self, path):
        assert path in DYNAMIC_KEY_PARENTS, (
            f"{path} is keyed by data (item name / agent id); without "
            f"registration every new key is permanent schema drift")


class TestWalkerCollapsesThem:
    """The behaviour, not just the registry entry."""

    def _paths(self, prefix, obj):
        from collections import defaultdict

        class Stat:
            def __init__(self):
                self.seen = []

            def observe(self, v):
                self.seen.append(v)

        stats = defaultdict(Stat)
        _walk(prefix, obj, stats, 0)
        return set(stats)

    def test_item_names_collapse_to_a_star(self):
        paths = self._paths("applied_effects.item_discovery",
                            {"items_added": {"void_lattice_samples": 2,
                                             "physical_ledger_core": 1}})

        assert "applied_effects.item_discovery.items_added.*" in paths
        assert not any("void_lattice_samples" in p for p in paths)

    def test_agent_ids_collapse_to_a_star(self):
        paths = self._paths("state_summary",
                            {"soulcredit_states": {
                                "player_01": {"score": 8, "changes": 3},
                                "enemy_void_cultist_fd9f7bb5": {"score": -5, "changes": 2}}})

        assert "state_summary.soulcredit_states.*" in paths
        assert not any("player_01" in p for p in paths)

    def test_the_value_schema_is_still_mined(self):
        """Collapsing the key must not lose the shape underneath it — the
        contract should still know a ledger entry has score and changes."""
        paths = self._paths("state_summary",
                            {"soulcredit_states": {"player_01": {"score": 8,
                                                                 "changes": 3}}})

        assert "state_summary.soulcredit_states.*.score" in paths
        assert "state_summary.soulcredit_states.*.changes" in paths

    def test_fixed_records_are_untouched(self):
        """A roll is a fixed shape; its keys are schema and must stay named."""
        paths = self._paths("combat_action", {"attack": {"d20": 14, "dc": 18}})

        assert "combat_action.attack.d20" in paths
        assert "combat_action.attack.dc" in paths


class TestContractIsClean:
    """The shipped contract must not still carry per-session keys."""

    @pytest.fixture(scope="class")
    def contract(self):
        if not _CONTRACT.exists():
            pytest.skip("no frozen contract")
        return json.loads(_CONTRACT.read_text())

    def test_no_agent_ids_appear_as_schema_fields(self, contract):
        import re
        agent_id = re.compile(
            r"\.(player_\d+|dm_\d+|enemy_[a-z_]*[0-9a-f]{6,}|npc_[a-z0-9_]+\d)$")
        offenders = [
            f"{event}.{path}"
            for event, fields in contract["schema"].items()
            for path in fields
            if agent_id.search(path)
        ]

        assert not offenders, (
            "per-session agent ids frozen as schema fields — every session will "
            "drift:\n  " + "\n  ".join(sorted(offenders)[:10]))

    def test_no_item_names_under_items_added(self, contract):
        offenders = [
            f"{event}.{path}"
            for event, fields in contract["schema"].items()
            for path in fields
            if "items_added." in path and not path.endswith(".*")
            and ".*." not in path
        ]

        assert not offenders, (
            "item names frozen as schema fields — every new item drifts:\n  "
            + "\n  ".join(sorted(offenders)[:10]))
