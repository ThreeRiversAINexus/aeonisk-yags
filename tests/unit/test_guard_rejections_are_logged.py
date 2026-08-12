"""A guard that leaves no trace cannot be measured or regression-tested (#155).

Five guards across five modules announced themselves to the console and nowhere
else. Across the 303 run logs on disk that is 343 dropped viewer ids, 75
prisoner-targeting warnings, 72 refused conversions and 9 rejected attribute
reframes — none of it readable from the corpus, all of it readable only by
grepping stdout, which is the practice this project retired precisely because
grep locates and does not conclude.

Two costs, and the second is the one that bites:

  * the highest-signal events for the research question are unmeasurable.
    "How often does the DM aim combat damage at a prisoner" is a fidelity
    measurement, not noise, and nothing could compute it;
  * no fixture can assert that a guard fired, because firing writes nothing —
    so the guards themselves have no recorded-data regression test.

The event carries a `disposition` rather than a bare "rejected" flag because
the four outcomes are not interchangeable. `allowed` means the guard flagged a
request and let it through (a signal about the DM), `skipped` means it refused
(a signal about the engine's protection), `corrected` means it repaired the
request, `dropped` means it discarded input. Summing them would hide which one
is growing.
"""

import pathlib

import pytest

from aeonisk.multiagent.guard_log import DISPOSITIONS, record_guard_rejection
from aeonisk.multiagent.outcome_pipeline import canonicalize_viewer_ids
from aeonisk.multiagent.round_assessment import apply_assessments


class RecordingLogger:
    """The jsonl_logger surface the helper touches, and nothing more."""

    def __init__(self):
        self.events = []

    def log_guard_rejection(self, **kw):
        self.events.append(kw)


class FakeMechanics:
    def __init__(self, logger=None, current_round=3):
        self.jsonl_logger = logger
        self.current_round = current_round


class TestTheHelper:

    def test_it_writes_the_event(self):
        m = FakeMechanics(RecordingLogger())

        assert record_guard_rejection(
            m, 2, guard='target_combat_state', disposition='allowed',
            requested='tgt_4at1', reason='target is a prisoner') is True
        assert m.jsonl_logger.events == [{
            'round_num': 2, 'guard': 'target_combat_state',
            'disposition': 'allowed', 'requested': 'tgt_4at1',
            'reason': 'target is a prisoner', 'subject_id': None,
            'agent_id': None, 'substituted': None}]

    def test_a_missing_round_falls_back_to_the_engine(self):
        """Validators do not all know the round; the engine always does."""
        m = FakeMechanics(RecordingLogger(), current_round=7)

        record_guard_rejection(m, None, guard='g', disposition='dropped',
                               requested='x', reason='y')

        assert m.jsonl_logger.events[0]['round_num'] == 7

    def test_no_logger_is_not_an_error(self):
        """A guard must not be able to crash the session it protects."""
        assert record_guard_rejection(FakeMechanics(None), 1, guard='g',
                                      disposition='skipped', requested='x',
                                      reason='y') is False

    def test_no_mechanics_at_all_is_not_an_error(self):
        assert record_guard_rejection(None, 1, guard='g', disposition='skipped',
                                      requested='x', reason='y') is False

    def test_an_unknown_disposition_is_refused(self):
        """The vocabulary is the point. A free-text disposition would make the
        counts unaggregatable, which is the defect this event exists to fix."""
        with pytest.raises(ValueError, match="unknown disposition"):
            record_guard_rejection(FakeMechanics(RecordingLogger()), 1,
                                   guard='g', disposition='rejected',
                                   requested='x', reason='y')

    def test_the_four_dispositions_are_distinct_and_closed(self):
        assert DISPOSITIONS == {'skipped', 'corrected', 'dropped', 'allowed'}


class TestTheViewerIdGuard:
    """`canonicalize_viewer_ids` — 343 silent drops across 16 runs."""

    ROSTER = {'player_01': 'Hard Vane', 'npc_subdued_operative_#1_9872':
              'Subdued Operative #1'}

    def test_an_unmappable_id_is_recorded(self):
        m = FakeMechanics(RecordingLogger())

        kept = canonicalize_viewer_ids(
            ['player_01', 'npc_subdued_operative_1'], self.ROSTER, m, 1)

        assert kept == ['player_01']
        assert [(e['guard'], e['disposition'], e['requested'])
                for e in m.jsonl_logger.events] == [
            ('viewer_id_mapping', 'dropped', 'npc_subdued_operative_1')]

    def test_the_real_normalisation_failure_from_3de9e609(self):
        """The recorded id is `npc_subdued_operative_#1_9872`; the synthesis
        proposed `npc_subdued_operative_1`, and stripping `#N_<suffix>` is not
        something the matcher does. Three of these in one round."""
        m = FakeMechanics(RecordingLogger())

        kept = canonicalize_viewer_ids(
            [f'npc_subdued_operative_{n}' for n in (1, 2, 3)], self.ROSTER, m, 1)

        assert kept == []
        assert len(m.jsonl_logger.events) == 3

    def test_a_clean_list_records_nothing(self):
        m = FakeMechanics(RecordingLogger())

        assert canonicalize_viewer_ids(['player_01'], self.ROSTER, m, 1) == ['player_01']
        assert m.jsonl_logger.events == []

    def test_it_still_works_without_a_logger(self):
        """The parameter is optional; every existing caller must keep working."""
        assert canonicalize_viewer_ids(['nope'], self.ROSTER) == []


