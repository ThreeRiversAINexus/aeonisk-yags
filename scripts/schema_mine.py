"""Ground-truth schema miner for the session JSONL corpus.

Motivation
----------
The session-invariant checker and the analysis tooling encode assumptions about
the event schema — which fields exist, what enum values a field can take, which
event types are authoritative. Those assumptions rot silently: the corpus grew to
40 event types while LOGGING_IMPLEMENTATION.md still documents 19, and two
invariants over-fired for weeks because they applied one subsystem's threshold to
another's differently-scaled field. A checker's rules need the same scrutiny as
the code they audit.

This miner streams the whole corpus (never loading a file whole) and reports, per
event_type, every field path that ACTUALLY occurs, its presence rate, value-type
mix, and — for low-cardinality leaves — the observed value set (enum discovery).
It turns "I think death_state can be X" into "here are the values that occur".

Two output modes:
  * default / --report : human-readable, WITH counts (for exploration).
  * --contract         : a stable, count-FREE structural schema (the frozen
    reference committed as scripts/schema_contract.json). Enum value SETS, field
    types, and event-type list only — no counts, no percentages, no freeform
    values — so it is deterministic and grows only when the schema genuinely
    changes. tests/unit/test_schema_drift.py re-mines live corpus and diffs
    against the committed contract, so drift fails CI instead of silently
    inflating an invariant tally.

Usage
-----
    python scripts/schema_mine.py [ROOT ...]                 # full report (json)
    python scripts/schema_mine.py --contract [ROOT ...]      # frozen contract (json)
    python scripts/schema_mine.py --contract --out scripts/schema_contract.json
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter, defaultdict

MAX_DISTINCT = 40   # past this a string leaf is "freeform", not an enum
MAX_DEPTH = 4       # nested-dict walk depth

# Dict parents whose keys are DATA (clock names, skill names), not schema.
# Their children collapse to a single `parent.*` field — otherwise every new
# session's fresh clock name reads as schema drift and the contract churns
# forever (mined: action_resolution.clocks had 762 distinct clock-name keys).
# Paths are relative to the event body, [] and * segments already applied.
DYNAMIC_KEY_PARENTS = {
    "clocks",                                # action_resolution
    "context.clock_sources",                 # action_resolution
    "context.clock_deltas",                  # action_resolution
    "final_state.scene_clocks",              # session_end
    "state_summary.scene_clocks",            # end_state_snapshot
    "stats.skills",                          # enemy_spawn (custom skills occur)
    "action_context.character_skills",       # pydantic_validation_failure
    "entity_states_before",                  # applied_outcome (keys are entity ids)
    "entity_states_after",                   # applied_outcome (keys are entity ids)
}

# Per-event identity/envelope fields: their values are unique by construction
# (uuids, timestamps) — pinning them as enums on rare event types made every
# new session "drift". Always freeform.
IDENTITY_FIELDS = {
    "ts", "session", "event_id", "parent_event_id", "correlation_id",
    # outcome pipeline: per-event uuids, per-session entity ids (npc ids carry
    # a session suffix), and free prose — all churn as enums
    "outcome_id", "adjudication_id", "declaration_event_id",
    "actor_id", "subject_id", "causing_actor_id", "source_outcome_id",
    "reasoning_short", "prose_safe_summary", "symbolic_value",
    "intent", "method", "text", "synthesis",
}


class FieldStat:
    __slots__ = ("present", "types", "values", "overflow", "nmin", "nmax")

    def __init__(self):
        self.present = 0
        self.types = Counter()
        self.values = Counter()
        self.overflow = False
        self.nmin = None
        self.nmax = None

    def observe(self, v):
        self.present += 1
        self.types[type(v).__name__] += 1
        if isinstance(v, bool):
            self.values[v] += 1
        elif isinstance(v, (int, float)):
            self.nmin = v if self.nmin is None else min(self.nmin, v)
            self.nmax = v if self.nmax is None else max(self.nmax, v)
        elif isinstance(v, str):
            if not self.overflow:
                self.values[v] += 1
                if len(self.values) > MAX_DISTINCT:
                    self.overflow = True
                    self.values.clear()
        elif v is None:
            self.values["<None>"] += 1


def _walk(prefix, obj, stats, depth):
    if depth > MAX_DEPTH:
        return
    if isinstance(obj, dict):
        dynamic = prefix in DYNAMIC_KEY_PARENTS
        for k, v in obj.items():
            key = "*" if dynamic else k
            path = f"{prefix}.{key}" if prefix else key
            stats[path].observe(v)
            if isinstance(v, (dict, list)):
                _walk(path, v, stats, depth + 1)
    elif isinstance(obj, list):
        for el in obj:
            _walk(prefix + "[]", el, stats, depth + 1)


def iter_session_files(roots):
    files = []
    for root in roots:
        if os.path.isdir(root):
            files += glob.glob(f"{root}/**/session_*.jsonl", recursive=True)
        elif os.path.isfile(root):
            files.append(root)
    return sorted(set(files))


def mine(roots):
    """Return (type_counts, per_type_stats, n_lines, n_files)."""
    per_type = defaultdict(lambda: defaultdict(FieldStat))
    type_counts = Counter()
    n_lines = 0
    files = iter_session_files(roots)
    for path in files:
        try:
            fh = open(path)
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(e, dict):
                    continue
                n_lines += 1
                et = e.get("event_type", "<no event_type>")
                type_counts[et] += 1
                d = e.get("data")
                body = d if isinstance(d, dict) else e
                for k in ("round", "agent", "turn", "phase"):
                    if k in e:
                        per_type[et][f"@{k}"].observe(e.get(k))
                _walk("", body, per_type[et], 1)
    return type_counts, per_type, n_lines, len(files)


def _leaf_shape(st: FieldStat):
    """Reduce a FieldStat to its stable, count-free structural shape."""
    types = sorted(st.types)
    shape = {"types": types}
    if st.nmin is not None:
        shape["numeric"] = True
    if st.overflow:
        shape["values"] = "freeform"
    elif st.values:
        # bool/str/None enum set — sorted, stable
        shape["values"] = sorted(str(v) for v in st.values)
    return shape


def build_contract(type_counts, per_type):
    """Stable, count-free structural schema for drift detection."""
    contract = {"event_types": sorted(type_counts), "schema": {}}
    for et in sorted(per_type):
        fields = {}
        for path, st in sorted(per_type[et].items()):
            shape = _leaf_shape(st)
            # Under a dynamic-key parent the VALUES are data too (clock tick
            # strings, skill ratings) — never pin them as an enum. Likewise
            # identity/envelope fields (uuids, timestamps) are unique by
            # construction.
            segs = path.split(".")
            if ("*" in segs or segs[-1] in IDENTITY_FIELDS) \
                    and isinstance(shape.get("values"), list) \
                    and "str" in shape.get("types", []):
                shape["values"] = "freeform"
            fields[path] = shape
        contract["schema"][et] = fields
    return contract


def build_report(type_counts, per_type, n_lines, n_files):
    """Human report WITH counts."""
    out = {
        "files": n_files,
        "lines": n_lines,
        "event_types": dict(type_counts.most_common()),
        "schema": {},
    }
    for et in sorted(per_type):
        tc = type_counts[et]
        fields = {}
        for path, st in sorted(per_type[et].items()):
            rec = {"present": st.present,
                   "pct": round(100 * st.present / tc, 1) if tc else 0,
                   "types": dict(st.types)}
            if st.nmin is not None:
                rec["num_range"] = [st.nmin, st.nmax]
            if st.overflow:
                rec["values"] = f"<{MAX_DISTINCT}+ distinct freeform>"
            elif st.values:
                rec["values"] = dict(st.values.most_common())
            fields[path] = rec
        out["schema"][et] = {"count": tc, "fields": fields}
    return out


def diff_contract(reference: dict, live: dict):
    """Additive drift of `live` relative to `reference`. Returns a list of human
    strings describing anything live introduces that the reference doesn't know:
    new event types, new field paths, new value types, new enum values. Shrinkage
    (present in reference, absent live) is reported separately as info — it can be
    mere sampling and does not fail the gate."""
    drift, info = [], []
    ref_ets, live_ets = set(reference["event_types"]), set(live["event_types"])
    for et in sorted(live_ets - ref_ets):
        drift.append(f"NEW event_type: {et}")
    for et in sorted(ref_ets - live_ets):
        info.append(f"absent event_type (not in live sample): {et}")

    rs, ls = reference["schema"], live["schema"]
    for et in sorted(set(ls) & set(rs)):
        rf, lf = rs[et], ls[et]
        for path in sorted(set(lf) - set(rf)):
            drift.append(f"{et}: NEW field {path} {lf[path]}")
        for path in sorted(set(rf) & set(lf)):
            r, l = rf[path], lf[path]
            new_types = set(l.get("types", [])) - set(r.get("types", []))
            if new_types:
                drift.append(f"{et}.{path}: NEW type(s) {sorted(new_types)} "
                             f"(was {r.get('types')})")
            rv, lv = r.get("values"), l.get("values")
            # only compare when reference pinned an enum (list); freeform never drifts
            if isinstance(rv, list) and isinstance(lv, list):
                new_vals = set(lv) - set(rv)
                if new_vals:
                    drift.append(f"{et}.{path}: NEW enum value(s) {sorted(new_vals)} "
                                 f"(known {rv})")
            elif isinstance(rv, list) and lv == "freeform":
                drift.append(f"{et}.{path}: enum -> freeform (cardinality exploded)")
    return drift, info


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    contract_mode = "--contract" in argv
    out_path = None
    if "--out" in argv:
        i = argv.index("--out")
        out_path = argv[i + 1]
        del argv[i:i + 2]
    for flag in ("--contract", "--report"):
        if flag in argv:
            argv.remove(flag)
    roots = argv or ["multiagent_output"]

    type_counts, per_type, n_lines, n_files = mine(roots)
    doc = (build_contract(type_counts, per_type) if contract_mode
           else build_report(type_counts, per_type, n_lines, n_files))
    text = json.dumps(doc, indent=1, sort_keys=contract_mode, default=str)
    if out_path:
        with open(out_path, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {'contract' if contract_mode else 'report'} -> {out_path} "
              f"({n_files} files, {n_lines} events, {len(type_counts)} event types)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
