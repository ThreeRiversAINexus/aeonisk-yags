"""The enemy prompt shipped raw source and a round that never happened (#140).

Read out of the recorded prompt of session a518e68b:

    ## 📖 RECENT ACTION OUTCOMES
    {"=" * 60}
    What just happened in the previous round:

    1. [Sergeant Corin Ireveth, spoken to tgt_ydzd] "Hold still—non-lethal only."

That is **round 1**. There is no previous round, and the quoted line is from the
current one — Corin declared at 06:59:19, Ysolde's call went out at 06:59:31.

Neither half is cosmetic. `_format_recent_outcomes` was the one section in the
module that was not an f-string, so its separator reached the model as Python
source. And the model believed the header:

    "Sergeant Corin Ireveth just declared non-lethal intent last round -
     they're attempting capture operations, making them a priority threat"

The temporal confabulation in that tactical reasoning is downstream of a header
asserting a round that did not exist. Anything mining enemy reasoning for
quality would have scored it against the model.

Only one literal placeholder ever reached the prompt. `grep` finds fifteen
`{"=" * 60}` in this module; the other fourteen are inside f-strings and render
correctly — stated here so nobody "fixes" them.
"""

import re

import pytest

from scripts.aeonisk.multiagent.enemy_prompts import _format_recent_outcomes


NARRATIONS = ['[Sergeant Corin Ireveth, spoken to tgt_ydzd] "Hold still—non-lethal only."']


class TestTheSeparatorRenders:

    def test_no_python_source_reaches_the_model(self):
        assert '{"=" * 60}' not in _format_recent_outcomes(NARRATIONS)

    def test_the_separator_is_an_actual_rule(self):
        assert "=" * 60 in _format_recent_outcomes(NARRATIONS)

    def test_no_unrendered_placeholder_of_any_kind_survives(self):
        """Catches the whole class, not just the one occurrence."""
        section = _format_recent_outcomes(NARRATIONS)

        assert not re.search(r"\{[^}]*\*[^}]*\}", section), section


class TestTheHeaderDoesNotInventARound:

    def test_it_does_not_claim_a_previous_round(self):
        section = _format_recent_outcomes(NARRATIONS)

        assert "previous round" not in section.lower()

    def test_the_narrations_are_still_listed_in_order(self):
        section = _format_recent_outcomes(["first thing", "second thing"])

        assert "1. first thing" in section
        assert "2. second thing" in section
        assert section.index("1. first thing") < section.index("2. second thing")

    def test_an_empty_history_still_renders_a_section(self):
        section = _format_recent_outcomes([])

        assert "RECENT ACTION OUTCOMES" in section
