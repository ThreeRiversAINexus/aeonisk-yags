#!/usr/bin/env python3
"""
Build strict DM fine-tune datasets from Aeonisk YAGS JSONL sessions.

This tool intentionally treats raw session logs as untrusted training material.
It first applies the existing bulk validators, then extracts only clean DM
action-resolution calls that can be paired with a completed action_resolution
event.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from datamine import BulkValidator  # noqa: E402
from datamine.types import ValidationResult, ValidatorType  # noqa: E402


ACTION_PHASES = {"adjudicate"}
DEFAULT_PATTERN = "session_*.jsonl"


@dataclass
class SourceSession:
    path: Path
    validation: ValidationResult
    events: List[Dict[str, Any]]
    session_id: str
    session_name: Optional[str]
    git_commit: Optional[str]
    game_version: Optional[str]
    dm_provider: Optional[str]
    dm_model: Optional[str]
    player_provider: Optional[str]
    player_model: Optional[str]
    prompt_versions: Counter = field(default_factory=Counter)
    scenario_family: Optional[str] = None

    @property
    def slice_key(self) -> str:
        parts = [
            self.git_commit or "unknown_commit",
            f"{self.dm_provider or 'unknown'}:{self.dm_model or 'unknown'}",
            self._prompt_fingerprint(),
            self.scenario_family or "unknown_scenario",
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _prompt_fingerprint(self) -> str:
        if not self.prompt_versions:
            return "unknown_prompts"
        raw = json.dumps(sorted(self.prompt_versions.items()), separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class TrainingExample:
    example_id: str
    source_path: str
    session_id: str
    session_name: Optional[str]
    round_num: Optional[int]
    llm_line: int
    resolution_line: int
    action_type: Optional[str]
    success_tier: Optional[str]
    margin: Optional[int]
    slice_key: str
    messages: List[Dict[str, str]]
    mechanics: Dict[str, Any]


@dataclass
class Rejection:
    source_path: str
    session_id: Optional[str]
    line_number: Optional[int]
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


def read_events(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            event["_line_num"] = line_number
            events.append(event)
    return events


def discover_session_files(paths: Sequence[Path], recursive: bool, pattern: str) -> List[Path]:
    files: List[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            globber = path.rglob if recursive else path.glob
            files.extend(globber(pattern))
        else:
            raise FileNotFoundError(f"Path does not exist: {path}")
    return sorted(set(files))


def normalize_message(message: Dict[str, Any]) -> Optional[Dict[str, str]]:
    role = message.get("role")
    content = message.get("content")
    if role not in {"system", "user", "assistant"}:
        return None
    if not isinstance(content, str) or not content.strip():
        return None
    return {"role": role, "content": content}


def load_source_session(path: Path, validation: ValidationResult) -> SourceSession:
    events = read_events(path)
    session_start = next((e for e in events if e.get("event_type") == "session_start"), {})
    scenario = next((e for e in events if e.get("event_type") == "scenario"), {})
    config = session_start.get("config", {}) if isinstance(session_start.get("config"), dict) else {}
    agents = config.get("agents", {}) if isinstance(config.get("agents"), dict) else {}
    dm_llm = agents.get("dm", {}).get("llm", {}) if isinstance(agents.get("dm"), dict) else {}
    players = agents.get("players", []) if isinstance(agents.get("players"), list) else []
    player_llm = players[0].get("llm", {}) if players and isinstance(players[0], dict) else {}
    prompt_versions: Counter = Counter()

    for event in events:
        if event.get("event_type") != "action_resolution":
            continue
        context = event.get("context", {})
        if not isinstance(context, dict):
            continue
        metadata = context.get("prompt_metadata", {})
        if isinstance(metadata, dict):
            template = metadata.get("template", "unknown_template")
            version = metadata.get("version", "unknown_version")
            prompt_versions[f"{template}@{version}"] += 1

    scenario_obj = scenario.get("scenario", {}) if isinstance(scenario.get("scenario"), dict) else {}
    return SourceSession(
        path=path,
        validation=validation,
        events=events,
        session_id=session_start.get("session") or path.stem.removeprefix("session_"),
        session_name=config.get("session_name"),
        git_commit=session_start.get("git_commit"),
        game_version=session_start.get("version"),
        dm_provider=dm_llm.get("provider"),
        dm_model=dm_llm.get("model"),
        player_provider=player_llm.get("provider"),
        player_model=player_llm.get("model"),
        prompt_versions=prompt_versions,
        scenario_family=derive_scenario_family(config, scenario_obj, path),
    )


def derive_scenario_family(config: Dict[str, Any], scenario: Dict[str, Any], path: Path) -> str:
    for key in ("scenario_theme", "session_name"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return slugify(value)
    theme = scenario.get("theme")
    if isinstance(theme, str) and theme.strip():
        return slugify(theme)
    for part in path.parts:
        if part.startswith("golden_seed") or part in {"season2_cheap", "smoke_cheap"}:
            return slugify(part)
    return "unknown"


def slugify(value: str) -> str:
    chars = []
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "_":
            chars.append("_")
    return "".join(chars).strip("_") or "unknown"


def strict_session_allowed(result: ValidationResult, allow_warnings: bool) -> Tuple[bool, str]:
    if not result.passed:
        return False, "validator_errors"
    if not result.stats.get("is_complete"):
        return False, "incomplete_session"
    if result.stats.get("fallback_triggers", 0) > 0:
        return False, "llm_fallback"
    if result.stats.get("validation_failures", 0) > 0:
        return False, "pydantic_validation_failure"
    if result.warnings and not allow_warnings:
        return False, "validator_warnings"
    return True, "included"


def is_action_resolution_call(event: Dict[str, Any]) -> bool:
    if event.get("event_type") != "llm_call" or event.get("agent_type") != "dm":
        return False
    prompt = event.get("prompt")
    response = event.get("response")
    if not isinstance(prompt, list) or not isinstance(response, str) or not response.strip():
        return False
    prompt_text = "\n".join(
        message.get("content", "") for message in prompt if isinstance(message, dict)
    )
    if "ActionResolution" not in prompt_text:
        return False
    if "ConversionDecisions" in prompt_text or "Based on the resolutions above, what conversions should occur?" in prompt_text:
        return False
    if "synthesizing a round of actions" in prompt_text:
        return False
    return True


def find_resolution_for_call(
    events: List[Dict[str, Any]],
    start_index: int,
    used_resolution_indexes: set[int],
) -> Optional[Tuple[int, Dict[str, Any]]]:
    call = events[start_index]
    call_round = call.get("round")

    for index in range(start_index + 1, min(len(events), start_index + 8)):
        event = events[index]
        event_type = event.get("event_type")

        if event_type == "llm_call":
            return None

        if event_type != "action_resolution":
            continue

        if index in used_resolution_indexes:
            continue
        if event.get("round") != call_round:
            continue
        if event.get("phase") not in ACTION_PHASES:
            continue
        return index, event

    return None


def validate_example_pair(
    call: Dict[str, Any],
    resolution: Dict[str, Any],
) -> Optional[str]:
    prompt = [normalize_message(m) for m in call.get("prompt", []) if isinstance(m, dict)]
    if not prompt or any(m is None for m in prompt):
        return "invalid_prompt_messages"
    response = call.get("response", "")
    if not isinstance(response, str) or len(response.strip()) < 20:
        return "empty_or_tiny_response"
    if "traceback" in response.lower() or "exception" in response.lower():
        return "error_like_response"
    roll = resolution.get("roll")
    if not isinstance(roll, dict) or roll.get("margin") is None:
        return "missing_roll"
    context = resolution.get("context")
    if not isinstance(context, dict):
        return "missing_resolution_context"
    metadata = context.get("prompt_metadata")
    if not isinstance(metadata, dict):
        return "missing_prompt_metadata"
    if not resolution.get("outcome_tiers_full"):
        return "missing_outcome_tiers_full"
    return None


def extract_examples(session: SourceSession) -> Tuple[List[TrainingExample], List[Rejection]]:
    examples: List[TrainingExample] = []
    rejections: List[Rejection] = []
    used_resolution_indexes: set[int] = set()

    for index, event in enumerate(session.events):
        if not is_action_resolution_call(event):
            continue

        pair = find_resolution_for_call(session.events, index, used_resolution_indexes)
        if not pair:
            rejections.append(Rejection(
                source_path=str(session.path),
                session_id=session.session_id,
                line_number=event.get("_line_num"),
                reason="unpaired_dm_action_resolution_call",
            ))
            continue

        resolution_index, resolution = pair
        reason = validate_example_pair(event, resolution)
        if reason:
            rejections.append(Rejection(
                source_path=str(session.path),
                session_id=session.session_id,
                line_number=event.get("_line_num"),
                reason=reason,
                details={"resolution_line": resolution.get("_line_num")},
            ))
            continue

        used_resolution_indexes.add(resolution_index)
        messages = [
            normalize_message(m)
            for m in event.get("prompt", [])
            if isinstance(m, dict)
        ]
        assert all(m is not None for m in messages)
        messages = list(messages)  # type: ignore[assignment]
        messages.append({"role": "assistant", "content": event["response"].strip()})

        mechanics = mechanics_projection(resolution)
        example_id = stable_example_id(session.path, event, resolution)
        context = resolution.get("context", {})
        examples.append(TrainingExample(
            example_id=example_id,
            source_path=str(session.path),
            session_id=session.session_id,
            session_name=session.session_name,
            round_num=event.get("round"),
            llm_line=event.get("_line_num", 0),
            resolution_line=resolution.get("_line_num", 0),
            action_type=context.get("action_type") if isinstance(context, dict) else None,
            success_tier=resolution.get("roll", {}).get("tier") if isinstance(resolution.get("roll"), dict) else None,
            margin=resolution.get("roll", {}).get("margin") if isinstance(resolution.get("roll"), dict) else None,
            slice_key=session.slice_key,
            messages=messages,  # type: ignore[arg-type]
            mechanics=mechanics,
        ))

    return examples, rejections


def mechanics_projection(resolution: Dict[str, Any]) -> Dict[str, Any]:
    context = resolution.get("context", {}) if isinstance(resolution.get("context"), dict) else {}
    return {
        "agent": resolution.get("agent"),
        "action": resolution.get("action"),
        "action_type": context.get("action_type"),
        "is_ritual": context.get("is_ritual"),
        "roll": resolution.get("roll", {}),
        "economy": resolution.get("economy", {}),
        "clocks": resolution.get("clocks", {}),
        "effects": resolution.get("effects", []),
        "outcome_tiers_full_present": bool(resolution.get("outcome_tiers_full")),
        "prompt_metadata": context.get("prompt_metadata", {}),
    }


def stable_example_id(path: Path, call: Dict[str, Any], resolution: Dict[str, Any]) -> str:
    raw = "|".join([
        str(path),
        str(call.get("_line_num")),
        str(resolution.get("_line_num")),
        str(call.get("event_id") or ""),
        str(resolution.get("event_id") or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def split_examples(
    examples: List[TrainingExample],
    validation_ratio: float,
) -> Tuple[List[TrainingExample], List[TrainingExample]]:
    by_session: Dict[str, List[TrainingExample]] = defaultdict(list)
    for example in examples:
        by_session[example.session_id].append(example)

    sessions = sorted(by_session)
    if len(sessions) < 2 or validation_ratio <= 0:
        return examples, []

    validation_count = max(1, round(len(sessions) * validation_ratio))
    validation_count = min(validation_count, len(sessions) - 1)
    scored = sorted(
        sessions,
        key=lambda session_id: hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
    )
    validation_sessions = set(scored[:validation_count])

    train: List[TrainingExample] = []
    validation: List[TrainingExample] = []
    for example in examples:
        if example.session_id in validation_sessions:
            validation.append(example)
        else:
            train.append(example)
    return train, validation


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def example_to_chat_row(example: TrainingExample) -> Dict[str, Any]:
    return {"messages": example.messages}


def example_to_manifest_row(example: TrainingExample) -> Dict[str, Any]:
    return {
        "example_id": example.example_id,
        "source_path": example.source_path,
        "session_id": example.session_id,
        "session_name": example.session_name,
        "round": example.round_num,
        "llm_line": example.llm_line,
        "resolution_line": example.resolution_line,
        "action_type": example.action_type,
        "success_tier": example.success_tier,
        "margin": example.margin,
        "slice_key": example.slice_key,
        "mechanics": example.mechanics,
    }


def rejection_to_row(rejection: Rejection) -> Dict[str, Any]:
    return {
        "source_path": rejection.source_path,
        "session_id": rejection.session_id,
        "line_number": rejection.line_number,
        "reason": rejection.reason,
        "details": rejection.details,
    }


def build_manifest(
    *,
    source_files: List[Path],
    included_sessions: List[SourceSession],
    excluded_sessions: List[Tuple[Path, str, ValidationResult]],
    examples: List[TrainingExample],
    train: List[TrainingExample],
    validation: List[TrainingExample],
    example_rejections: List[Rejection],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    slices: Dict[str, Dict[str, Any]] = {}
    session_by_path = {str(session.path): session for session in included_sessions}
    for example in examples:
        source = session_by_path.get(example.source_path)
        if example.slice_key not in slices:
            slices[example.slice_key] = {
                "slice_key": example.slice_key,
                "git_commit": source.git_commit if source else None,
                "game_version": source.game_version if source else None,
                "dm_provider": source.dm_provider if source else None,
                "dm_model": source.dm_model if source else None,
                "player_provider": source.player_provider if source else None,
                "player_model": source.player_model if source else None,
                "scenario_family": source.scenario_family if source else None,
                "prompt_versions": dict(source.prompt_versions) if source else {},
                "session_count": 0,
                "example_count": 0,
            }
        slices[example.slice_key]["example_count"] += 1

    for session in included_sessions:
        if session.slice_key in slices:
            slices[session.slice_key]["session_count"] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_paths": [str(path) for path in source_files],
        "settings": {
            "strict": not args.allow_warnings,
            "allow_warnings": args.allow_warnings,
            "validation_ratio": args.validation_ratio,
            "recursive": args.recursive,
            "pattern": args.pattern,
            "task": "dm_action_resolution",
            "assistant_target": "logged_dm_llm_response",
        },
        "counts": {
            "source_sessions": len(source_files),
            "included_sessions": len(included_sessions),
            "excluded_sessions": len(excluded_sessions),
            "examples": len(examples),
            "train_examples": len(train),
            "validation_examples": len(validation),
            "example_rejections": len(example_rejections),
        },
        "slices": sorted(slices.values(), key=lambda item: item["slice_key"]),
        "included_sessions": [
            {
                "path": str(session.path),
                "session_id": session.session_id,
                "session_name": session.session_name,
                "slice_key": session.slice_key,
                "stats": session.validation.to_dict()["stats"],
            }
            for session in included_sessions
        ],
        "excluded_sessions": [
            {
                "path": str(path),
                "reason": reason,
                "errors": result.error_count,
                "warnings": result.warning_count,
                "stats": result.to_dict()["stats"],
            }
            for path, reason, result in excluded_sessions
        ],
    }


def write_report(path: Path, manifest: Dict[str, Any], example_rejections: List[Rejection]) -> None:
    rejection_counts = Counter(r.reason for r in example_rejections)
    lines = [
        "# DM Fine-Tune Dataset Quality Report",
        "",
        f"Generated: {manifest['generated_at']}",
        "",
        "## Counts",
        "",
    ]
    for key, value in manifest["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Slices", ""])
    for slice_info in manifest["slices"]:
        lines.append(
            "- {slice_key}: {example_count} examples, {session_count} sessions, "
            "{git_commit}, {dm_provider}:{dm_model}, {scenario_family}".format(**slice_info)
        )
    lines.extend(["", "## Example Rejections", ""])
    if rejection_counts:
        for reason, count in rejection_counts.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Policy", ""])
    lines.append("- v1 exports only paired DM action-resolution calls.")
    lines.append("- Strict mode excludes sessions with validator warnings.")
    lines.append("- Train/validation split is session-disjoint.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_dataset(args: argparse.Namespace) -> int:
    source_files = discover_session_files(
        [Path(p) for p in args.inputs],
        recursive=args.recursive,
        pattern=args.pattern,
    )
    if not source_files:
        print("No session files found", file=sys.stderr)
        return 1

    validator = BulkValidator(fallback_threshold=args.fallback_threshold / 100)
    result_by_path = {
        path: safe_validate_session(validator, path)
        for path in source_files
    }

    included_sessions: List[SourceSession] = []
    excluded_sessions: List[Tuple[Path, str, ValidationResult]] = []
    all_examples: List[TrainingExample] = []
    all_rejections: List[Rejection] = []

    for path in source_files:
        result = result_by_path[path]
        allowed, reason = strict_session_allowed(result, allow_warnings=args.allow_warnings)
        if not allowed:
            excluded_sessions.append((path, reason, result))
            continue

        session = load_source_session(path, result)
        examples, rejections = extract_examples(session)
        included_sessions.append(session)
        all_examples.extend(examples)
        all_rejections.extend(rejections)

    if not all_examples:
        print("No training examples survived quality gates", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train, validation = split_examples(all_examples, args.validation_ratio)
    write_jsonl(output_dir / "train.jsonl", (example_to_chat_row(e) for e in train))
    write_jsonl(output_dir / "validation.jsonl", (example_to_chat_row(e) for e in validation))
    write_jsonl(output_dir / "examples_manifest.jsonl", (example_to_manifest_row(e) for e in all_examples))
    write_jsonl(output_dir / "quarantine.jsonl", (rejection_to_row(r) for r in all_rejections))

    manifest = build_manifest(
        source_files=source_files,
        included_sessions=included_sessions,
        excluded_sessions=excluded_sessions,
        examples=all_examples,
        train=train,
        validation=validation,
        example_rejections=all_rejections,
        args=args,
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_report(output_dir / "quality_report.md", manifest, all_rejections)

    print(json.dumps({
        "output_dir": str(output_dir),
        "train_examples": len(train),
        "validation_examples": len(validation),
        "included_sessions": len(included_sessions),
        "excluded_sessions": len(excluded_sessions),
        "example_rejections": len(all_rejections),
    }, indent=2))
    return 0


def safe_validate_session(validator: BulkValidator, path: Path) -> ValidationResult:
    """Run BulkValidator without letting schema-drift sessions crash the export."""
    try:
        return validator.validate_session(path)
    except Exception as exc:
        result = ValidationResult(session_path=path, passed=False)
        result.add_error(
            ValidatorType.INTEGRITY,
            f"Validator crashed: {type(exc).__name__}: {exc}",
        )
        return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build strict OpenAI chat fine-tune JSONL for the Aeonisk DM agent."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Session JSONL files or directories containing session_*.jsonl files.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="datasets/dm_finetune/latest",
        help="Directory to write train.jsonl, validation.jsonl, manifest, and quarantine files.",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help="Glob pattern used when an input is a directory.",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Do not recursively search input directories.",
    )
    parser.set_defaults(recursive=True)
    parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="Allow sessions with validator warnings. Default strict mode rejects warnings.",
    )
    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.2,
        help="Fraction of source sessions reserved for validation. Split is by session.",
    )
    parser.add_argument(
        "--fallback-threshold",
        type=float,
        default=10.0,
        help="Fallback warning threshold passed to BulkValidator, as a percentage.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    return build_dataset(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
