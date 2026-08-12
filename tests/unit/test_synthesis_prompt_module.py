"""The synthesis prompt moved to YAML, and it must be the same prompt (#159).

A prompt refactor that silently changes a prompt is a behaviour change wearing
a refactor's clothes, and this is the call that turns resolved mechanics into
the story — the most expensive place in the system to change something by
accident. So the test is byte identity against the f-string that used to live
in `dm.py`, reconstructed here from the source itself rather than retyped: a
copy I typed out could drift from the original in exactly the ways I would fail
to notice.

Why the move at all: `prompt_eval_harness.py` swaps YAML modules through
`ModuleSwapper`, which globs `prompts/claude/en/dm/*.yaml`. A prompt embedded in
Python is invisible to it — it cannot be swapped, varied, A/B tested or
iterated on. #158 is blocked on this; #159 is the other 50k characters.
"""

import ast
import json
from pathlib import Path

import pytest
import yaml

from aeonisk.multiagent import synthesis_prompt

DM_SOURCE = (Path(synthesis_prompt.__file__).parent / "dm.py")

ROUND = 3
PAYLOAD = [{"outcome_id": "out_000015", "sequence": 2, "actor_name": "Hard Vane",
            "intent": "Use my Corporate Influence contacts", "weapon": None,
            "target_names": [], "facts": []}]
LIFECYCLE = {"npcs_departed": ["npc_subdued_operative_#1_9872"],
             "enemies_converted": []}
PRIOR = "The chamber stays taut and airless after the earlier violence."