class TestTheAttributeReframeGuard:
    """`apply_assessments` — the DM naming an attribute that cannot exist."""

    SHEETS = {'Hard Vane': ({'Agility': 4}, {'Guns': 4})}

    def _declared(self):
        return {'player_01': [{'action': {
            'character_name': 'Hard Vane', 'attribute': 'Agility',
            'skill': 'Guns', 'difficulty_estimate': 10}}]}

    def _assessment(self, attribute):
        from aeonisk.multiagent.round_assessment import (
            ActionAssessment, RoundAssessment)
        return RoundAssessment(assessments=[ActionAssessment(
            character_name='Hard Vane', difficulty=10, attribute=attribute,
            reasoning='reframe under test')])

    def test_a_rejected_reframe_is_recorded(self):
        m = FakeMechanics(RecordingLogger())

        apply_assessments(self._declared(), self._assessment('Presence'),
                          self.SHEETS, mechanics=m)

        e = m.jsonl_logger.events[0]
        assert (e['guard'], e['disposition']) == ('attribute_reframe', 'skipped')
        assert e['requested'] == 'Presence'
        assert e['subject_id'] == 'Hard Vane'
        assert e['substituted'] == 'Agility'

    def test_an_accepted_reframe_records_nothing(self):
        """Only refusals. An event per successful ruling would drown them."""
        m = FakeMechanics(RecordingLogger())

        apply_assessments(self._declared(), self._assessment('Perception'),
                          self.SHEETS, mechanics=m)

        assert m.jsonl_logger.events == []

    def test_the_refusal_still_stands_without_a_logger(self):
        """Logging is observation, never control: the guard's decision must not
        depend on whether anyone is writing it down."""
        actions = self._declared()

        apply_assessments(actions, self._assessment('Presence'), self.SHEETS)

        assert actions['player_01'][0]['action']['attribute'] == 'Agility'


class TestTheGuardsAreReachableFromProduction:
    """A unit test on a guard proves the guard works, not that anything calls it.

    `canonicalize_viewer_ids` took `mechanics` as an optional argument and both
    production callers omitted it, so the viewer-id guard was instrumented and
    unreachable. The unit tests above passed the whole time — they call the
    function directly with the argument production never supplied.

    A live session made it visible immediately: the console reported four
    dropped viewer ids and three rejected attribute reframes, and the JSONL
    carried three `guard_rejection` events. Seven fired, three recorded.

    These check the wiring rather than the behaviour, which is the half that
    was missing.
    """

    SOURCE = pathlib.Path(__file__).parent.parent.parent / "scripts/aeonisk/multiagent"

    def test_synthesis_visibility_passes_mechanics_down(self):
        text = (self.SOURCE / "outcome_pipeline.py").read_text(encoding="utf-8")
        call = text.split("def canonicalize_synthesis_visibility", 1)[1]

        assert "canonicalize_viewer_ids(\n                segment.visibility, roster, mechanics, round_num)" in call

    def test_the_outcome_builder_passes_mechanics_down(self):
        text = (self.SOURCE / "outcome_pipeline.py").read_text(encoding="utf-8")

        assert "_effective_visibility(\n            resolution_data.get(\"aware_agents\", []) or [],\n            before,\n            facts,\n            mechanics,\n            round_num,\n        )" in text

    def test_every_outcome_build_site_supplies_mechanics(self):
        """Four sites in `_run_initiative_round`; one left unwired would drop
        that phase's viewer decisions silently."""
        text = (self.SOURCE / "session.py").read_text(encoding="utf-8")
        builds = text.count("applied_outcome = build_applied_outcome(")

        assert builds == 4
        assert text.count(
            "applied_outcome = build_applied_outcome(\n                            mechanics=mechanics,") == 4

    def test_the_dm_supplies_mechanics_when_canonicalising(self):
        text = (self.SOURCE / "dm.py").read_text(encoding="utf-8")
        call = text.split("canonicalize_synthesis_visibility(", 1)[1][:400]

        assert "mechanics=" in call and "round_num=" in call
