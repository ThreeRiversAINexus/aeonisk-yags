"""What `golden` has to mean before a fixture may claim it.

Four fixtures are named `golden_*`. Three of them fail the invariant checkers,
one by twelve findings, and nothing noticed — the prefix was a filename, not a
promise. Meanwhile `session_invariants.py tests/fixtures/sessions` was itself
reporting "Scanned 5 session(s)" over a directory of twelve, so even a person
who looked was shown a clean answer.

So the standard is stated here and enforced from the MANIFEST flag rather than
the filename:

  * complete — a session that reached `session_end`, because the terminal
    checkers (duplicate_session_end, snapshot_oracle_mismatch,
    enforce_ruling_dropped) cannot fire on an extract, and "all fixtures pass"
    was absence of evidence rather than evidence of absence;
  * zero ERROR-severity findings from `session_invariants.check_file`.

The gate is only worth having if it can say no, which is why
`harm_unrecorded_chain.jsonl` is kept deliberately dirty and asserted so: it is
#150's evidence, and it is the control that proves the gate discriminates.
"""

import json
from pathlib import Path

import pytest

from scripts.session_invariants import ERROR, check_file, load

FIXTURES = Path(__file__).parent.parent / "fixtures/sessions"
MANIFEST = FIXTURES / "MANIFEST.json"

_manifest = json.loads(MANIFEST.read_text())["fixtures"]
GOLDEN = sorted(n for n, meta in _manifest.items() if meta.get("golden"))


def test_something_is_actually_tagged_golden():
    """Anti-vacuity. A parametrised gate over an empty list passes forever, and
    would go on passing through the promotion it exists to guard."""
    assert GOLDEN, "no fixture carries golden:true — the gate below checks nothing"


@pytest.mark.parametrize("name", GOLDEN)
class TestEveryGoldenFixture:

    def test_exists(self, name):
        assert (FIXTURES / name).is_file()

    def test_has_no_error_severity_findings(self, name):
        found = [v for v in check_file(str(FIXTURES / name)) if v.severity == ERROR]

        assert not found, "\n".join(
            f"  {v.invariant} r{v.round} [{v.entity}]: {v.message}" for v in found)

    def test_is_a_complete_session_not_an_extract(self, name):
        kinds = [e.get("event_type") for e in load(str(FIXTURES / name))]

        assert kinds.count("session_end") == 1, (
            f"{name} has {kinds.count('session_end')} session_end events; the "
            f"terminal invariants can only be trusted on a whole session")


class TestTheGateCanSayNo:
    """The control. Without it, a gate that stopped checking anything would
    still be green."""

    DIRTY = "harm_unrecorded_chain.jsonl"

    def test_the_bug_fixture_is_not_tagged_golden(self):
        assert _manifest[self.DIRTY]["golden"] is False

    def test_the_bug_fixture_still_fails_the_standard(self):
        found = [v for v in check_file(str(FIXTURES / self.DIRTY))
                 if v.severity == ERROR]

        assert [v.invariant for v in found] == ["harm_unrecorded"]


class TestTheManifestDescribesWhatIsOnDisk:
    """Fixtures and manifest drift apart silently; each direction hides
    something different."""

    def test_every_fixture_file_has_an_entry(self):
        on_disk = {p.name for p in FIXTURES.glob("*.jsonl")}

        assert on_disk - set(_manifest) == set()

    def test_every_entry_has_a_file(self):
        assert {n for n in _manifest if not (FIXTURES / n).is_file()} == set()

    def test_the_golden_prefix_is_not_the_standard(self):
        """Stated as a test so nobody re-derives the wrong rule from the names:
        three `golden_*` fixtures do not meet the bar, and they still do not."""
        prefixed = {p.name for p in FIXTURES.glob("golden_*.jsonl")}

        assert prefixed - set(GOLDEN), (
            "every golden_*-named fixture now passes — delete this test and the "
            "distinction it was drawing")