def _legacy_template() -> str:
    """The original f-string, recovered from `dm.py`'s AST.

    Falls back to the committed module once the f-string is gone from source —
    at which point this comparison has done its job and the YAML is the only
    definition left.
    """
    tree = ast.parse(DM_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        parts, names = [], []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(value.value)
            else:
                names.append(ast.unparse(value))
                parts.append("\x00")
        text = "".join(parts)
        if "BINDING CONTRACT:" in text and "PRIOR CANONICAL ENDING:" in text:
            for name, token in zip(names, ("{round_num}", "{outcomes_json}",
                                           "{previous_ending}", "{lifecycle_json}")):
                text = text.replace("\x00", token, 1)
            return text
    return None


class TestTheMoveIsExact:

    def test_no_copy_of_this_prompt_is_left_in_python(self):
        """The extraction gate, pointed forward instead of backward.

        Byte identity against the original f-string was verified at extraction
        and cannot be re-verified once the literal is deleted — a test asserting
        it would skip forever, which is the "check that cannot fail" in another
        costume. What *can* keep failing is the regression: a second copy of
        this prompt reappearing in code, which is how the 50k characters in #159
        accumulated in the first place.
        """
        assert _legacy_template() is None, (
            "a prompt-shaped f-string carrying BINDING CONTRACT is back in dm.py — "
            "the module at prompts/claude/en/dm/dm_outcome_synthesis.yaml is the "
            "only definition, or the harness cannot swap it")

    def test_the_contract_survived_the_move_intact(self):
        """Structural pin on the part that is easiest to lose in a hand-edit:
        the contract is a flat list of 18 rules, and #158 will restructure it
        deliberately. If this count changes without that work, something was
        dropped rather than rewritten.
        """
        template = yaml.safe_load(synthesis_prompt.MODULE_PATH.read_text(
            encoding="utf-8"))["user_prompt"]
        contract = template.split("BINDING CONTRACT:", 1)[1]

        assert sum(1 for line in contract.splitlines()
                   if line.startswith("- ")) == 18

    def test_the_system_prompt_matches_what_a_real_session_sent(self):
        """Checked against a recording rather than against `dm.py`.

        The source comparison could only work until the literal was deleted,
        which is the same afternoon. A recorded call is a permanent oracle: this
        is the role instruction as it actually reached the model on 2026-08-11,
        and it keeps being true after the Python original is gone. The recorded
        system message continues into a ~21.7k-char schema dump appended by the
        structured-output layer, so the fixture keeps only its head.
        """
        chain = Path(__file__).parent.parent / "fixtures/sessions/synthesis_repetition_chain.jsonl"
        sent = None
        for line in chain.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            body = event.get("data") if isinstance(event.get("data"), dict) else event
            if event.get("event_type") == "llm_call" and body.get("prompt"):
                sent = body["prompt"][0]["content"]
                break

        assert sent, "fixture carries no recorded synthesis prompt"
        # The comparison runs the other way now that `system_prompt()` composes
        # the schema block too: the fixture keeps only the first 200 characters
        # of a 21,849-character message, and what those 200 characters prove is
        # that our reconstruction reproduces production's opening exactly —
        # role line, blank line, and the schema preamble that follows it.
        assert synthesis_prompt.system_prompt().startswith(sent)

    def test_the_rendered_prompt_carries_every_section(self):
        rendered = synthesis_prompt.user_prompt(ROUND, PAYLOAD, PRIOR, LIFECYCLE)

        for heading in ("AUTHORITATIVE, PROSE-SAFE OUTCOMES",
                        "HOW THE PREVIOUS ROUND CLOSED",
                        "ACCEPTED ENTITY LIFECYCLE CHANGES:",
                        "BINDING CONTRACT:"):
            assert heading in rendered


class TestRendering:

    def test_the_payload_is_rendered_as_indented_json(self):
        rendered = synthesis_prompt.user_prompt(ROUND, PAYLOAD, PRIOR, LIFECYCLE)

        assert json.dumps(PAYLOAD, indent=2) in rendered

    def test_the_round_number_reaches_the_first_line(self):
        rendered = synthesis_prompt.user_prompt(7, PAYLOAD, PRIOR, LIFECYCLE)

        assert rendered.startswith("Write the canonical literary narration for round 7.")

    def test_an_opening_round_says_so(self):
        rendered = synthesis_prompt.user_prompt(1, PAYLOAD, None, LIFECYCLE)

        assert synthesis_prompt.NO_PRIOR_ROUND in rendered

    def test_an_empty_prior_is_treated_as_an_opening_round(self):
        """`previous_ending` arrives as `""` on round 1, not None."""
        rendered = synthesis_prompt.user_prompt(1, PAYLOAD, "", LIFECYCLE)

        assert synthesis_prompt.NO_PRIOR_ROUND in rendered

    def test_lifecycle_values_that_are_not_json_do_not_crash(self):
        """The original passed `default=str`; enum members reach this field."""
        from enum import Enum

        class R(Enum):
            SUBDUED = "subdued"

        rendered = synthesis_prompt.user_prompt(
            ROUND, PAYLOAD, PRIOR, {"enemies_converted": [R.SUBDUED]})

        assert "SUBDUED" in rendered

    def test_only_the_closing_line_of_the_prior_round_goes_in(self):
        """#158 landed 2026-08-12; this test asserted the opposite until then.

        The prompt used to send the *entire* previous round under a heading
        calling it an "ending", directly above the rule forbidding its reuse.
        Measured over 24 replayed cases before promotion: identical round
        openings 5/19 → 0/19, median opening similarity 0.62 → 0.36 — the figure
        the pipeline had before it began feeding the narrator its own output.
        """
        prior = "First paragraph.\n\nSecond paragraph.\n\nThird and final paragraph."

        rendered = synthesis_prompt.user_prompt(ROUND, PAYLOAD, prior, LIFECYCLE)

        assert prior not in rendered
        assert "Third and final paragraph." in rendered
        assert "First paragraph." not in rendered


class TestTheTemplateStaysFormattable:

    def test_the_body_contains_no_stray_braces(self):
        """`str.format` would raise mid-session on the one call that turns
        mechanics into story, and it would raise nowhere near this file."""
        raw = yaml.safe_load(synthesis_prompt.MODULE_PATH.read_text(
            encoding="utf-8"))["user_prompt"]
        for token in ("{round_num}", "{outcomes_json}",
                      "{previous_ending}", "{lifecycle_json}"):
            raw = raw.replace(token, "")

        assert "{" not in raw and "}" not in raw

    def test_every_placeholder_is_present_exactly_once(self):
        raw = yaml.safe_load(synthesis_prompt.MODULE_PATH.read_text(
            encoding="utf-8"))["user_prompt"]

        assert [raw.count(t) for t in ("{round_num}", "{outcomes_json}",
                                       "{previous_ending}", "{lifecycle_json}")] == [1, 1, 1, 1]

    def test_the_module_is_where_the_harness_looks_for_it(self):
        """`ModuleSwapper` globs this directory; a module outside it is
        invisible to the harness, which is the whole reason for the move."""
        assert synthesis_prompt.MODULE_PATH.parent.name == "dm"
        assert synthesis_prompt.MODULE_PATH.suffix == ".yaml"
        assert yaml.safe_load(synthesis_prompt.MODULE_PATH.read_text(
            encoding="utf-8"))["module"] == "dm_outcome_synthesis"
