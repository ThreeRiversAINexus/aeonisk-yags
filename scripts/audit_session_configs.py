#!/usr/bin/env python3
"""Audit shipped session configs against the config-schema registry.

Read-only diagnostic — writes nothing, changes no configs. For every config under
the given root it reports:

  * recommended-deviation : effective value differs from the research-recommended
                            value (tactical / enemy / outcome-first should be ON) —
                            the "disabled but should be enabled" report;
  * deprecated            : deprecated keys still in use (with the replacement);
  * vestigial             : keys the engine never reads but the config sets
                            (a false sense of control);
  * unknown               : top-level keys not in the schema and not documentation
                            (`_`-prefixed / provenance) keys — likely typos;
  * validator-error       : whatever validate_session_config() flags.

Usage:
    python scripts/audit_session_configs.py [ROOT ...] [--json] [--only-issues]

Defaults to ROOT = scripts/session_configs.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# Make the package importable whether run from repo root or scripts/.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from aeonisk.multiagent import config_schema as cs  # noqa: E402
from aeonisk.multiagent.launch_config import validate_session_config  # noqa: E402


# JSON files that live under session_configs/ but are not session configs.
# Auditing them produced phantom "missing session_name" errors and phantom
# unknown keys (a manifest's own fields), which drowned out real findings.
NON_CONFIG_BASENAMES = {
    "character_library.json",   # shared character library
    "manifest.json",            # bulk-run manifest
}
NON_CONFIG_PREFIXES = (
    "pricing_",                 # pricing/batch bookkeeping, e.g. pricing_batch_*.json
)


def _is_session_config(path: str) -> bool:
    name = os.path.basename(path)
    return name not in NON_CONFIG_BASENAMES and not name.startswith(NON_CONFIG_PREFIXES)


def _iter_configs(roots):
    files = []
    for root in roots:
        if os.path.isdir(root):
            files += glob.glob(f"{root}/**/*.json", recursive=True)
        elif os.path.isfile(root):
            files.append(root)
    return sorted(f for f in set(files) if _is_session_config(f))


def audit_config(config: dict, path: str) -> dict:
    """Return a findings dict for one parsed config."""
    findings = {
        "recommended_deviation": [],
        "enforce_without_teeth": [],
        "deprecated": [],
        "vestigial": [],
        "unknown": [],
        "validator_error": [],
    }

    # (a) recommended deviations — effective value vs recommended
    for key, rec in cs.recommended_overrides().items():
        spec = cs.by_path(key)
        default = spec.default if spec else None
        effective = config.get(key, default)
        if effective != rec:
            findings["recommended_deviation"].append(
                f"{key}={effective!r} (recommended {rec!r})")

    # (a2) enforce is on but nothing gates SC → records but does not deter (regime B, not C)
    if config.get("post_resolution_adjudication") == "enforce" and not cs.has_teeth(config):
        findings["enforce_without_teeth"].append(
            "post_resolution_adjudication='enforce' but no SC-gated checkpoint or "
            "contract-lock weapon — ledger moves but does not bite")

    # (b) deprecated keys in use
    if "_scenario_hint" in config:
        findings["deprecated"].append(
            f"_scenario_hint -> {cs.deprecations().get('_scenario_hint', 'scenario_hint')}")
    scenario = config.get("scenario")
    if isinstance(scenario, dict) and "initial_clocks" in scenario:
        findings["deprecated"].append(
            f"scenario.initial_clocks -> {cs.deprecations().get('scenario.initial_clocks', 'starting_clocks')}")
    agents = config.get("agents")
    if isinstance(agents, dict):
        if "enemy_agents" in agents:
            findings["deprecated"].append(
                f"agents.enemy_agents -> {cs.deprecations().get('agents.enemy_agents', 'agents.enemies')}")
        for player in (agents.get("players") or []):
            if isinstance(player, dict) and "void_score" in player:
                findings["deprecated"].append(
                    f"agents.players[].void_score -> {cs.deprecations().get('agents.players[].void_score', 'void')}")
                break

    # (c) vestigial keys set but engine-ignored
    eac = config.get("enemy_agent_config")
    if isinstance(eac, dict):
        for vpath in cs.vestigial_keys():
            leaf = vpath.split(".")[-1]
            if leaf in eac:
                findings["vestigial"].append(vpath)

    # (d) unknown top-level keys (typos / dead options), whitelisting doc keys
    known = cs.top_level_keys()
    for key in config:
        if key in known or cs.is_meta_key(key):
            continue
        findings["unknown"].append(key)

    # (e) validator errors
    findings["validator_error"] = validate_session_config(config, path=path)

    return findings


def _has_issues(findings: dict) -> bool:
    return any(findings[k] for k in findings)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*", default=["scripts/session_configs"],
                    help="Config files or directories (default: scripts/session_configs).")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    ap.add_argument("--only-issues", action="store_true",
                    help="Only list configs that have at least one finding.")
    args = ap.parse_args(argv)

    roots = args.roots or ["scripts/session_configs"]
    files = _iter_configs(roots)

    report = {}
    totals = {"recommended_deviation": 0, "enforce_without_teeth": 0, "deprecated": 0,
              "vestigial": 0, "unknown": 0, "validator_error": 0, "configs": 0, "clean": 0,
              "unparseable": 0}
    # Per-recommended-key tallies for the sanity check.
    rec_off = {k: 0 for k in cs.recommended_overrides()}

    for path in files:
        totals["configs"] += 1
        try:
            with open(path) as fh:
                config = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            totals["unparseable"] += 1
            report[path] = {"error": f"unparseable: {e}"}
            continue
        if not isinstance(config, dict):
            totals["unparseable"] += 1
            report[path] = {"error": "not a JSON object"}
            continue

        findings = audit_config(config, path)
        for k in rec_off:
            spec = cs.by_path(k)
            default = spec.default if spec else None
            if config.get(k, default) != cs.recommended_overrides()[k]:
                rec_off[k] += 1
        for k in totals:
            if k in findings and findings[k]:
                totals[k] += 1
        if _has_issues(findings):
            report[path] = findings
        else:
            totals["clean"] += 1

    if args.json:
        print(json.dumps({"totals": totals, "recommended_off": rec_off,
                          "report": report}, indent=2, default=str))
        return 0

    # Text output
    rel = lambda p: os.path.relpath(p)
    for path in files:
        findings = report.get(path)
        if findings is None:
            if not args.only_issues:
                print(f"✓ {rel(path)}")
            continue
        if "error" in findings:
            print(f"✗ {rel(path)}: {findings['error']}")
            continue
        print(f"● {rel(path)}")
        labels = {
            "recommended_deviation": "recommended",
            "enforce_without_teeth": "no-teeth",
            "deprecated": "deprecated",
            "vestigial": "vestigial",
            "unknown": "unknown-key",
            "validator_error": "VALIDATOR",
        }
        for key, label in labels.items():
            for item in findings[key]:
                print(f"    [{label}] {item}")

    print("\n" + "=" * 60)
    print(f"Configs scanned      : {totals['configs']}")
    print(f"Clean                : {totals['clean']}")
    print(f"Unparseable          : {totals['unparseable']}")
    print(f"With recommended-off : {totals['recommended_deviation']}")
    print(f"Enforce w/o teeth    : {totals['enforce_without_teeth']}")
    print(f"With deprecated keys : {totals['deprecated']}")
    print(f"With vestigial keys  : {totals['vestigial']}")
    print(f"With unknown keys    : {totals['unknown']}")
    print(f"With validator errors: {totals['validator_error']}")
    print("\nRecommended-OFF by flag:")
    for k, n in rec_off.items():
        print(f"  {k:28s} off in {n}/{totals['configs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
