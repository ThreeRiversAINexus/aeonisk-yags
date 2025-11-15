#!/usr/bin/env python3
"""
Convert session configs from Anthropic to OpenAI.

Usage: python3 scripts/convert_to_openai.py <input_json> <output_json>
"""

import json
import sys
from pathlib import Path


def convert_llm_config(llm_config):
    """Convert LLM config from Anthropic to OpenAI."""
    return {
        "provider": "openai",
        "model": "gpt-5-mini",
        "temperature": llm_config.get("temperature", 0.8)
    }


def convert_config(input_path: Path, output_path: Path):
    """Convert a session config from Anthropic to OpenAI."""
    with open(input_path, 'r') as f:
        config = json.load(f)

    # Update metadata
    if "_role" in config:
        config["_role"] = config["_role"] + "_openai" if not config["_role"].endswith("_openai") else config["_role"]

    if "_purpose" in config:
        if "ALL AGENTS USE OPENAI" not in config["_purpose"]:
            config["_purpose"] += " ALL AGENTS USE OPENAI GPT-5-MINI FOR COST EFFICIENCY."

    if "session_name" in config:
        if not config["session_name"].endswith("(OpenAI)"):
            config["session_name"] += " (OpenAI)"

    # Convert DM LLM config
    if "agents" in config and "dm" in config["agents"]:
        if "llm" in config["agents"]["dm"]:
            # Use temperature 1.0 for DM for creativity
            dm_temp = config["agents"]["dm"]["llm"].get("temperature", 0.7)
            config["agents"]["dm"]["llm"] = {
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 1.0  # Max creativity for DM
            }

    # Convert player LLM configs
    if "agents" in config and "players" in config["agents"]:
        for player in config["agents"]["players"]:
            if "llm" in player:
                player["llm"] = convert_llm_config(player["llm"])

    # Update design notes if present
    if "_design_notes" in config:
        if isinstance(config["_design_notes"], dict):
            config["_design_notes"]["llm_provider"] = "ALL AGENTS USE OPENAI GPT-5-MINI - 8x cheaper output tokens than Claude Sonnet 4.5, 10x higher rate limits. Temperature 1.0 for DM (creativity), 0.8 for players (consistency)."
        elif isinstance(config["_design_notes"], str):
            if "llm_provider" not in config["_design_notes"]:
                config["_design_notes"] += " LLM: ALL AGENTS USE OPENAI GPT-5-MINI (8x cheaper output, 10x higher rate limits)."

    # Update notes if present
    if "notes" in config:
        if "ALL AGENTS USE OPENAI" not in config["notes"]:
            config["notes"] += " ALL AGENTS USE OPENAI GPT-5-MINI FOR COST EFFICIENCY (8x cheaper output tokens, 10x higher rate limits vs Claude)."

    # Write output
    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Converted {input_path.name} → {output_path.name}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/convert_to_openai.py <input_json> <output_json>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    convert_config(input_path, output_path)


if __name__ == "__main__":
    main()
