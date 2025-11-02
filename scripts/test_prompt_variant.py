#!/usr/bin/env python3
"""
Test alternate prompt files against baseline fixtures.

Replays fixtures with new prompts and compares mechanical outcomes.

Usage:
    # Test new DM prompt
    python scripts/test_prompt_variant.py \
        --baseline tests/fixtures/sessions/baseline_combat.jsonl \
        --dm-prompt prompts/claude/en/dm_v2.yaml \
        --output /tmp/variant_test.jsonl

    # Test new player prompt
    python scripts/test_prompt_variant.py \
        --baseline tests/fixtures/sessions/baseline_combat.jsonl \
        --player-prompt prompts/claude/en/player_v2.yaml \
        --output /tmp/variant_test.jsonl

    # Test modular DM prompts (directory)
    python scripts/test_prompt_variant.py \
        --baseline tests/fixtures/sessions/baseline_combat.jsonl \
        --dm-prompt-dir prompts/claude/en/dm/ \
        --output /tmp/variant_test.jsonl

    # Auto-diff and report
    python scripts/test_prompt_variant.py \
        --baseline tests/fixtures/sessions/baseline_combat.jsonl \
        --dm-prompt prompts/claude/en/dm_v2.yaml \
        --output /tmp/variant_test.jsonl \
        --diff \
        --report /tmp/variant_report.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def replay_fixture_with_prompts(
    baseline_path: Path,
    output_path: Path,
    dm_prompt: Optional[Path] = None,
    dm_prompt_dir: Optional[Path] = None,
    player_prompt: Optional[Path] = None,
    cache_mode: str = "player_actions",
    max_rounds: Optional[int] = None,
) -> bool:
    """
    Replay fixture with alternate prompts using replay_fixture.py.

    Args:
        baseline_path: Path to baseline fixture JSONL
        output_path: Path to output replayed session
        dm_prompt: Path to alternate DM prompt YAML (single file)
        dm_prompt_dir: Path to alternate DM prompt directory (modular)
        player_prompt: Path to alternate player prompt YAML
        cache_mode: "all" (all cached), "player_actions" (players cached, DM live), "none" (all live)
        max_rounds: Optional max rounds to replay

    Returns:
        True if replay succeeded, False otherwise
    """
    cmd = [
        sys.executable,
        "scripts/replay_fixture.py",
        str(baseline_path),
        "--output", str(output_path),
    ]

    # Add cache mode flags
    if cache_mode == "all":
        cmd.append("--all-cached")
    elif cache_mode == "player_actions":
        cmd.append("--cache-player-actions")
    elif cache_mode == "none":
        cmd.append("--no-cache")
    else:
        raise ValueError(f"Invalid cache_mode: {cache_mode}")

    # Add max rounds if specified
    if max_rounds:
        cmd.extend(["--max-rounds", str(max_rounds)])

    # Set environment variables for alternate prompts
    env = {}
    if dm_prompt:
        env["AEONISK_DM_PROMPT"] = str(dm_prompt)
    if dm_prompt_dir:
        env["AEONISK_DM_PROMPT_DIR"] = str(dm_prompt_dir)
    if player_prompt:
        env["AEONISK_PLAYER_PROMPT"] = str(player_prompt)

    print(f"\n=== REPLAYING FIXTURE ===")
    print(f"Baseline: {baseline_path}")
    print(f"Output: {output_path}")
    print(f"Cache mode: {cache_mode}")
    if dm_prompt:
        print(f"DM prompt: {dm_prompt}")
    if dm_prompt_dir:
        print(f"DM prompt dir: {dm_prompt_dir}")
    if player_prompt:
        print(f"Player prompt: {player_prompt}")
    print()

    # Run replay
    try:
        result = subprocess.run(
            cmd,
            env={**subprocess.os.environ, **env} if env else None,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        if result.returncode != 0:
            print(f"ERROR: Replay failed with exit code {result.returncode}")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            return False

        print(f"✓ Replay succeeded")
        return True

    except subprocess.TimeoutExpired:
        print("ERROR: Replay timed out (>10 minutes)")
        return False
    except Exception as e:
        print(f"ERROR: Replay failed with exception: {e}")
        return False


def diff_fixtures(
    baseline_path: Path,
    variant_path: Path,
    focus_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Compare baseline and variant fixtures using diff_fixtures.py.

    Args:
        baseline_path: Path to baseline fixture
        variant_path: Path to variant fixture
        focus_fields: Optional list of fields to focus on (e.g., ["effects.damage.dealt"])

    Returns:
        Dict with diff results:
        {
            "identical": bool,
            "differences": List[Dict],
            "summary": str
        }
    """
    cmd = [
        sys.executable,
        "scripts/diff_fixtures.py",
        str(baseline_path),
        str(variant_path),
        "--json",
    ]

    if focus_fields:
        cmd.extend(["--focus"] + focus_fields)

    print(f"\n=== DIFFING FIXTURES ===")
    print(f"Baseline: {baseline_path}")
    print(f"Variant: {variant_path}")
    if focus_fields:
        print(f"Focus fields: {', '.join(focus_fields)}")
    print()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse JSON output
        try:
            diff_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Fallback: parse text output
            diff_data = {
                "identical": result.returncode == 0,
                "differences": [],
                "summary": result.stdout,
            }

        return diff_data

    except subprocess.TimeoutExpired:
        print("ERROR: Diff timed out (>60 seconds)")
        return {"identical": False, "differences": [], "summary": "Timeout"}
    except Exception as e:
        print(f"ERROR: Diff failed with exception: {e}")
        return {"identical": False, "differences": [], "summary": str(e)}


