"""Guard the vectorstore's canon source list against filename drift.

The rule file list previously pointed at `ai_pack/core.md`, `ai_pack/character.md`
and `ai_pack/scifitech.md` (archived in Oct 2025) plus a set of v1.2.1 content
files that had since been superseded by v1.3.0. Every path silently failed the
`.exists()` check at load time, so the vectorstore populated from nothing.
"""

from pathlib import Path

import pytest

from scripts.aeonisk.multiagent.vectorstore_system import RULE_FILES

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_rule_files_is_not_empty():
    assert RULE_FILES, "vectorstore has no canon sources to ingest"


@pytest.mark.parametrize("rule_file", RULE_FILES)
def test_rule_file_exists(rule_file):
    assert (REPO_ROOT / rule_file).is_file(), (
        f"{rule_file} does not exist; the vectorstore would skip it silently"
    )


def test_rule_files_cover_the_four_core_documents():
    """Module, lore, gear and tactical must all be ingested."""
    joined = " ".join(RULE_FILES)
    for required in ("YAGS Module", "System Neutral Lore", "Gear & Tech", "Tactical Module"):
        assert required in joined, f"vectorstore is missing {required}"
