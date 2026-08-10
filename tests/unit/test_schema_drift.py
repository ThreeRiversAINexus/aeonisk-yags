"""Schema-drift gate: the committed scripts/schema_contract.json is the frozen
ground-truth structural schema of the session JSONL corpus. This test re-mines the
live corpus and asserts it introduces nothing the contract doesn't already know —
no new event type, field, value type, or enum value.

Why this exists: the invariant checker and analysis tooling hard-code assumptions
about the schema (which fields are authoritative, what enum values occur). Those
assumptions rotted silently before — the corpus grew to 40 event types while the
docs said 19, and invariants over-fired by mixing two subsystems' scales. When the
schema genuinely changes, this test fails loudly; a human reviews the drift and
regenerates the contract (`python scripts/schema_mine.py --contract --out
scripts/schema_contract.json`) as a deliberate, reviewed act — instead of an
assumption drifting unnoticed into a bad dataset.
"""
import json
import os

import pytest

from scripts.schema_mine import mine, build_contract, diff_contract, iter_session_files

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONTRACT = os.path.join(_REPO, "scripts", "schema_contract.json")
_CORPUS = os.path.join(_REPO, "multiagent_output")


# --- fast, corpus-independent unit tests of the diff engine -----------------
class TestDiffContract:
    def _ref(self):
        return {
            "event_types": ["character_state", "combat_action"],
            "schema": {
                "character_state": {
                    "death_state": {"types": ["str"], "values": ["alive", "dead", "unconscious"]},
                    "wounds": {"types": ["int"], "numeric": True},
                },
                "combat_action": {"weapon": {"types": ["str"], "values": "freeform"}},
            },
        }

    def test_identical_is_clean(self):
        drift, _ = diff_contract(self._ref(), self._ref())
        assert drift == []

    def test_new_event_type_is_drift(self):
        live = self._ref()
        live["event_types"] = live["event_types"] + ["telemetry_beacon"]
        drift, _ = diff_contract(self._ref(), live)
        assert any("NEW event_type: telemetry_beacon" in d for d in drift)

    def test_new_enum_value_is_drift(self):
        live = self._ref()
        live["schema"]["character_state"]["death_state"]["values"] = \
            ["alive", "dead", "unconscious", "petrified"]
        drift, _ = diff_contract(self._ref(), live)
        assert any("petrified" in d for d in drift)

    def test_new_field_is_drift(self):
        live = self._ref()
        live["schema"]["character_state"]["hexed"] = {"types": ["bool"], "values": ["False", "True"]}
        drift, _ = diff_contract(self._ref(), live)
        assert any("NEW field hexed" in d for d in drift)

    def test_new_type_is_drift(self):
        live = self._ref()
        live["schema"]["character_state"]["wounds"]["types"] = ["int", "str"]
        drift, _ = diff_contract(self._ref(), live)
        assert any("NEW type" in d for d in drift)

    def test_shrinkage_is_info_not_drift(self):
        # a value present in the reference but not the live sample must NOT fail
        live = self._ref()
        live["schema"]["character_state"]["death_state"]["values"] = ["alive", "dead"]
        drift, info = diff_contract(self._ref(), live)
        assert drift == []

    def test_freeform_never_drifts(self):
        live = self._ref()
        # weapon stays freeform; a "new weapon" is not a schema change
        drift, _ = diff_contract(self._ref(), live)
        assert drift == []


