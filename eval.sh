#!/bin/bash -x

# Single-pass eval (score current prompt, no rewriting):
# python scripts/prompt_eval_harness.py --swap-module scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml --sessions ~/Coding/aeonisk-v1/lethal_intent_mismatch/control ~/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v2 --action-type combat --models openai:gpt-5-mini --scorers suppression_table damage_comparison --output-dir evals/results --save-prompts --proxy "http://localhost:8000" --direct --goal-file evals/goals/suppress_goals.yaml --classify-intent

# Scan-only with intent classification audit:
# python scripts/prompt_eval_harness.py --swap-module scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml --sessions ~/Coding/aeonisk-v1/lethal_intent_mismatch/control ~/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v2 --scan-only -v --action-type combat --goal-file evals/goals/suppress_goals.yaml --classify-intent --proxy "http://localhost:8000" --direct

# Self-judge loop with integrated regression checks and intent classification:
python scripts/prompt_eval_harness.py --swap-module scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_combat_with_suppression.yaml --sessions ~/Coding/aeonisk-v1/lethal_intent_mismatch/control ~/Coding/aeonisk-v1/lethal_intent_mismatch/treatment_v2 --self-judge --goal-file evals/goals/suppress_goals.yaml --classify-intent --judge-model anthropic:claude-sonnet-4-5 --models "openai:gpt-5.2-2025-12-11" "grok:grok-4-latest" "gemini:gemini-2.5-pro" "anthropic:claude-opus-4-6" "deepinfra:deepseek-ai/DeepSeek-V3.2" --scorers suppression_table damage_comparison --max-iterations 5 --output-dir evals/results --proxy "http://localhost:8000" --direct --workers 50