def validate_session_schema(session_path: Path) -> Dict[str, Any]:
    """
    Validate session JSONL against schemas using validate_logging.py.

    Returns:
        {
            "valid": bool,
            "errors": List[str],
            "success_rate": float
        }
    """
    cmd = [
        sys.executable,
        "scripts/aeonisk/multiagent/validate_logging.py",
        str(session_path),
    ]

    print(f"\n=== VALIDATING SCHEMA ===")
    print(f"Session: {session_path}")
    print()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse output for validation results
        output = result.stdout
        errors = []
        success_rate = 1.0

        # Look for validation errors in output
        for line in output.split('\n'):
            if "ERROR" in line or "FAILED" in line:
                errors.append(line.strip())
            if "success rate" in line.lower():
                # Try to extract success rate (e.g., "95.2% success rate")
                try:
                    rate_str = line.split('%')[0].split()[-1]
                    success_rate = float(rate_str) / 100.0
                except (ValueError, IndexError):
                    pass

        return {
            "valid": result.returncode == 0,
            "errors": errors,
            "success_rate": success_rate,
            "output": output,
        }

    except subprocess.TimeoutExpired:
        print("ERROR: Validation timed out (>60 seconds)")
        return {"valid": False, "errors": ["Timeout"], "success_rate": 0.0}
    except Exception as e:
        print(f"ERROR: Validation failed with exception: {e}")
        return {"valid": False, "errors": [str(e)], "success_rate": 0.0}