class TestDynamicKeyCollapse:
    """Data-dependent dict keys (clock names, skill names) must mine as a single
    `parent.*` field, not one field per name — otherwise every new session with a
    fresh clock name is 'schema drift' and the contract churns forever. Mined
    fact: action_resolution.clocks had 762 distinct clock-name keys."""

    def _mine_events(self, events, tmp_path):
        import json as _json
        f = tmp_path / "session_dyn.jsonl"
        f.write_text("\n".join(_json.dumps(e) for e in events))
        tc, pt, _, _ = mine([str(f)])
        return build_contract(tc, pt)

    def test_clock_names_collapse(self, tmp_path):
        events = [
            {"event_type": "action_resolution", "round": 1,
             "clocks": {"ACG Audit Sweep": "0/4", "Void Surge": "2/6"},
             "context": {"clock_sources": {"ACG Audit Sweep": "structured_output"}}},
        ]
        c = self._mine_events(events, tmp_path)
        fields = c["schema"]["action_resolution"]
        assert "clocks.*" in fields
        assert "clocks.ACG Audit Sweep" not in fields
        assert "context.clock_sources.*" in fields

    def test_scene_clock_subfields_merge_under_star(self, tmp_path):
        events = [
            {"event_type": "end_state_snapshot",
             "state_summary": {"scene_clocks": {
                 "Doom": {"current": 2, "maximum": 6},
                 "Hope": {"current": 1, "maximum": 4}}}},
        ]
        c = self._mine_events(events, tmp_path)
        fields = c["schema"]["end_state_snapshot"]
        assert "state_summary.scene_clocks.*" in fields
        assert "state_summary.scene_clocks.*.current" in fields
        assert "state_summary.scene_clocks.Doom" not in fields

    def test_skill_names_collapse(self, tmp_path):
        events = [
            {"event_type": "enemy_spawn", "round": 0,
             "stats": {"health": 20, "skills": {"Guns": 4, "Intimacy Ritual": 2}}},
        ]
        c = self._mine_events(events, tmp_path)
        fields = c["schema"]["enemy_spawn"]
        assert "stats.skills.*" in fields
        assert "stats.skills.Guns" not in fields

    def test_fixed_schema_fields_do_not_collapse(self, tmp_path):
        events = [
            {"event_type": "combat_action", "round": 1,
             "damage": {"base_damage": 12, "soak": 3, "dealt": 9}},
        ]
        c = self._mine_events(events, tmp_path)
        fields = c["schema"]["combat_action"]
        assert "damage.base_damage" in fields
        assert "damage.*" not in fields

    def test_envelope_identity_fields_are_freeform(self, tmp_path):
        # event_id/ts/session/correlation_id are per-event identity, never an
        # enum — on rare event types they pinned as 3-value enums and drifted
        # on every new session
        events = [
            {"event_type": "targeting_validation", "round": 1,
             "ts": "2026-07-12T07:03:49", "session": "abc-123",
             "event_id": "uuid-1", "parent_event_id": "uuid-0",
             "correlation_id": "round_2_x", "original_target": "tgt_a"},
        ]
        c = self._mine_events(events, tmp_path)
        fields = c["schema"]["targeting_validation"]
        for f in ("ts", "session", "event_id", "parent_event_id", "correlation_id"):
            assert fields[f]["values"] == "freeform", f

    def test_new_clock_name_is_not_drift(self, tmp_path):
        ref = self._mine_events(
            [{"event_type": "action_resolution", "round": 1,
              "clocks": {"Old Clock": "0/4"}}], tmp_path)
        (tmp_path / "session_dyn.jsonl").unlink()
        live = self._mine_events(
            [{"event_type": "action_resolution", "round": 1,
              "clocks": {"A Brand New Clock Name": "1/8"}}], tmp_path)
        drift, _ = diff_contract(ref, live)
        assert drift == []


# --- the real gate: live corpus vs committed contract -----------------------
@pytest.mark.skipif(not os.path.exists(_CONTRACT), reason="no committed contract")
@pytest.mark.skipif(not iter_session_files([_CORPUS]),
                    reason="no session corpus present (CI without data)")
def test_live_corpus_matches_frozen_contract():
    reference = json.load(open(_CONTRACT))
    tc, per_type, _, _ = mine([_CORPUS])
    live = build_contract(tc, per_type)
    drift, info = diff_contract(reference, live)
    assert not drift, (
        "Session JSONL schema drifted from the frozen contract. Review each change; "
        "if intentional, regenerate: python scripts/schema_mine.py --contract "
        "--out scripts/schema_contract.json\n  " + "\n  ".join(drift)
    )


def test_entity_keyed_maps_never_mine_as_schema_fields():
    """Enemy ids carry a uuid suffix (`enemy_spawner.py:87`), so any map keyed by
    entity id mints "new schema fields" on every single session.

    `soulcredit_states` shipped without that registration and drifted the
    contract the first time a session with enemies was mined — the same defect
    class as #104, in a field added during the same audit.
    """
    from scripts.schema_mine import DYNAMIC_KEY_PARENTS, build_contract, mine
    import json
    import tempfile
    import os

    for parent in ("final_state.soulcredit_states", "state_summary.soulcredit_states"):
        assert parent in DYNAMIC_KEY_PARENTS, f"{parent} is keyed by entity id"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "session_x.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({
                "event_type": "session_end",
                "data": {"final_state": {"soulcredit_states": {
                    "enemy_boss_2937e857": {"score": -3, "changes": 1}}}},
            }) + "\n")

        contract = build_contract(*mine([path])[:2])

    fields = contract["schema"]["session_end"]
    assert "final_state.soulcredit_states.*" in fields
    assert not any("2937e857" in path for path in fields), \
        "a random enemy id leaked into the frozen contract"
