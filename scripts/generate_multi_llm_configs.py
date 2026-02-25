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


def generate_config(
    base_config: dict,
    provider: str = None,
    model: str = None,
    dm_spec: str = None,
    player_spec: str = None,
    enemy_spec: str = None,
    npc_spec: str = None,
    proxy_url: str = None
) -> dict:
    """Deep-copy base config and replace provider/model in agent LLM blocks.

    Supports two modes:
    1. Legacy (provider + model): Sets ALL roles to the same provider:model.
    2. Per-role (dm_spec, player_spec, enemy_spec, npc_spec): Override
       specific roles independently. Per-role overrides take precedence
       over the legacy provider/model when both are specified.

    Args:
        base_config: Base session config dict (not mutated).
        provider: Legacy mode - provider name for all roles.
        model: Legacy mode - model name for all roles.
        dm_spec: "provider:model" for DM only.
        player_spec: "provider:model" for all players.
        enemy_spec: "provider:model" for enemies (creates agents.enemies.llm).
        npc_spec: "provider:model" for NPCs (creates agents.npcs.llm).
        proxy_url: Wrap configs in batch_proxy routing.

    Returns:
        New config dict with updated LLM blocks.
    """
    config = copy.deepcopy(base_config)

    # Legacy mode: --providers sets all roles to same model
    if provider and model:
        # Update DM
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

        # Update enemies section (Spec 11: per-role config)
        config.setdefault("agents", {}).setdefault("enemies", {})["llm"] = \
            update_llm_block({}, provider, model, proxy_url)

        # Update NPCs section (Spec 11: per-role config)
        config.setdefault("agents", {}).setdefault("npcs", {})["llm"] = \
            update_llm_block({}, provider, model, proxy_url)

    # Per-role overrides (take precedence over --providers)
    if dm_spec:
        dm_provider, dm_model = dm_spec.split(":", 1)
        config.setdefault("agents", {}).setdefault("dm", {})["llm"] = update_llm_block(
            config.get("agents", {}).get("dm", {}).get("llm", {}),
            dm_provider, dm_model, proxy_url
        )

    if player_spec:
        player_provider, player_model = player_spec.split(":", 1)
        for player in config.get("agents", {}).get("players", []):
            player["llm"] = update_llm_block(
                player.get("llm", {}), player_provider, player_model, proxy_url
            )

    if enemy_spec:
        enemy_provider, enemy_model = enemy_spec.split(":", 1)
        config.setdefault("agents", {}).setdefault("enemies", {})["llm"] = \
            update_llm_block({}, enemy_provider, enemy_model, proxy_url)

    if npc_spec:
        npc_provider, npc_model = npc_spec.split(":", 1)
        config.setdefault("agents", {}).setdefault("npcs", {})["llm"] = \
            update_llm_block({}, npc_provider, npc_model, proxy_url)

    # Update session_name to reflect model choices
    base_name = config.get("session_name", "experiment")

    if dm_spec or player_spec or enemy_spec or npc_spec:
        # Per-role mode: include role labels in session name
        name_parts = [base_name]
        if dm_spec:
            dm_model_name = dm_spec.split(":", 1)[1]
            name_parts.append(f"dm-{sanitize_model_name(dm_model_name)}")
        if player_spec:
            player_model_name = player_spec.split(":", 1)[1]
            name_parts.append(f"pc-{sanitize_model_name(player_model_name)}")
        if enemy_spec:
            enemy_model_name = enemy_spec.split(":", 1)[1]
            name_parts.append(f"enemy-{sanitize_model_name(enemy_model_name)}")
        if npc_spec:
            npc_model_name = npc_spec.split(":", 1)[1]
            name_parts.append(f"npc-{sanitize_model_name(npc_model_name)}")
        config["session_name"] = "_".join(name_parts)
    elif provider and model:
        # Legacy mode: single provider_model suffix
        safe_model = sanitize_model_name(model)
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
        default=None,
        help='Provider:model pairs (e.g., "openai:gpt-5-mini" "anthropic:claude-sonnet-4-5")',
    )
    parser.add_argument(
        "--dm-model",
        default=None,
        help='Override DM model only (e.g., "anthropic:claude-sonnet-4-5")',
    )
    parser.add_argument(
        "--player-model",
        default=None,
        help='Override all player models (e.g., "openai:gpt-5-mini")',
    )
    parser.add_argument(
        "--enemy-model",
        default=None,
        help='Override enemy model (e.g., "openai:gpt-4o-mini")',
    )
    parser.add_argument(
        "--npc-model",
        default=None,
        help='Override NPC model (e.g., "openai:gpt-4o-mini")',
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

    # Validate: at least one model specification required
    has_per_role = any([args.dm_model, args.player_model, args.enemy_model, args.npc_model])
    if not args.providers and not has_per_role:
        parser.error("Must specify --providers and/or per-role flags (--dm-model, --player-model, --enemy-model, --npc-model)")

    # Validate per-role spec format
    for flag_name, flag_value in [
        ("--dm-model", args.dm_model),
        ("--player-model", args.player_model),
        ("--enemy-model", args.enemy_model),
        ("--npc-model", args.npc_model),
    ]:
        if flag_value and ":" not in flag_value:
            print(
                f"Error: Invalid {flag_name} spec '{flag_value}' - expected 'provider:model'",
                file=sys.stderr,
            )
            sys.exit(1)

    # Load base config
    base_path = Path(args.base_config)
    if not base_path.exists():
        print(f"Error: Base config not found: {base_path}", file=sys.stderr)
        sys.exit(1)

    with open(base_path) as f:
        base_config = json.load(f)

    # Parse provider:model pairs (legacy --providers flag)
    specs = []
    if args.providers:
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

    if specs:
        # Legacy mode: one config per provider:model pair, plus per-role overrides
        for provider, model in specs:
            config = generate_config(
                base_config,
                provider=provider,
                model=model,
                dm_spec=args.dm_model,
                player_spec=args.player_model,
                enemy_spec=args.enemy_model,
                npc_spec=args.npc_model,
                proxy_url=args.proxy,
            )
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
            if has_per_role:
                print(f"  per-role overrides: dm={args.dm_model}, player={args.player_model}, enemy={args.enemy_model}, npc={args.npc_model}")
            print()
    else:
        # Per-role mode only (no --providers)
        config = generate_config(
            base_config,
            dm_spec=args.dm_model,
            player_spec=args.player_model,
            enemy_spec=args.enemy_model,
            npc_spec=args.npc_model,
            proxy_url=args.proxy,
        )

        # Build filename from per-role specs
        name_parts = [base_stem]
        if args.dm_model:
            name_parts.append(f"dm_{sanitize_model_name(args.dm_model.split(':', 1)[1])}")
        if args.player_model:
            name_parts.append(f"pc_{sanitize_model_name(args.player_model.split(':', 1)[1])}")
        if args.enemy_model:
            name_parts.append(f"enemy_{sanitize_model_name(args.enemy_model.split(':', 1)[1])}")
        if args.npc_model:
            name_parts.append(f"npc_{sanitize_model_name(args.npc_model.split(':', 1)[1])}")

        filename = f"session_config_{'_'.join(name_parts)}.json"
        output_path = output_dir / filename

        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        generated_paths.append(str(output_path))
        print(f"Generated: {output_path}")
        print(f"  session_name: {config['session_name']}")
        print(f"  dm={args.dm_model}, player={args.player_model}, enemy={args.enemy_model}, npc={args.npc_model}")
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
