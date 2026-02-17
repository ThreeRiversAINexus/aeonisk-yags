#!/usr/bin/env python3
"""
Multi-LLM Config Generator - Generate provider-specific session configs for experiments.

Takes a base session config and a list of provider:model specs, generates
provider-specific copies with all agent LLM blocks updated.

Usage:
    python scripts/generate_multi_llm_configs.py \
        --base-config scripts/session_configs/experiment/session_config_lethality_test.json \
        --providers "openai:gpt-5-mini" "anthropic:claude-sonnet-4-5" \
        --output-dir /tmp/lethality_configs/

Output:
    - One config file per provider:model pair
    - Ready-to-run bulk_session_runner.py command printed to stdout
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path


def sanitize_model_name(model: str) -> str:
    """Convert model name to filesystem-safe string (e.g., 'gpt-5-mini' -> 'gpt5mini')."""
    return re.sub(r"[^a-zA-Z0-9]", "", model)


def update_llm_block(llm_config: dict, provider: str, model: str, proxy_url: str = None) -> dict:
    """Update an LLM config block with new provider and model.

    When proxy_url is set, wraps the config in batch_proxy routing.
    """
    updated = copy.deepcopy(llm_config)
    if proxy_url:
        updated["provider"] = "batch_proxy"
        updated["model"] = model
        updated["underlying_provider"] = provider
        updated["use_proxy"] = True
        updated["proxy_url"] = proxy_url
        updated["proxy_priority"] = "normal"
        updated["proxy_strategy"] = "auto"
    else:
        updated["provider"] = provider
        updated["model"] = model
    return updated


def generate_config(base_config: dict, provider: str, model: str, proxy_url: str = None) -> dict:
    """Deep-copy base config and replace provider/model in ALL agent LLM blocks."""
    config = copy.deepcopy(base_config)

    # Update DM LLM block
    if "agents" in config and "dm" in config["agents"]:
        if "llm" in config["agents"]["dm"]:
            config["agents"]["dm"]["llm"] = update_llm_block(
                config["agents"]["dm"]["llm"], provider, model, proxy_url=proxy_url
            )

    # Update all player LLM blocks
    if "agents" in config and "players" in config["agents"]:
        for player in config["agents"]["players"]:
            if "llm" in player:
                player["llm"] = update_llm_block(player["llm"], provider, model, proxy_url=proxy_url)

    # Update session_name with original provider/model (not "batch_proxy")
    safe_model = sanitize_model_name(model)
    base_name = config.get("session_name", "experiment")
    config["session_name"] = f"{base_name}_{provider}_{safe_model}"

    return config


def main():
    parser = argparse.ArgumentParser(
        description="Generate provider-specific session configs for multi-LLM experiments"
    )
    parser.add_argument(
        "--base-config",
        required=True,
        help="Path to base session config JSON",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        required=True,
        help='Provider:model pairs (e.g., "openai:gpt-5-mini" "anthropic:claude-sonnet-4-5")',
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write generated configs",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy URL to wrap configs in batch_proxy routing (e.g., http://localhost:8000)",
    )
    parser.add_argument(
        "--runs-per-config",
        type=int,
        default=5,
        help="Runs per config for the printed bulk command (default: 5)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Workers for the printed bulk command (default: 4)",
    )

    args = parser.parse_args()

    # Load base config
    base_path = Path(args.base_config)
    if not base_path.exists():
        print(f"Error: Base config not found: {base_path}", file=sys.stderr)
        sys.exit(1)

    with open(base_path) as f:
        base_config = json.load(f)

    # Parse provider:model pairs
    specs = []
    for spec in args.providers:
        if ":" not in spec:
            print(
                f"Error: Invalid provider spec '{spec}' - expected 'provider:model'",
                file=sys.stderr,
            )
            sys.exit(1)
        provider, model = spec.split(":", 1)
        specs.append((provider, model))

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate configs
    generated_paths = []
    base_stem = base_path.stem.replace("session_config_", "")

    for provider, model in specs:
        config = generate_config(base_config, provider, model, proxy_url=args.proxy)
        safe_model = sanitize_model_name(model)
        filename = f"session_config_{base_stem}_{provider}_{safe_model}.json"
        output_path = output_dir / filename

        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        generated_paths.append(str(output_path))
        print(f"Generated: {output_path}")
        print(f"  session_name: {config['session_name']}")
        print(f"  provider: {provider}, model: {model}")
        print()

    # Print bulk runner command
    configs_arg = " \\\n    ".join(generated_paths)
    print("=" * 60)
    print("Ready to run:")
    print()
    print(f"python scripts/bulk_session_runner.py \\")
    print(f"  --configs {configs_arg} \\")
    print(f"  --runs-per-config {args.runs_per_config} --workers {args.workers} \\")
    print(f"  --output-dir ./multiagent_output/lethality_experiment/")


if __name__ == "__main__":
    main()
