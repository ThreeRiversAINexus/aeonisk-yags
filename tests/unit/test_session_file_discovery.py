"""Both corpus tools must find every session file, and only session files.

`session_invariants.py` and `schema_mine.py` each globbed `session_*.jsonl`, so
a session whose filename did not start with `session_` was skipped in silence.
That hid 7 of the 12 fixtures — including all four goldens — from both tools:
`session_invariants.py tests/fixtures/sessions` reported "Scanned 5 session(s)"
and never mentioned the rest, and the frozen schema contract had never seen a
golden fixture event.

Filename is the wrong test. `evals/rules_fidelity/*.jsonl` are `.jsonl` files
that are not sessions at all, so a bare `*.jsonl` glob is equally wrong in the
other direction. Content decides: a session file carries `event_type` records.

The two tools discover files independently, so the last test here pins them to
the same answer — divergence between them is what produced the original hole.
"""

import json

import pytest

from scripts.schema_mine import iter_session_files
from scripts.session_invariants import _iter_sessions


@pytest.fixture
def corpus(tmp_path):
    """A directory holding both real sessions and lookalike non-sessions."""
    (tmp_path / "session_abc.jsonl").write_text(
        json.dumps({"event_type": "session_start"}) + "\n")
    (tmp_path / "golden_lawful_arrest_complete.jsonl").write_text(
        json.dumps({"event_type": "session_start"}) + "\n" +
        json.dumps({"event_type": "session_end"}) + "\n")
    (tmp_path / "negative_health_bug.jsonl").write_text(
        json.dumps({"event_type": "action_resolution", "round": 1}) + "\n")

    # Not sessions: eval responses carry no event_type.
    (tmp_path / "responses_gpt.jsonl").write_text(
        json.dumps({"id": 1, "prompt": "x", "completion": "y"}) + "\n")
    (tmp_path / "items.jsonl").write_text(json.dumps({"item": "a"}) + "\n")
    (tmp_path / "notes.txt").write_text("not jsonl at all\n")
    return tmp_path


def names(paths):
    import os
    return {os.path.basename(p) for p in paths}


class TestDiscovery:

    def test_finds_sessions_not_named_session(self, corpus):
        """The exact hole: all four goldens were invisible to both tools."""
        found = names(iter_session_files([str(corpus)]))

        assert "golden_lawful_arrest_complete.jsonl" in found
        assert "negative_health_bug.jsonl" in found

    def test_still_finds_conventionally_named_sessions(self, corpus):
        assert "session_abc.jsonl" in names(iter_session_files([str(corpus)]))

    def test_ignores_jsonl_that_is_not_a_session(self, corpus):
        """`evals/rules_fidelity/*.jsonl` must not be mined as game events."""
        found = names(iter_session_files([str(corpus)]))

        assert "responses_gpt.jsonl" not in found
        assert "items.jsonl" not in found

    def test_ignores_non_jsonl(self, corpus):
        assert "notes.txt" not in names(iter_session_files([str(corpus)]))

    def test_an_explicit_file_path_is_always_honoured(self, corpus):
        """Naming a file directly overrides the sniff — the user asked for it."""
        target = str(corpus / "responses_gpt.jsonl")

        assert list(iter_session_files([target])) == [target]


class TestBothToolsAgree:

    def test_same_files_for_the_same_directory(self, corpus):
        assert names(_iter_sessions([str(corpus)])) == \
            names(iter_session_files([str(corpus)]))

    def test_both_cover_every_real_fixture(self):
        from pathlib import Path

        fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"
        if not fixtures.exists():
            pytest.skip("fixtures not present")
        # rglob: five more fixtures live in sessions/golden_seed/
        on_disk = {p.name for p in fixtures.rglob("*.jsonl")}

        assert names(_iter_sessions([str(fixtures)])) == on_disk
        assert names(iter_session_files([str(fixtures)])) == on_disk
