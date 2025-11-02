#!/usr/bin/env python3
"""
Token profiling tool for prompt YAML files.

Measures actual token usage per section to identify optimization opportunities.

Usage:
    python scripts/analyze_prompt_tokens.py prompts/claude/en/dm.yaml
    python scripts/analyze_prompt_tokens.py prompts/claude/en/dm.yaml --breakdown sections
    python scripts/analyze_prompt_tokens.py prompts/claude/en/dm.yaml --output dm_tokens.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    import tiktoken
except ImportError:
    print("WARNING: tiktoken not installed. Install with: pip install tiktoken")
    print("Falling back to approximate token counting (1 token ≈ 4 characters)")
    tiktoken = None


def count_tokens(text: str, model: str = "claude-3-5-sonnet-20241022") -> int:
    """
    Count tokens in text using tiktoken or fallback estimation.

    Args:
        text: Text to count tokens for
        model: Model name (for tokenizer selection)

    Returns:
        Estimated token count
    """
    if tiktoken is not None:
        # Use cl100k_base encoding (closest to Claude)
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    else:
        # Fallback: approximate 1 token per 4 characters
        return len(text) // 4


def load_yaml_prompt(file_path: Path) -> Dict[str, Any]:
    """Load YAML prompt file and return parsed data."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def analyze_monolithic_prompt(file_path: Path) -> Dict[str, Any]:
    """
    Analyze a monolithic YAML prompt file (single sections dict).

    Returns:
        {
            "file": str,
            "total_lines": int,
            "total_chars": int,
            "total_tokens": int,
            "sections": [
                {"name": str, "lines": int, "chars": int, "tokens": int, "percent": float},
                ...
            ]
        }
    """
    data = load_yaml_prompt(file_path)

    # Check if this is a modular prompt (dm/ directory) or monolithic
    if "sections" not in data:
        # Single content field (modular prompt file)
        content = data.get("content", "")
        total_tokens = count_tokens(content)
        return {
            "file": str(file_path),
            "total_lines": content.count('\n') + 1,
            "total_chars": len(content),
            "total_tokens": total_tokens,
            "sections": [{
                "name": file_path.stem,
                "lines": content.count('\n') + 1,
                "chars": len(content),
                "tokens": total_tokens,
                "percent": 100.0
            }]
        }

    sections_data = data.get("sections", {})
    sections_analysis = []
    total_lines = 0
    total_chars = 0
    total_tokens = 0

    for section_name, section_content in sections_data.items():
        if not isinstance(section_content, str):
            continue

        lines = section_content.count('\n') + 1
        chars = len(section_content)
        tokens = count_tokens(section_content)

        sections_analysis.append({
            "name": section_name,
            "lines": lines,
            "chars": chars,
            "tokens": tokens
        })

        total_lines += lines
        total_chars += chars
        total_tokens += tokens

    # Calculate percentages
    for section in sections_analysis:
        section["percent"] = (section["tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0

    # Sort by token count descending
    sections_analysis.sort(key=lambda s: s["tokens"], reverse=True)

    return {
        "file": str(file_path),
        "total_lines": total_lines,
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "sections": sections_analysis
    }


def analyze_modular_prompts(directory: Path) -> Dict[str, Any]:
    """
    Analyze a directory of modular prompt files (dm/ structure).

    Returns similar structure to analyze_monolithic_prompt but aggregated.
    """
    yaml_files = list(directory.glob("*.yaml"))
    if not yaml_files:
        raise ValueError(f"No YAML files found in {directory}")

    sections_analysis = []
    total_lines = 0
    total_chars = 0
    total_tokens = 0

    for yaml_file in yaml_files:
        data = load_yaml_prompt(yaml_file)
        content = data.get("content", "")

        if not content:
            continue

        lines = content.count('\n') + 1
        chars = len(content)
        tokens = count_tokens(content)

        sections_analysis.append({
            "name": yaml_file.stem,
            "lines": lines,
            "chars": chars,
            "tokens": tokens
        })

        total_lines += lines
        total_chars += chars
        total_tokens += tokens

    # Calculate percentages
    for section in sections_analysis:
        section["percent"] = (section["tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0

    # Sort by token count descending
    sections_analysis.sort(key=lambda s: s["tokens"], reverse=True)

    return {
        "file": str(directory),
        "total_lines": total_lines,
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "sections": sections_analysis
    }


def print_analysis(analysis: Dict[str, Any], breakdown: str = "summary"):
    """Print analysis results in human-readable format."""
    print(f"\n=== TOKEN ANALYSIS: {Path(analysis['file']).name} ===")
    print(f"Total lines: {analysis['total_lines']:,}")
    print(f"Total characters: {analysis['total_chars']:,}")
    print(f"Total tokens: {analysis['total_tokens']:,}")

    if breakdown == "sections" and analysis['sections']:
        print(f"\n{'Section':<40} {'Lines':>7} {'Tokens':>8} {'% Total':>8}")
        print("=" * 70)

        for section in analysis['sections']:
            name = section['name']
            if len(name) > 38:
                name = name[:35] + "..."

            print(f"{name:<40} {section['lines']:>7,} {section['tokens']:>8,} {section['percent']:>7.1f}%")

        print("=" * 70)
        print(f"{'TOTAL':<40} {analysis['total_lines']:>7,} {analysis['total_tokens']:>8,} {'100.0':>7}%")


def main():
    parser = argparse.ArgumentParser(
        description="Profile token usage of prompt YAML files"
    )
    parser.add_argument(
        "prompt_path",
        type=Path,
        help="Path to prompt YAML file or directory (e.g., prompts/claude/en/dm.yaml or prompts/claude/en/dm/)"
    )
    parser.add_argument(
        "--breakdown",
        choices=["summary", "sections"],
        default="sections",
        help="Level of detail (default: sections)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for results (optional)"
    )
    parser.add_argument(
        "--model",
        default="claude-3-5-sonnet-20241022",
        help="Model name for tokenizer selection (default: claude-3-5-sonnet-20241022)"
    )

    args = parser.parse_args()

    # Check if path exists
    if not args.prompt_path.exists():
        print(f"ERROR: Path not found: {args.prompt_path}")
        sys.exit(1)

    # Analyze prompt(s)
    if args.prompt_path.is_dir():
        analysis = analyze_modular_prompts(args.prompt_path)
    else:
        analysis = analyze_monolithic_prompt(args.prompt_path)

    # Print results
    print_analysis(analysis, args.breakdown)

    # Save JSON output if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
