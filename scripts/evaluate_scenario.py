#!/usr/bin/env python3
"""
Complete workflow: Create scenario → Run evaluation → Analyze results

This is the end-to-end script for PettingZoo-based scenario evaluation.

Usage:
    # Create and evaluate a new scenario
    python3 evaluate_scenario.py --create heist --runs 10

    # Evaluate existing scenario config
    python3 evaluate_scenario.py --config session_config_heist.json --runs 20

    # Quick test run
    python3 evaluate_scenario.py --quick-test
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / 'aeonisk'))


def create_scenario_template(scenario_type: str, max_turns: int = 15) -> Dict[str, Any]:
    """
    Create a scenario configuration template.

    Args:
        scenario_type: Type of scenario (combat, investigation, heist, survival, social)
        max_turns: Maximum rounds for the scenario

    Returns:
        Complete session configuration dict
    """

    templates = {
        "combat": {
            "session_name": f"combat_eval_{datetime.now().strftime('%Y%m%d')}",
            "max_turns": max_turns,
            "party_size": 2,
            "force_combat": True,
            "notes": "Combat evaluation - gang confrontation, security breach, or hostile encounter. Test tactical decision-making and combat efficiency.",
            "clocks_hint": "Enemy Reinforcements (danger), Civilian Safety (safety), Tactical Advantage (investigation)"
        },

        "investigation": {
            "session_name": f"investigation_eval_{datetime.now().strftime('%Y%m%d')}",
            "max_turns": max_turns,
            "party_size": 2,
            "force_combat": False,
            "notes": "Investigation scenario - void contamination at corporate facility. Gather evidence, interview witnesses, discover source. Combat possible if discovered. Focus on information gathering and social skills.",
            "clocks_hint": "Evidence Collection (investigation), Corporate Suspicion (danger), Contamination Spread (time)"
        },

        "heist": {
            "session_name": f"heist_eval_{datetime.now().strftime('%Y%m%d')}",
            "max_turns": max_turns,
            "party_size": 2,
            "force_combat": False,
            "notes": "Heist scenario - infiltrate secure facility to recover stolen data. Stealth preferred, but security response possible. Multiple approaches: social engineering, hacking, or force. Test multi-skill problem solving.",
            "clocks_hint": "Infiltration Progress (investigation), Security Alert (danger), Data Recovery (investigation)"
        },

        "survival": {
            "session_name": f"survival_eval_{datetime.now().strftime('%Y%m%d')}",
            "max_turns": max_turns * 2,  # Survival takes longer
            "party_size": 2,
            "force_combat": False,
            "notes": "Survival scenario - stranded during void storm on abandoned station. Repair systems, manage void exposure, find rescue. Void-corrupted creatures possible. Test resource management and adaptation.",
            "clocks_hint": "Station Integrity (danger), Void Corruption (danger), Escape Route (investigation)"
        },

        "social": {
            "session_name": f"social_eval_{datetime.now().strftime('%Y%m%d')}",
            "max_turns": max_turns,
            "party_size": 2,
            "force_combat": False,
            "notes": "Social conflict scenario - negotiation with rival faction over territory/resources. Intimidation, persuasion, or deception viable. Violence possible but costly. Test social skill mastery.",
            "clocks_hint": "Negotiation Progress (investigation), Faction Tension (danger), Alliance Building (investigation)"
        }
    }

    if scenario_type not in templates:
        print(f"Unknown scenario type: {scenario_type}")
        print(f"Available types: {', '.join(templates.keys())}")
        sys.exit(1)

    template = templates[scenario_type]

    # Build complete config
    config = {
        "session_name": template["session_name"],
        "max_turns": template["max_turns"],
        "party_size": template["party_size"],
        "output_dir": "./multiagent_output",
        "enable_human_interface": False,  # Automated evaluation
        "force_combat": template.get("force_combat", False),
        "vendor_spawn_frequency": 0,  # Disable for focused evaluation

        "tactical_module_enabled": True,
        "enemy_agents_enabled": True,

        "enemy_agent_config": {
            "allow_groups": True,
            "max_enemies_per_combat": 10,
            "shared_intel_enabled": True,
            "auto_execute_reactions": True,
            "loot_suggestions_enabled": True,
            "void_tracking_enabled": True
        },

        "agents": {
            "dm": {
                "llm": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.7
                }
            },
            "players": [
                {
                    "name": "Agent Alpha",
                    "pronouns": "they/them",
                    "faction": "Neutral Operative",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-3-5-sonnet-20241022",
                        "temperature": 0.8
                    },
                    "personality": {
                        "riskTolerance": 6,
                        "voidCuriosity": 3,
                        "bondPreference": "neutral",
                        "ritualConservatism": 5
                    },
                    "goals": [
                        "Complete mission objectives efficiently",
                        "Minimize collateral damage and void exposure",
                        "Gather actionable intelligence"
                    ],
                    "attributes": {
                        "Strength": 3, "Agility": 4, "Endurance": 4,
                        "Perception": 4, "Intelligence": 4, "Empathy": 3,
                        "Willpower": 3, "Charisma": 3, "Size": 5
                    },
                    "skills": {
                        "Combat": 4, "Guns": 4, "Stealth": 4,
                        "Investigation": 4, "Awareness": 4, "Athletics": 3
                    },
                    "equipped_weapons": {"primary": "pistol", "sidearm": "combat_knife"},
                    "inventory": {"pistol": 1, "combat_knife": 1, "med_kit": 1}
                },
                {
                    "name": "Agent Beta",
                    "pronouns": "they/them",
                    "faction": "Neutral Operative",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-3-5-sonnet-20241022",
                        "temperature": 0.8
                    },
                    "personality": {
                        "riskTolerance": 5,
                        "voidCuriosity": 4,
                        "bondPreference": "neutral",
                        "ritualConservatism": 6
                    },
                    "goals": [
                        "Support team objectives tactically",
                        "Manage resources and void risk",
                        "Adapt strategy to changing conditions"
                    ],
                    "attributes": {
                        "Strength": 3, "Agility": 4, "Endurance": 3,
                        "Perception": 4, "Intelligence": 4, "Empathy": 4,
                        "Willpower": 4, "Charisma": 3, "Size": 5
                    },
                    "skills": {
                        "Combat": 4, "Stealth": 4, "Investigation": 4,
                        "Awareness": 4, "Persuasion": 3, "Intimidation": 3
                    },
                    "equipped_weapons": {"primary": "pistol", "sidearm": "combat_knife"},
                    "inventory": {"pistol": 1, "combat_knife": 1, "med_kit": 1}
                }
            ]
        },

        "notes": template["notes"],
        "_clocks_hint": template.get("clocks_hint", "")
    }

    return config


def run_evaluation_batch(config_path: str, num_runs: int, parallel: int = 4) -> str:
    """
    Run batch evaluation using run_success_at_n.py

    Returns:
        Path to generated report
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"./evaluation_reports/eval_{timestamp}.md"

    # Ensure report directory exists
    Path("./evaluation_reports").mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"RUNNING EVALUATION BATCH")
    print(f"{'='*60}")
    print(f"Config: {config_path}")
    print(f"Runs: {num_runs} (parallel: {parallel})")
    print(f"Report: {report_path}\n")

    # Run the evaluation
    cmd = [
        sys.executable,
        "run_success_at_n.py",
        "--config", config_path,
        "--runs", str(num_runs),
        "--parallel", str(parallel),
        "--report", report_path,
        "--n-values", "5,10,15,20"
    ]

    result = subprocess.run(cmd, cwd=Path(__file__).parent)

    if result.returncode == 0:
        print(f"\n✓ Evaluation complete! Report: {report_path}")
        return report_path
    else:
        print(f"\n✗ Evaluation failed with code {result.returncode}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end scenario evaluation workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create and evaluate combat scenario (10 runs)
  python3 evaluate_scenario.py --create combat --runs 10

  # Create investigation scenario with 15-round limit
  python3 evaluate_scenario.py --create investigation --max-turns 15 --runs 20

  # Evaluate existing config
  python3 evaluate_scenario.py --config my_scenario.json --runs 10

  # Quick test (3 runs, 2 parallel)
  python3 evaluate_scenario.py --create heist --quick-test

Available scenario types:
  - combat: Tactical combat scenarios
  - investigation: Evidence gathering, stealth
  - heist: Infiltration with multiple approaches
  - survival: Resource management under pressure
  - social: Negotiation, intimidation, persuasion
        """
    )

    parser.add_argument(
        '--create',
        type=str,
        choices=['combat', 'investigation', 'heist', 'survival', 'social'],
        help='Create new scenario config of this type'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Use existing scenario config file'
    )

    parser.add_argument(
        '--max-turns',
        type=int,
        default=15,
        help='Maximum turns for created scenario (default: 15)'
    )

    parser.add_argument(
        '--runs',
        type=int,
        default=10,
        help='Number of evaluation runs (default: 10)'
    )

    parser.add_argument(
        '--parallel',
        type=int,
        default=4,
        help='Parallel sessions (default: 4)'
    )

    parser.add_argument(
        '--quick-test',
        action='store_true',
        help='Quick test: 3 runs, 2 parallel'
    )

    parser.add_argument(
        '--save-config',
        type=str,
        help='Save created config to this path'
    )

    args = parser.parse_args()

    # Quick test mode
    if args.quick_test:
        args.runs = 3
        args.parallel = 2
        print("🚀 Quick test mode: 3 runs, 2 parallel")

    # Determine config path
    if args.create:
        # Create new scenario config
        print(f"\n📝 Creating {args.create} scenario config...")
        config = create_scenario_template(args.create, args.max_turns)

        # Save config
        if args.save_config:
            config_path = args.save_config
        else:
            config_path = f"session_config_eval_{args.create}_{datetime.now().strftime('%Y%m%d')}.json"

        Path(config_path).write_text(json.dumps(config, indent=2))
        print(f"✓ Config saved: {config_path}")
        print(f"\nScenario: {config['notes']}")
        print(f"Max turns: {config['max_turns']}")
        print(f"Clocks hint: {config.get('_clocks_hint', 'Auto-generated')}")

    elif args.config:
        # Use existing config
        config_path = args.config
        if not Path(config_path).exists():
            print(f"Error: Config not found: {config_path}")
            return 1
        print(f"\n📋 Using existing config: {config_path}")

    else:
        print("Error: Must specify --create or --config")
        parser.print_help()
        return 1

    # Run evaluation
    print(f"\n{'='*60}")
    print("STEP 1: CREATE SCENARIO CONFIG ✓")
    print("STEP 2: RUN EVALUATION BATCH...")
    print(f"{'='*60}\n")

    report_path = run_evaluation_batch(config_path, args.runs, args.parallel)

    if report_path and Path(report_path).exists():
        print(f"\n{'='*60}")
        print("STEP 3: VIEW RESULTS")
        print(f"{'='*60}\n")

        # Show summary from report
        with open(report_path) as f:
            lines = f.readlines()

        # Find and display summary table
        in_table = False
        for line in lines:
            if "Success Rates by Round Threshold" in line:
                in_table = True
            if in_table:
                print(line.rstrip())
                if line.startswith("## Detailed"):
                    break

        print(f"\n📊 Full report: {report_path}")
        print(f"\n{'='*60}")
        print("EVALUATION COMPLETE!")
        print(f"{'='*60}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
