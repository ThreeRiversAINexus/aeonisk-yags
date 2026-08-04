"""The law-is-law binding tests: one statute, every court, no drift."""
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from aeonisk.multiagent.nexus_law import OPERATIONAL_RUBRIC, LAW_VERSION

ROOT = Path(__file__).parent.parent.parent
STATUTE = (ROOT / "content/supplemental/NEXUS_LAW.md").read_text()


def test_version_matches_statute():
    assert f"### v{LAW_VERSION}" in STATUTE


def test_every_cited_article_exists_in_statute():
    cited = set(re.findall(r'\[([IVX]+\.\d+[a-z]?|A\d\.\d)', OPERATIONAL_RUBRIC))
    assert len(cited) >= 20
    for article in cited:
        anchor = f"**{article}" if article.startswith("A") else f"**{article}**"
        assert anchor in STATUTE, f"rubric cites {article}, not found in statute"


def test_intent_rule_and_judge_error_present():
    assert "the attempt IS the offense" in OPERATIONAL_RUBRIC
    assert "JUDGE ERROR" in OPERATIONAL_RUBRIC


def test_harness_renders_the_statute():
    from datamine.fidelity_harness import NEXUS_LAW
    assert NEXUS_LAW is OPERATIONAL_RUBRIC


def test_post_adjudication_prompt_has_rubric_slot():
    data = yaml.safe_load((ROOT / "scripts/aeonisk/multiagent/prompts/claude/"
                           "en/dm/dm_post_adjudication.yaml").read_text())
    assert "{law_rubric}" in data["post_adjudication_prompt"]


def test_in_session_guidance_drift_guard():
    """dm_state_tracking is static yaml; guard its core clauses against
    drifting from the statute's until it too renders from this module."""
    guidance = (ROOT / "scripts/aeonisk/multiagent/prompts/claude/en/dm/"
                "dm_state_tracking.yaml").read_text()
    for clause in ("record tampering", "JUDGE THE DEED",
                   "Sovereign Nexus universal morality"):
        assert clause in guidance


def test_codex_nexum_identity_is_consistent():
    """The Legislator's 2026-08-04 ruling: the Codex Nexum IS the law, running.

    'Codex Nexum' formerly named both the astral computer (statute preamble,
    dm_prompt) and a governing legal *text* (Module glossary), while the law
    itself had no name of its own. The ruling: the Codex Nexum is the astral
    computer and is identical with its law; that law is the Sovereign Nexus
    Constitution. Guard both halves against re-drift.
    """
    assert "# The Sovereign Nexus Constitution" in STATUTE
    assert "The **Codex Nexum** is the astral computer" in STATUTE

    glossary = (ROOT / "content/Aeonisk - YAGS Module - v1.3.0.md").read_text()
    assert "**Sovereign Nexus Constitution:**" in glossary, (
        "the law needs its own glossary entry"
    )
    assert "**Codex Nexum:** The astral computer" in glossary
    assert "Governing legal-mnemonic text" not in glossary, (
        "the Codex Nexum is not a text; that reading was overruled"
    )
