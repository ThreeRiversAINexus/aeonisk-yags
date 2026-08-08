"""Regression guard: dm.py must NOT manually advance the LLM logger's call_count.

`LLMCallLogger._log_llm_call` is the single stamp+increment authority (see
test_call_sequence_logging). Every DM LLM call reaches it — either directly
(`self.llm_logger._log_llm_call(...)`) or indirectly via
`generate_structured` → `openai_structured` → `_log_llm_call`. So any
`self.llm_logger.call_count += 1` in dm.py double-counts, which produced the
gappy DM sequence (0,2,4,5,7,8,…) — every other call_sequence never emitted,
poisoning the replay cache key.

This test fails if the antipattern is reintroduced.
"""
import re
from pathlib import Path

DM_PATH = Path(__file__).resolve().parents[2] / "scripts" / "aeonisk" / "multiagent" / "dm.py"


def test_no_manual_call_count_mutation_in_dm():
    src = DM_PATH.read_text()
    offenders = [
        (i + 1, line.strip())
        for i, line in enumerate(src.splitlines())
        # any assignment/increment to a logger's call_count is forbidden
        if re.search(r"\.call_count\s*(\+=|-=|=)\s*", line)
        and "call_count ==" not in line  # allow comparisons
    ]
    assert offenders == [], (
        "dm.py must not mutate call_count manually — _log_llm_call owns it. "
        f"Offending lines: {offenders}"
    )
