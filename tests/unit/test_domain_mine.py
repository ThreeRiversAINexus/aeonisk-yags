"""The domain snapshot: harvest the corpus, keep the distillation.

`multiagent_output/` and `bulk_output/` are gitignored and get cleared. The
snapshot is what survives, so two properties are load-bearing:

* **merge, never replace** — harvesting after a clear must not lose what only
  the previous batch had seen. A replace would make `rm -rf bulk_output/`
  silently destroy coverage.
* **provenance survives the source** — a sample outlives its session file, so it
  carries the commit that produced it and whether that tree was dirty.

Corpus-free: every event here is synthetic.
"""

import json

import pytest

from scripts.domain_mine import (
    build_snapshot, harvest_events, merge_snapshots,
)


def start(commit="c50e2b3", session="s1"):
    return {"event_type": "session_start", "session": session,
            "git_commit": commit, "config": {}}


def cstate(health=26, wounds=0, stuns=0, name="Nera"):
    return {"event_type": "character_state", "round": 1,
            "data": {"character_name": name, "health": health, "max_health": 26,
                     "wounds": wounds, "stuns": stuns, "void_score": 0,
                     "soulcredit": 0, "is_defeated": False,
                     "death_state": "alive", "agent": "player"}}


def ko(stuns=10, wounds=3, health_attr=3, roll=8, dc=40, total=14):
    return {"event_type": "ko_check", "round": 1, "name": "Nera",
            "side": "player", "stuns": stuns, "wounds": wounds,
            "health_attr": health_attr, "roll": roll, "dc": dc, "total": total,
            "can_act": False, "status": "unconscious"}


class TestHarvest:

    def test_collects_joint_body_tuples(self):
        snap = harvest_events([[start(), cstate(health=20, wounds=1, stuns=2)]])

        assert [20, 1, 2] in snap["samples"]["body_states"]

    def test_deduplicates_repeated_states(self):
        """4,166 real rows collapse to ~134 tuples; the snapshot keeps tuples."""
        events = [start()] + [cstate(health=26, wounds=0, stuns=0)] * 50

        snap = harvest_events([events])

        assert snap["samples"]["body_states"].count([26, 0, 0]) == 1

    def test_keeps_ko_rows_whole(self):
        """Oracle rows are not deduplicated to a tuple: the logged outputs are
        the expected values and must travel with their inputs."""
        row = harvest_events([[start(), ko()]])["samples"]["ko_check"][0]

        assert row["dc"] == 40 and row["status"] == "unconscious"

    def test_records_provenance(self):
        snap = harvest_events([[start(commit="c50e2b3"), cstate()]])

        assert snap["provenance"]["sessions"] == 1
        assert "c50e2b3" in snap["provenance"]["commits"]

    def test_counts_dirty_sessions(self):
        snap = harvest_events([[start(commit="54243cd-dirty"), cstate()]])

        assert snap["provenance"]["dirty_sessions"] == 1

    def test_derives_numeric_domains(self):
        snap = harvest_events([[start(), cstate(health=0), cstate(health=55)]])

        assert snap["domains"]["health"]["min"] == 0
        assert snap["domains"]["health"]["max"] == 55


class TestMergeIsTheDefault:
    """The property that makes clearing a corpus directory safe."""

    def test_union_of_samples(self):
        a = harvest_events([[start(session="a"), cstate(health=20)]])
        b = harvest_events([[start(session="b"), cstate(health=30)]])

        merged = merge_snapshots(a, b)

        states = merged["samples"]["body_states"]
        assert [20, 0, 0] in states and [30, 0, 0] in states

    def test_a_later_harvest_never_drops_earlier_coverage(self):
        """The exact scenario: harvest, clear bulk_output/, harvest again."""
        first = harvest_events([[start(session="gone"), cstate(health=55)]])
        second = harvest_events([[start(session="kept"), cstate(health=26)]])

        merged = merge_snapshots(first, second)

        assert [55, 0, 0] in merged["samples"]["body_states"], \
            "coverage from a deleted batch was lost"

    def test_domains_widen_across_harvests(self):
        a = harvest_events([[start(), cstate(health=26)]])
        b = harvest_events([[start(), cstate(health=0)]])

        merged = merge_snapshots(a, b)

        assert merged["domains"]["health"]["min"] == 0
        assert merged["domains"]["health"]["max"] == 26

    def test_provenance_accumulates(self):
        a = harvest_events([[start(commit="aaa1111", session="a"), cstate()]])
        b = harvest_events([[start(commit="bbb2222", session="b"), cstate()]])

        merged = merge_snapshots(a, b)

        assert set(merged["provenance"]["commits"]) == {"aaa1111", "bbb2222"}
        assert merged["provenance"]["sessions"] == 2

    def test_merging_the_same_harvest_twice_is_idempotent(self):
        """Re-running a harvest must not inflate the snapshot."""
        a = harvest_events([[start(), cstate(), ko()]])

        once = merge_snapshots(a, a)

        assert len(once["samples"]["body_states"]) == \
            len(a["samples"]["body_states"])
        assert len(once["samples"]["ko_check"]) == len(a["samples"]["ko_check"])

    def test_re_mining_the_same_sessions_does_not_inflate_the_count(self):
        """Counting by increment made a re-harvest report 660 sessions over the
        same 330 files. The snapshot would then overstate how much evidence
        backs it — a silently wrong number, which is the whole thing this
        effort exists to catch. Sessions are identified, not tallied.
        """
        a = harvest_events([[start(session="s1"), cstate()]])

        twice = merge_snapshots(a, a)

        assert twice["provenance"]["sessions"] == 1

    def test_distinct_sessions_still_add_up(self):
        a = harvest_events([[start(session="s1"), cstate()]])
        b = harvest_events([[start(session="s2"), cstate()]])

        assert merge_snapshots(a, b)["provenance"]["sessions"] == 2

    def test_dirty_counts_are_deduplicated_too(self):
        a = harvest_events([[start(commit="abc-dirty", session="s1"), cstate()]])

        assert merge_snapshots(a, a)["provenance"]["dirty_sessions"] == 1

    def test_per_commit_session_counts_are_deduplicated(self):
        a = harvest_events([[start(commit="abc1234", session="s1"), cstate()]])

        twice = merge_snapshots(a, a)

        assert twice["provenance"]["commits"]["abc1234"]["sessions"] == 1


class TestSnapshotFile:

    def test_round_trips_through_json(self, tmp_path):
        """It is committed to git, so it has to be plain serialisable JSON."""
        snap = harvest_events([[start(), cstate(), ko()]])
        path = tmp_path / "domain_corpus.json"

        path.write_text(build_snapshot(snap))

        assert json.loads(path.read_text())["samples"]["ko_check"]

    def test_is_stable_across_builds(self):
        """Sorted output: a re-harvest of identical data must not churn the
        committed file, or every run shows a spurious diff."""
        snap = harvest_events([[start(), cstate(health=30), cstate(health=10)]])

        assert build_snapshot(snap) == build_snapshot(snap)

    def test_carries_a_schema_version(self):
        snap = harvest_events([[start(), cstate()]])

        assert snap["schema_version"]
