#!/usr/bin/env python3
"""
Convert prompt JSON files to YAML format with proper multi-line formatting.
"""

import json
import yaml
from pathlib import Path


class literal_str(str):
    """String subclass that forces YAML to use literal block style (|)."""
    pass


def literal_str_representer(dumper, data):
    """Custom YAML representer for literal strings."""
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


# Register custom representer
yaml.add_representer(literal_str, literal_str_representer)


def convert_strings_to_literal(obj):
    """Recursively convert multi-line strings to literal_str for better YAML formatting."""
    if isinstance(obj, dict):
        return {k: convert_strings_to_literal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_strings_to_literal(item) for item in obj]
    elif isinstance(obj, str) and '\n' in obj:
        return literal_str(obj)
    else:
        return obj


def convert_json_to_yaml(json_path: Path) -> Path:
    """Convert a JSON file to YAML format with readable multi-line strings."""
    # Read JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Convert multi-line strings to use literal block style
    data = convert_strings_to_literal(data)

    # Create YAML path (same location, different extension)
    yaml_path = json_path.with_suffix('.yaml')

    # Write YAML
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
            indent=2
        )

    print(f"✓ Converted: {json_path.name} → {yaml_path.name}")
    return yaml_path


def main():
    """Find and convert all JSON prompt files."""
    script_dir = Path(__file__).parent
    prompts_dir = script_dir / "prompts"

    # Find all JSON files
    json_files = list(prompts_dir.rglob("*.json"))

    if not json_files:
        print("No JSON files found to convert.")
        return

    print(f"Found {len(json_files)} JSON file(s) to convert:\n")

    # Convert each file
    for json_path in sorted(json_files):
        convert_json_to_yaml(json_path)

    print(f"\n✓ Successfully converted {len(json_files)} file(s)")
    print("\nYou can now delete the old JSON files if the YAML files work correctly:")
    for json_path in sorted(json_files):
        print(f"  rm {json_path}")


if __name__ == "__main__":
    main()
