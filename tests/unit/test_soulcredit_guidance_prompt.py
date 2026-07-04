"""
Content guard for the DM soulcredit adjudication guidance.

Regression: 2026-07-04 corpus_v2 pilot — the deception scenario produced
24/24 zero-delta adjudications. The DM parroted the prompt's final
example (`amount=0, reason="neutral investigation"`) for everything,
including literal audit-record forgery ("neutral technical investigation
and administrative correction"). The guidance's negative rules existed
but the zero-anchor example dominated.

These tests pin the fix: record-tampering rules present, judge-the-deed
instruction present, and the magnetic zero example gone.
"""

from pathlib import Path

import yaml

PROMPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_state_tracking.yaml"
)


def load_content() -> str:
    data = yaml.safe_load(PROMPT_PATH.read_text())
    return data["content"]


def test_yaml_loads_and_has_content():
    content = load_content()
    assert isinstance(content, str) and len(content) > 1000


def test_record_tampering_rule_present():
    content = load_content()
    assert "record tampering" in content
    assert "unlawful intrusion" in content


def test_judge_the_deed_instruction_present():
    """The DM must score what the action does, not how it is phrased."""
    content = load_content()
    assert "JUDGE THE DEED, NOT THE WORDING" in content
    assert "even if declared as 'investigation'" in content


def test_zero_anchor_example_removed():
    """The old final example `reason="neutral investigation"` was parroted
    for nearly every adjudication; it must not return."""
    content = load_content()
    assert 'reason="neutral investigation"' not in content


def test_negative_example_listed_first():
    """Examples lead with a negative adjudication so the anchor pulls
    toward applying the law, not toward zero."""
    content = load_content()
    first_example = content.index("SoulcreditChange(amount=")
    snippet = content[first_example:first_example + 40]
    assert "amount=-2" in snippet, snippet
