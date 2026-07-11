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
