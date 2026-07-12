#!/usr/bin/env python3
"""Contract replay — token-free schema verification of recorded LLM decisions.

Phase 2 of the replay plan (the mechanics-diff harness is Phase 1). After a
prompt/schema change, this answers "do the decisions we already recorded still
satisfy the CURRENT contracts?" without running a session or paying for a
single LLM call: each structured llm_call's cached response is re-validated
against the current Pydantic model named by its `call_type` tag
("structured:<SchemaName>", stamped at record time).

Each recorded decision is checked INDEPENDENTLY — no chaining, no divergence
propagation — the same soundness principle as the mechanics-diff harness.

Honest accounting: unknown schema names, unparseable responses, and untagged
legacy events are counted and reported, never silently passed. (Sessions
recorded before the call_type tag shipped are all "untagged" — expected.)

Usage:
    python scripts/contract_replay.py session.jsonl [more.jsonl ...]
    python scripts/contract_replay.py --corpus multiagent_output/
    python scripts/contract_replay.py --json session.jsonl

Exit code is non-zero if any tagged structured response fails validation
(schema breakage), so it can gate CI after a schema edit.
"""
from __future__ import annotations

import argparse
import glob
import importlib
import inspect
import json
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

# Modules OUTSIDE the schemas package that define result_type models.
# (SimpleNarration is function-local in dm.py and cannot be imported — it will
# surface as unknown_schema, which is the honest outcome.)
_EXTRA_MODULES = (
    "aeonisk.multiagent.post_adjudication",   # PostRulings
    "aeonisk.multiagent.round_assessment",    # RoundAssessment
    "aeonisk.multiagent.npc_agent",           # NPCAction
)


def build_registry() -> Dict[str, Type[BaseModel]]:
    """Map schema name -> current Pydantic model class.

    Walks the aeonisk.multiagent.schemas package plus the known extra modules.
    Name collisions keep the schemas-package definition (canonical home).
    """
    registry: Dict[str, Type[BaseModel]] = {}

    def scan(module) -> None:
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModel) and obj is not BaseModel:
                registry.setdefault(name, obj)

    import aeonisk.multiagent.schemas as pkg
    for m in pkgutil.iter_modules(pkg.__path__):
        scan(importlib.import_module(f"aeonisk.multiagent.schemas.{m.name}"))
    for modname in _EXTRA_MODULES:
        try:
            scan(importlib.import_module(modname))
        except Exception:
            pass  # a heavy module failing to import must not kill the tool
    return registry


@dataclass
class CallResult:
    status: str                 # ok | invalid | unknown_schema | skipped_text | untagged
    agent: Optional[str] = None
    seq: Optional[int] = None
    round: Optional[int] = None
    schema: Optional[str] = None
    error: Optional[str] = None

    def __str__(self) -> str:
        r = f"r{self.round}" if self.round is not None else "r?"
        return (f"{self.status:14s} {r} [{self.agent} #{self.seq}] "
                f"{self.schema or ''}: {self.error or ''}").rstrip(": ")


@dataclass
class Report:
    ok: int = 0
    invalid: int = 0
    unknown_schema: int = 0
    skipped_text: int = 0
    untagged: int = 0
    failures: List[CallResult] = field(default_factory=list)
    unknown: List[CallResult] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return self.invalid > 0


def check_call(event: Dict[str, Any], registry: Dict[str, Type[BaseModel]]) -> CallResult:
    """Validate one recorded llm_call against the current schema it was made for."""
    base = dict(agent=event.get("agent_id"), seq=event.get("call_sequence"),
                round=event.get("round"))
    call_type = event.get("call_type")
    if call_type is None:
        return CallResult("untagged", **base)
    if not call_type.startswith("structured:"):
        return CallResult("skipped_text", **base)

    schema_name = call_type.split(":", 1)[1]
    model = registry.get(schema_name)
    if model is None:
        return CallResult("unknown_schema", schema=schema_name, **base)

    response = event.get("response") or ""
    try:
        model.model_validate_json(response)
    except Exception as e:
        # first line of the pydantic error is the useful summary
        return CallResult("invalid", schema=schema_name,
                          error=str(e).splitlines()[0][:200], **base)
    return CallResult("ok", schema=schema_name, **base)


def replay_events(events: List[Dict[str, Any]],
                  registry: Optional[Dict[str, Type[BaseModel]]] = None) -> Report:
    reg = registry if registry is not None else build_registry()
    rep = Report()
    for e in events:
        if e.get("event_type") != "llm_call":
            continue
        res = check_call(e, reg)
        setattr(rep, res.status, getattr(rep, res.status) + 1)
        if res.status == "invalid":
            rep.failures.append(res)
        elif res.status == "unknown_schema":
            rep.unknown.append(res)
    return rep


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Token-free schema verification of recorded LLM decisions.")
    ap.add_argument("sessions", nargs="*", help="session JSONL file(s)")
    ap.add_argument("--corpus", metavar="DIR", action="append", default=[],
                    help="also check every *.jsonl under DIR (repeatable)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    paths = list(args.sessions)
    for d in args.corpus:
        paths.extend(sorted(glob.glob(str(Path(d) / "*.jsonl"))))
    if not paths:
        ap.error("no sessions given (positional files and/or --corpus DIR)")

    registry = build_registry()
    agg = Report()
    per_file: Dict[str, Report] = {}
    for p in paths:
        rep = replay_events(load_jsonl(p), registry)
        per_file[p] = rep
        for f_ in ("ok", "invalid", "unknown_schema", "skipped_text", "untagged"):
            setattr(agg, f_, getattr(agg, f_) + getattr(rep, f_))
        agg.failures.extend(rep.failures)
        agg.unknown.extend(rep.unknown)

    if args.json:
        print(json.dumps({
            "ok": agg.ok, "invalid": agg.invalid,
            "unknown_schema": agg.unknown_schema,
            "skipped_text": agg.skipped_text, "untagged": agg.untagged,
            "failures": [f.__dict__ for f in agg.failures],
        }, indent=2))
        return 1 if agg.has_failures else 0

    for p, r in per_file.items():
        if not (r.ok or r.invalid or r.unknown_schema or r.untagged):
            continue
        tag = "clean" if not r.has_failures else f"{r.invalid} INVALID"
        print(f"  ok={r.ok:3} invalid={r.invalid:2} unknown={r.unknown_schema:2} "
              f"text={r.skipped_text:3} untagged={r.untagged:3}  {tag:12s} {Path(p).name}")
        for f_ in r.failures:
            print(f"      {f_}")
        for u in r.unknown[:3]:
            print(f"      {u}")

    print(f"\n{agg.ok} validated ok, {agg.invalid} invalid, "
          f"{agg.unknown_schema} unknown schema, {agg.skipped_text} text, "
          f"{agg.untagged} untagged (pre-call_type recordings) "
          f"across {len(paths)} session(s).")
    if agg.has_failures:
        print("✗ schema breakage: recorded decisions no longer satisfy current contracts.")
    else:
        print("✓ every tagged structured decision satisfies the current schemas.")
    return 1 if agg.has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
