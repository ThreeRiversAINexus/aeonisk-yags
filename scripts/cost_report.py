#!/usr/bin/env python3
"""
Cost and token reporting for Aeonisk YAGS session JSONL outputs.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from token_utils import count_chat_tokens, count_text_tokens, get_encoding


@dataclass
class CostBucket:
    config: str
    run: str
    agent_type: str
    provider: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    logged_calls: int = 0
    tokenizer_estimated_calls: int = 0
    char_estimated_calls: int = 0
    model_mismatch_calls: int = 0
    logged_models: Dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0

    def add(
        self,
        input_tokens: int,
        output_tokens: int,
        method: str,
        cost_usd: float,
        logged_model: str,
    ) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.cost_usd += cost_usd
        self.logged_models[logged_model] = self.logged_models.get(logged_model, 0) + 1
        if logged_model and logged_model != self.model:
            self.model_mismatch_calls += 1

        if method == "logged":
            self.logged_calls += 1
        elif method == "tiktoken":
            self.tokenizer_estimated_calls += 1
        else:
            self.char_estimated_calls += 1


@dataclass
class CostReport:
    path: str
    session_files: int = 0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    logged_calls: int = 0
    tokenizer_estimated_calls: int = 0
    char_estimated_calls: int = 0
    model_mismatch_calls: int = 0
    cost_usd: float = 0.0
    buckets: Dict[Tuple[str, str, str, str, str], CostBucket] = field(default_factory=dict)

    def add_call(
        self,
        config: str,
        run: str,
        agent_type: str,
        provider: str,
        model: str,
        logged_model: str,
        input_tokens: int,
        output_tokens: int,
        method: str,
        cost_usd: float,
    ) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.cost_usd += cost_usd

        if method == "logged":
            self.logged_calls += 1
        elif method == "tiktoken":
            self.tokenizer_estimated_calls += 1
        else:
            self.char_estimated_calls += 1
        if logged_model and logged_model != model:
            self.model_mismatch_calls += 1

        key = (config, run, agent_type, provider, model)
        if key not in self.buckets:
            self.buckets[key] = CostBucket(
                config=config,
                run=run,
                agent_type=agent_type,
                provider=provider,
                model=model,
            )
        self.buckets[key].add(input_tokens, output_tokens, method, cost_usd, logged_model)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "session_files": self.session_files,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "logged_calls": self.logged_calls,
            "tokenizer_estimated_calls": self.tokenizer_estimated_calls,
            "char_estimated_calls": self.char_estimated_calls,
            "model_mismatch_calls": self.model_mismatch_calls,
            "cost_usd": self.cost_usd,
            "buckets": [bucket.__dict__ for bucket in self.sorted_buckets()],
        }

    def sorted_buckets(self) -> List[CostBucket]:
        return sorted(
            self.buckets.values(),
            key=lambda b: (b.config, b.run, b.agent_type, b.provider, b.model),
        )


def discover_session_files(path: Path, recursive: bool = True) -> List[Path]:
    if path.is_file():
        return [path]
    if recursive:
        return sorted(path.rglob("session_*.jsonl"))
    return sorted(path.glob("session_*.jsonl"))


def load_pricing(path: Optional[Path]) -> Dict[str, Dict[str, float]]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if "models" in raw:
        raw = raw["models"]

    pricing: Dict[str, Dict[str, float]] = {}
    for model, values in raw.items():
        pricing[model] = {
            "input_per_1m": float(values.get("input_per_1m", values.get("input", 0.0))),
            "output_per_1m": float(values.get("output_per_1m", values.get("output", 0.0))),
        }
    return pricing


def call_tokens(event: Dict[str, Any]) -> Tuple[int, int, str]:
    tokens = event.get("tokens") or {}
    input_tokens = int(tokens.get("input", tokens.get("input_tokens", 0)) or 0)
    output_tokens = int(tokens.get("output", tokens.get("output_tokens", 0)) or 0)

    if input_tokens > 0 or output_tokens > 0:
        return input_tokens, output_tokens, "logged"

    model = event.get("model") or ""
    prompt = event.get("prompt") or []
    response = event.get("response") or ""
    method = "tiktoken" if get_encoding(model) is not None else "chars"

    if isinstance(prompt, list):
        input_tokens = count_chat_tokens(prompt, model)
    else:
        input_tokens = count_text_tokens(str(prompt), model)
    output_tokens = count_text_tokens(str(response), model)
    return input_tokens, output_tokens, method


def effective_provider(llm_config: Dict[str, Any]) -> str:
    provider = llm_config.get("provider") or "unknown"
    if provider == "batch_proxy":
        return llm_config.get("underlying_provider") or provider
    return provider


def infer_llm_config(session_config: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    agents = session_config.get("agents") or {}
    agent_type = event.get("agent_type")
    agent_id = event.get("agent_id") or ""

    if agent_type == "dm":
        return (agents.get("dm") or {}).get("llm") or {}

    if agent_type == "enemy":
        enemy_config = agents.get("enemy_agents") or agents.get("enemies") or {}
        return enemy_config.get("llm") or {}

    if agent_type == "player":
        players = agents.get("players") or []
        match = re.match(r"player_(\d+)$", agent_id)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(players):
                return players[index].get("llm") or {}
        if players:
            return players[0].get("llm") or {}

    return {}


def call_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: Dict[str, Dict[str, float]],
) -> float:
    model_pricing = pricing.get(f"{provider}:{model}") or pricing.get(model)
    if not model_pricing:
        return 0.0
    return (
        input_tokens * model_pricing["input_per_1m"] / 1_000_000
        + output_tokens * model_pricing["output_per_1m"] / 1_000_000
    )


def infer_run_name(path: Path) -> str:
    for parent in [path.parent, *path.parents]:
        if parent.name.startswith("run_"):
            return parent.name
    return path.parent.name


def analyze_cost(path: Path, recursive: bool = True, pricing_file: Optional[Path] = None) -> CostReport:
    pricing = load_pricing(pricing_file)
    report = CostReport(path=str(path))
    session_files = discover_session_files(path, recursive=recursive)
    report.session_files = len(session_files)

    for session_file in session_files:
        run = infer_run_name(session_file)
        config = "unknown"
        session_config: Dict[str, Any] = {}
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                if event.get("event_type") == "session_start":
                    session_config = event.get("config") or {}
                    config = session_config.get("session_name", config)
                    continue
                if event.get("event_type") != "llm_call":
                    continue

                llm_config = infer_llm_config(session_config, event)
                provider = effective_provider(llm_config)
                logged_model = event.get("model") or ""
                model = llm_config.get("model") or logged_model or "unknown"
                agent_type = event.get("agent_type") or "unknown"
                input_tokens, output_tokens, method = call_tokens(event)
                cost_usd = call_cost(provider, model, input_tokens, output_tokens, pricing)
                report.add_call(
                    config=config,
                    run=run,
                    agent_type=agent_type,
                    provider=provider,
                    model=model,
                    logged_model=logged_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    method=method,
                    cost_usd=cost_usd,
                )

    return report


def print_text_report(report: CostReport) -> None:
    print(f"\nCOST REPORT: {report.path}")
    print("=" * 80)
    print(f"Sessions: {report.session_files}")
    print(f"LLM calls: {report.calls}")
    print(f"Input tokens: {report.input_tokens:,}")
    print(f"Output tokens: {report.output_tokens:,}")
    print(f"Total tokens: {report.total_tokens:,}")
    print(f"Logged calls: {report.logged_calls}")
    print(f"Tiktoken-estimated calls: {report.tokenizer_estimated_calls}")
    print(f"Char-estimated calls: {report.char_estimated_calls}")
    if report.model_mismatch_calls:
        print(f"Model mismatches: {report.model_mismatch_calls}")
    if report.cost_usd:
        print(f"Estimated cost: ${report.cost_usd:.6f}")
    else:
        print("Estimated cost: unavailable (provide --pricing-file)")

    print("\nBy config/run/agent/provider/model:")
    print(f"{'Config':<34} {'Run':<10} {'Agent':<8} {'Provider':<10} {'Model':<22} {'Calls':>5} {'Input':>11} {'Output':>9} {'Mismatch':>8} {'Cost':>10}")
    print("-" * 142)
    for bucket in report.sorted_buckets():
        config = bucket.config[:33]
        run = bucket.run[:9]
        provider = bucket.provider[:9]
        model = bucket.model[:21]
        cost = f"${bucket.cost_usd:.4f}" if bucket.cost_usd else "-"
        print(
            f"{config:<34} {run:<10} {bucket.agent_type:<8} {provider:<10} {model:<22} "
            f"{bucket.calls:>5} {bucket.input_tokens:>11,} {bucket.output_tokens:>9,} "
            f"{bucket.model_mismatch_calls:>8} {cost:>10}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Estimate token usage and cost for YAGS session outputs.")
    parser.add_argument("path", type=Path, help="Session JSONL or bulk output directory")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse into directories")
    parser.add_argument("--pricing-file", type=Path, help="JSON file with per-model input/output costs per 1M tokens")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = analyze_cost(args.path, recursive=not args.no_recursive, pricing_file=args.pricing_file)
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
