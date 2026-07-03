"""
Versioning reliability: the JSONL session_start git_commit stamp must flag a dirty
working tree so it can't silently claim a clean commit the running code didn't match.
"""

from unittest.mock import MagicMock, patch

from aeonisk.multiagent.mechanics import JSONLLogger


def _run_factory(porcelain: str):
    """Build a subprocess.run stand-in: rev-parse -> sha, status --porcelain -> given."""
    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "rev-parse" in cmd:
            result.stdout = "abc1234\n"
        elif "status" in cmd:
            result.stdout = porcelain
        else:
            result.stdout = ""
        return result
    return fake_run


def test_git_commit_clean_tree_is_bare_sha(tmp_path):
    logger = JSONLLogger("sess", str(tmp_path))
    with patch("subprocess.run", side_effect=_run_factory("")):
        assert logger._get_git_commit() == "abc1234"


def test_git_commit_dirty_tree_is_flagged(tmp_path):
    logger = JSONLLogger("sess", str(tmp_path))
    with patch("subprocess.run", side_effect=_run_factory(" M scripts/foo.py\n")):
        assert logger._get_git_commit() == "abc1234-dirty"
