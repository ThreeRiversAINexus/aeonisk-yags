#!/usr/bin/env python3
"""
DM Prompt Audit Script

Analyzes all DM prompt files to identify:
1. Deprecated text markers ([SESSION_END:], [SPAWN_ENEMY:], [NEW_CLOCK:])
2. Working notes (Problem:, TODO:, FIXME:, etc.)
3. File sizes and section counts
4. Redundancy and removal recommendations

Generates DM_PROMPT_AUDIT_REPORT.md with detailed findings.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


# Deprecated patterns to search for
DEPRECATED_MARKERS = [
    r'\[SESSION_END:',
    r'\[SPAWN_ENEMY:',
    r'\[DESPAWN_ENEMY:',
    r'\[NEW_CLOCK:',
    r'\[ADVANCE_STORY:',
    r'\[UPDATE_CLOCK:',
    r'\[REMOVE_CLOCK:',
]

# Working notes patterns
WORKING_NOTES = [
    r'Problem:',
    r'TODO:',
    r'FIXME:',
    r'HACK:',
    r'XXX:',
    r'NOTE:.*deprecated',
    r'Note:.*deprecated',
]

# DM prompt directory
DM_PROMPTS_DIR = Path(__file__).parent.parent / "scripts" / "aeonisk" / "multiagent" / "prompts" / "claude" / "en" / "dm"


def count_lines(file_path: Path) -> int:
    """Count total lines in file."""
    with open(file_path, 'r') as f:
        return sum(1 for _ in f)


def find_patterns(file_path: Path, patterns: List[str]) -> List[Tuple[int, str, str]]:
    """
    Find all occurrences of patterns in file.

    Returns: List of (line_number, pattern_matched, line_text)
    """
    matches = []
    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    matches.append((line_num, pattern, line.strip()))
    return matches


def analyze_yaml_structure(file_path: Path) -> Dict:
    """Analyze YAML structure to count examples, sections, etc."""
    with open(file_path, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return {"error": str(e)}

    content = data.get('content', '')

    # Count markdown headers
    headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)

    # Count code blocks (examples)
    code_blocks = re.findall(r'```', content)
    num_examples = len(code_blocks) // 2  # Each example has opening and closing ```

    # Count bullet points
    bullets = re.findall(r'^\s*[-*]\s+', content, re.MULTILINE)

    return {
        "sections": len(headers),
        "section_names": headers,
        "examples": num_examples,
        "bullet_points": len(bullets),
        "content_length": len(content),
    }


def generate_removal_recommendations(file_path: Path, deprecated_matches: List, working_notes: List, structure: Dict, line_count: int) -> Dict:
    """Generate specific removal recommendations for this file."""
    recommendations = {
        "priority": "low",
        "estimated_lines_removable": 0,
        "actions": [],
        "risk_level": "low"
    }

    # High priority if lots of deprecated markers
    if len(deprecated_matches) > 10:
        recommendations["priority"] = "high"
        recommendations["estimated_lines_removable"] += len(deprecated_matches) * 2  # Assume each marker has ~2 lines of context
        recommendations["actions"].append(f"Remove {len(deprecated_matches)} deprecated text marker references")
        recommendations["risk_level"] = "low"  # Removing deprecated stuff is safe
    elif len(deprecated_matches) > 5:
        recommendations["priority"] = "medium"
        recommendations["estimated_lines_removable"] += len(deprecated_matches) * 2
        recommendations["actions"].append(f"Remove {len(deprecated_matches)} deprecated text marker references")
        recommendations["risk_level"] = "low"

    # Working notes should be cleaned up
    if len(working_notes) > 0:
        recommendations["actions"].append(f"Remove {len(working_notes)} working notes (Problem:, TODO:, etc.)")
        recommendations["estimated_lines_removable"] += len(working_notes)
        if recommendations["priority"] == "low":
            recommendations["priority"] = "medium"

    # Very large files are candidates for splitting or condensing
    if line_count > 500:
        recommendations["actions"].append(f"Consider splitting file ({line_count} lines is very large)")
        recommendations["priority"] = "high"
        recommendations["risk_level"] = "medium"  # Splitting requires careful testing
    elif line_count > 300:
        recommendations["actions"].append(f"Large file ({line_count} lines) - review for redundancy")
        if recommendations["priority"] == "low":
            recommendations["priority"] = "medium"

    # Lots of examples might indicate redundancy
    if structure.get("examples", 0) > 10:
        recommendations["actions"].append(f"Many examples ({structure['examples']}) - consider consolidating most common cases")
        recommendations["estimated_lines_removable"] += structure["examples"] * 5  # Rough estimate
        recommendations["risk_level"] = "high"  # Removing examples affects LLM behavior

    return recommendations


def audit_dm_prompts():
    """Main audit function."""
    print("🔍 Auditing DM Prompts...")
    print(f"📁 Scanning directory: {DM_PROMPTS_DIR}\n")

    results = {}
    total_lines = 0
    total_deprecated = 0
    total_working_notes = 0

    # Find all YAML files
    yaml_files = sorted(DM_PROMPTS_DIR.glob("dm_*.yaml"))

    for yaml_file in yaml_files:
        print(f"📄 Analyzing {yaml_file.name}...")

        line_count = count_lines(yaml_file)
        total_lines += line_count

        deprecated_matches = find_patterns(yaml_file, DEPRECATED_MARKERS)
        total_deprecated += len(deprecated_matches)

        working_notes = find_patterns(yaml_file, WORKING_NOTES)
        total_working_notes += len(working_notes)

        structure = analyze_yaml_structure(yaml_file)

        recommendations = generate_removal_recommendations(
            yaml_file, deprecated_matches, working_notes, structure, line_count
        )

        results[yaml_file.name] = {
            "line_count": line_count,
            "deprecated_markers": deprecated_matches,
            "working_notes": working_notes,
            "structure": structure,
            "recommendations": recommendations
        }

    print(f"\n✅ Audit complete!")
    print(f"📊 Total DM prompt lines: {total_lines}")
    print(f"⚠️  Deprecated markers found: {total_deprecated}")
    print(f"📝 Working notes found: {total_working_notes}\n")

    return results, total_lines


def generate_markdown_report(results: Dict, total_lines: int) -> str:
    """Generate markdown audit report."""
    report = []
    report.append("# DM Prompt Audit Report\n")
    report.append(f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Total DM Prompt Lines:** {total_lines}\n")

    # Summary statistics
    total_deprecated = sum(len(r["deprecated_markers"]) for r in results.values())
    total_working_notes = sum(len(r["working_notes"]) for r in results.values())
    total_removable = sum(r["recommendations"]["estimated_lines_removable"] for r in results.values())

    report.append("## Summary\n")
    report.append(f"- **Files analyzed:** {len(results)}")
    report.append(f"- **Total lines:** {total_lines}")
    report.append(f"- **Deprecated markers found:** {total_deprecated}")
    report.append(f"- **Working notes found:** {total_working_notes}")
    report.append(f"- **Estimated removable lines:** {total_removable} ({int(total_removable/total_lines*100)}% reduction)")
    report.append("")

    # Sort files by priority
    high_priority = [(name, data) for name, data in results.items() if data["recommendations"]["priority"] == "high"]
    medium_priority = [(name, data) for name, data in results.items() if data["recommendations"]["priority"] == "medium"]
    low_priority = [(name, data) for name, data in results.items() if data["recommendations"]["priority"] == "low"]

    # High priority files
    if high_priority:
        report.append("## 🔴 High Priority Files\n")
        for filename, data in sorted(high_priority, key=lambda x: x[1]["line_count"], reverse=True):
            report.append(f"### {filename}\n")
            report.append(f"- **Lines:** {data['line_count']}")
            report.append(f"- **Deprecated markers:** {len(data['deprecated_markers'])}")
            report.append(f"- **Working notes:** {len(data['working_notes'])}")
            report.append(f"- **Estimated removable:** {data['recommendations']['estimated_lines_removable']} lines")
            report.append(f"- **Risk level:** {data['recommendations']['risk_level']}\n")
            report.append("**Actions:**")
            for action in data["recommendations"]["actions"]:
                report.append(f"  - {action}")
            report.append("")

    # Medium priority files
    if medium_priority:
        report.append("## 🟡 Medium Priority Files\n")
        for filename, data in sorted(medium_priority, key=lambda x: x[1]["line_count"], reverse=True):
            report.append(f"### {filename}\n")
            report.append(f"- **Lines:** {data['line_count']}")
            report.append(f"- **Deprecated markers:** {len(data['deprecated_markers'])}")
            report.append(f"- **Working notes:** {len(data['working_notes'])}")
            report.append(f"- **Estimated removable:** {data['recommendations']['estimated_lines_removable']} lines\n")
            if data["recommendations"]["actions"]:
                report.append("**Actions:**")
                for action in data["recommendations"]["actions"]:
                    report.append(f"  - {action}")
            report.append("")

    # Low priority files (brief summary)
    if low_priority:
        report.append("## 🟢 Low Priority Files\n")
        report.append("These files appear to be in good shape:\n")
        for filename, data in sorted(low_priority, key=lambda x: x[1]["line_count"], reverse=True):
            report.append(f"- **{filename}** ({data['line_count']} lines)")
        report.append("")

    # Detailed findings section
    report.append("## Detailed Findings\n")

    for filename, data in sorted(results.items(), key=lambda x: x[1]["line_count"], reverse=True):
        report.append(f"### {filename}\n")
        report.append(f"**File Statistics:**")
        report.append(f"- Lines: {data['line_count']}")
        report.append(f"- Sections: {data['structure'].get('sections', 0)}")
        report.append(f"- Examples: {data['structure'].get('examples', 0)}")
        report.append(f"- Bullet points: {data['structure'].get('bullet_points', 0)}")
        report.append("")

        if data["deprecated_markers"]:
            report.append(f"**Deprecated Markers ({len(data['deprecated_markers'])}):**")
            for line_num, pattern, line_text in data["deprecated_markers"][:5]:  # Show first 5
                report.append(f"  - Line {line_num}: `{pattern}` → {line_text[:80]}")
            if len(data["deprecated_markers"]) > 5:
                report.append(f"  - ... and {len(data['deprecated_markers']) - 5} more")
            report.append("")

        if data["working_notes"]:
            report.append(f"**Working Notes ({len(data['working_notes'])}):**")
            for line_num, pattern, line_text in data["working_notes"]:
                report.append(f"  - Line {line_num}: `{pattern}` → {line_text[:80]}")
            report.append("")

        report.append("---\n")

    return "\n".join(report)


if __name__ == "__main__":
    results, total_lines = audit_dm_prompts()

    # Generate markdown report
    report_content = generate_markdown_report(results, total_lines)

    # Write to file
    report_path = Path(__file__).parent.parent / "DM_PROMPT_AUDIT_REPORT.md"
    with open(report_path, 'w') as f:
        f.write(report_content)

    print(f"📋 Report written to: {report_path}")
    print("\nTop 3 recommendations:")

    # Show top 3 high-priority items
    high_priority_items = [
        (name, data) for name, data in results.items()
        if data["recommendations"]["priority"] == "high"
    ]

    for filename, data in sorted(high_priority_items, key=lambda x: x[1]["recommendations"]["estimated_lines_removable"], reverse=True)[:3]:
        print(f"\n  {filename}:")
        for action in data["recommendations"]["actions"]:
            print(f"    - {action}")