def analyze_token_usage(session_path: Path) -> Dict[str, Any]:
    """
    Analyze token usage from session using analyze_session.py.

    Returns:
        {
            "total_tokens": int,
            "avg_tokens_per_round": float,
            "dm_tokens": int,
            "player_tokens": int,
        }
    """
    cmd = [
        sys.executable,
        "scripts/analyze_session.py",
        str(session_path),
        "--search", "event_type=llm_call",
        "--fields", "source,tokens_used",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Parse JSON output (each line is a JSON object)
        dm_tokens = 0
        player_tokens = 0
        total_tokens = 0

        for line in result.stdout.strip().split('\n'):
            if not line or line.startswith("Found"):
                continue

            try:
                event = json.loads(line)
                tokens = event.get("tokens_used", 0)
                source = event.get("source", "")

                if "dm" in source.lower():
                    dm_tokens += tokens
                elif "player" in source.lower():
                    player_tokens += tokens

                total_tokens += tokens
            except json.JSONDecodeError:
                continue

        # Get round count
        cmd_rounds = [
            sys.executable,
            "scripts/analyze_session.py",
            str(session_path),
            "--mode", "summary",
        ]
        result_rounds = subprocess.run(cmd_rounds, capture_output=True, text=True, timeout=30)
        rounds = 1

        for line in result_rounds.stdout.split('\n'):
            if "Rounds:" in line:
                try:
                    rounds = int(line.split("Rounds:")[1].split("|")[0].strip())
                except (ValueError, IndexError):
                    pass

        return {
            "total_tokens": total_tokens,
            "avg_tokens_per_round": total_tokens / rounds if rounds > 0 else 0,
            "dm_tokens": dm_tokens,
            "player_tokens": player_tokens,
            "rounds": rounds,
        }

    except Exception as e:
        print(f"WARNING: Token analysis failed: {e}")
        return {
            "total_tokens": 0,
            "avg_tokens_per_round": 0,
            "dm_tokens": 0,
            "player_tokens": 0,
            "rounds": 0,
        }


def generate_report(
    baseline_path: Path,
    variant_path: Path,
    diff_results: Dict[str, Any],
    validation_results: Dict[str, Any],
    token_results: Dict[str, Any],
    baseline_tokens: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate comprehensive test report."""
    report = {
        "baseline": str(baseline_path),
        "variant": str(variant_path),
        "timestamp": subprocess.run(["date", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True).stdout.strip(),
        "results": {
            "mechanical_parity": diff_results.get("identical", False),
            "schema_valid": validation_results.get("valid", False),
            "schema_success_rate": validation_results.get("success_rate", 0.0),
        },
        "token_usage": token_results,
        "token_comparison": {},
        "differences": diff_results.get("differences", []),
        "validation_errors": validation_results.get("errors", []),
    }

    # Add token comparison if baseline provided
    if baseline_tokens:
        baseline_total = baseline_tokens.get("total_tokens", 0)
        variant_total = token_results.get("total_tokens", 0)
        if baseline_total > 0:
            savings = baseline_total - variant_total
            savings_pct = (savings / baseline_total) * 100
            report["token_comparison"] = {
                "baseline_tokens": baseline_total,
                "variant_tokens": variant_total,
                "savings": savings,
                "savings_percent": savings_pct,
            }

    return report


def print_report(report: Dict[str, Any]):
    """Print human-readable test report."""
    print("\n" + "="*70)
    print("PROMPT VARIANT TEST REPORT")
    print("="*70)
    print(f"Baseline: {report['baseline']}")
    print(f"Variant: {report['variant']}")
    print(f"Timestamp: {report['timestamp']}")
    print()

    results = report['results']
    print("RESULTS:")
    print(f"  Mechanical Parity: {'✓ PASS' if results['mechanical_parity'] else '✗ FAIL'}")
    print(f"  Schema Valid: {'✓ PASS' if results['schema_valid'] else '✗ FAIL'}")
    print(f"  Schema Success Rate: {results['schema_success_rate']*100:.1f}%")
    print()

    token_usage = report.get('token_usage', {})
    if token_usage and token_usage.get('total_tokens', 0) > 0:
        print("TOKEN USAGE:")
        print(f"  Total: {token_usage['total_tokens']:,}")
        print(f"  Avg per round: {token_usage['avg_tokens_per_round']:,.0f}")
        print(f"  DM: {token_usage['dm_tokens']:,}")
        print(f"  Players: {token_usage['player_tokens']:,}")
    else:
        print("TOKEN USAGE: (not analyzed)")

    if report['token_comparison']:
        comp = report['token_comparison']
        print()
        print("TOKEN COMPARISON:")
        print(f"  Baseline: {comp['baseline_tokens']:,}")
        print(f"  Variant: {comp['variant_tokens']:,}")
        print(f"  Savings: {comp['savings']:,} ({comp['savings_percent']:+.1f}%)")

    if report['differences']:
        print()
        print(f"MECHANICAL DIFFERENCES: {len(report['differences'])}")
        for i, diff in enumerate(report['differences'][:5], 1):
            print(f"  {i}. {diff}")
        if len(report['differences']) > 5:
            print(f"  ... and {len(report['differences']) - 5} more")

    if report['validation_errors']:
        print()
        print(f"VALIDATION ERRORS: {len(report['validation_errors'])}")
        for i, error in enumerate(report['validation_errors'][:5], 1):
            print(f"  {i}. {error}")
        if len(report['validation_errors']) > 5:
            print(f"  ... and {len(report['validation_errors']) - 5} more")

    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description="Test alternate prompts against baseline fixtures"
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Path to baseline fixture JSONL"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output replayed session"
    )
    parser.add_argument(
        "--dm-prompt",
        type=Path,
        help="Path to alternate DM prompt YAML (single file)"
    )
    parser.add_argument(
        "--dm-prompt-dir",
        type=Path,
        help="Path to alternate DM prompt directory (modular)"
    )
    parser.add_argument(
        "--player-prompt",
        type=Path,
        help="Path to alternate player prompt YAML"
    )
    parser.add_argument(
        "--cache-mode",
        choices=["all", "player_actions", "none"],
        default="player_actions",
        help="Cache mode for replay (default: player_actions)"
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        help="Max rounds to replay (optional)"
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Run diff after replay"
    )
    parser.add_argument(
        "--focus",
        nargs="+",
        help="Fields to focus on in diff (e.g., effects.damage.dealt)"
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Path to save JSON report"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate schema after replay"
    )
    parser.add_argument(
        "--analyze-tokens",
        action="store_true",
        help="Analyze token usage after replay"
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.baseline.exists():
        print(f"ERROR: Baseline fixture not found: {args.baseline}")
        sys.exit(1)

    if args.dm_prompt and not args.dm_prompt.exists():
        print(f"ERROR: DM prompt not found: {args.dm_prompt}")
        sys.exit(1)

    if args.dm_prompt_dir and not args.dm_prompt_dir.exists():
        print(f"ERROR: DM prompt directory not found: {args.dm_prompt_dir}")
        sys.exit(1)

    if args.player_prompt and not args.player_prompt.exists():
        print(f"ERROR: Player prompt not found: {args.player_prompt}")
        sys.exit(1)

    # Step 1: Replay fixture
    success = replay_fixture_with_prompts(
        baseline_path=args.baseline,
        output_path=args.output,
        dm_prompt=args.dm_prompt,
        dm_prompt_dir=args.dm_prompt_dir,
        player_prompt=args.player_prompt,
        cache_mode=args.cache_mode,
        max_rounds=args.max_rounds,
    )

    if not success:
        print("\n✗ Replay failed, aborting test")
        sys.exit(1)

    # Step 2: Diff (if requested)
    diff_results = {}
    if args.diff:
        diff_results = diff_fixtures(
            baseline_path=args.baseline,
            variant_path=args.output,
            focus_fields=args.focus,
        )

    # Step 3: Validate (if requested)
    validation_results = {}
    if args.validate:
        validation_results = validate_session_schema(args.output)

    # Step 4: Analyze tokens (if requested)
    token_results = {}
    baseline_tokens = {}
    if args.analyze_tokens:
        token_results = analyze_token_usage(args.output)
        baseline_tokens = analyze_token_usage(args.baseline)

    # Step 5: Generate report
    if args.report or args.diff or args.validate or args.analyze_tokens:
        report = generate_report(
            baseline_path=args.baseline,
            variant_path=args.output,
            diff_results=diff_results,
            validation_results=validation_results,
            token_results=token_results,
            baseline_tokens=baseline_tokens if baseline_tokens else None,
        )

        # Print report
        print_report(report)

        # Save JSON report
        if args.report:
            with open(args.report, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"\n✓ Report saved to {args.report}")

    print("\n✓ Test complete")


if __name__ == "__main__":
    main()
