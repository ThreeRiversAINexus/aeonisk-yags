#!/bin/bash -x

# Single-pass eval (score current prompt, no rewriting):
# python scripts/prompt_eval_harness.py --swap-module scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml --sessions ~/Coding/aeonisk-v1/lethal_intent_mismatch/control ~/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v2 --action-type combat --intent-keywords suppress "covering fire" "pin down" "warning shot" --weapon-damage-type wound --models openai:gpt-5-mini --scorers suppression_table damage_comparison --output-dir evals/results --save-prompts --proxy "http://localhost:8000" --direct

# Scan-only: verify lethal case filtering (exclude suppression):
# python scripts/prompt_eval_harness.py --swap-module scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml --sessions ~/Coding/aeonisk-v1/lethal_intent_mismatch/control --scan-only --action-type combat --weapon-damage-type wound --exclude-keywords suppress "covering fire" "pin down" "pin them" "warning shot"

# Self-judge loop with integrated regression checks (Claude Sonnet 4.5 rewrites, GPT-5-mini evaluates):
python scripts/prompt_eval_harness.py --swap-module scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml --sessions ~/Coding/aeonisk-v1/lethal_intent_mismatch/control ~/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v2 --self-judge --goal-file evals/goals/suppress_goals.yaml --judge-model anthropic:claude-sonnet-4-5 --models openai:gpt-5-mini --scorers suppression_table damage_comparison --max-iterations 5 --output-dir evals/results --proxy "http://localhost:8000" --direct --workers 50
