"""A content document's filename version must match the version inside it.

The Gear & Tech Reference shipped as `v1.2.2.md` while its header read
`Version 1.2.4`, because code resolved it by filename and nobody wanted to
touch the references. An external review read the mismatch as sloppiness, which
was fair — a pinned filename is invisible to anyone holding the document.
Renaming is cheap; the divergence is what costs. This test keeps them together.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT = REPO_ROOT / "content"

FILENAME_VERSION = re.compile(r" - v(\d+\.\d+\.\d+)\.md$")
INTERNAL_VERSION = re.compile(r"^\*{0,2}Version (\d+\.\d+\.\d+)\*{0,2}$", re.MULTILINE)


def versioned_documents():
    return sorted(p for p in CONTENT.rglob("*.md") if FILENAME_VERSION.search(p.name))


def test_there_are_versioned_documents():
    assert versioned_documents(), "no version-stamped canon documents found"


@pytest.mark.parametrize("doc", versioned_documents(), ids=lambda p: p.name)
def test_filename_version_matches_internal_version(doc):
    filename_version = FILENAME_VERSION.search(doc.name).group(1)
    found = INTERNAL_VERSION.search(doc.read_text())
    assert found, f"{doc.name} carries no 'Version X.Y.Z' line"
    assert found.group(1) == filename_version, (
        f"{doc.name} is named v{filename_version} but declares "
        f"Version {found.group(1)} inside"
    )


def test_no_stale_version_references_in_repo():
    """Every content path referenced elsewhere must actually resolve."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.split("\n")

    referenced = set()
    # Canon filenames contain spaces ("Aeonisk - YAGS Module - v1.4.0.md"), so the
    # path body must allow them — an earlier version of this pattern excluded
    # whitespace and therefore matched none of the documents it was guarding.
    pattern = re.compile(r"content/[A-Za-z0-9 &_./-]*? - v\d+\.\d+\.\d+\.md")
    for rel in tracked:
        if not rel or Path(rel).suffix not in {".py", ".md", ".yaml", ".yml", ".json"}:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            referenced.update(pattern.findall(path.read_text()))
        except (UnicodeDecodeError, OSError):
            continue

    missing = sorted(r for r in referenced if not (REPO_ROOT / r).is_file())
    assert not missing, f"references point at documents that do not exist: {missing}"
