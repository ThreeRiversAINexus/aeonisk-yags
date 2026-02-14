# Baseline Datamining: Combat Ambush Lethality Experiment (Control)

**Date:** 2026-02-14
**Branch:** `intention-lethality-mismatch`
**Bulk Run ID:** `run_2026-02-14_113048_5276cf26`
**Output:** `multiagent_output/lethality_experiment_combat_ambush/control/models/run_2026-02-14_113048_5276cf26/`

## Files in This Directory

| File | Description |
|------|-------------|
| `README.md` | This overview |
| `experiment_design.md` | Scenario setup, character sheets, clocks, hypothesis |
| `per_session_results.md` | Raw per-session data table (20 successful + 5 failed) |
| `model_comparison.md` | Per-model aggregated stats, behavioral profiles, key findings |
| `claude_failure_analysis.md` | Root cause analysis of Anthropic Claude Opus 4.6 100% failure rate |
| `research_observations.md` | Agent psychology observations, DM behavior patterns, open questions |
| `intention_lethality_mismatch.md` | Deep-dive: suppressing fire, shock baton, and non-lethal intent vs DM adjudication |
| `enemy_npc_analysis.md` | Enemy combat behavior, NPC actions, spawning patterns, entity lifecycle per model |
| `soulcredit_moral_analysis.md` | Soulcredit system performance, moral judgments, and ethically dubious situations |

## Quick Summary

- **25 sessions** across 5 DM models (5 runs each), identical scenario
- **20 succeeded**, 5 failed (all Anthropic Claude Opus 4.6)
- **75% total party kill rate** across successful sessions
- **0% enemy kills by Gemini** (most lethal DM), **40% both-PCs-survive by Grok** (most permissive)
- **14.5M total tokens**, ~4 hours wall-clock time
- Both DM and player agents use the **same model** per config (not GPT-5 mini — naming artifact)
- **40% of player declarations contain non-lethal/suppressive intent**, but all gun-based suppression deals lethal wound damage

## Experiment Purpose

Establish a **general behavioral baseline** for multi-agent combat sessions across different LLM providers. A Pantheon Security Enforcer and a Freeborn Drifter get ambushed by street gang grunts. This control condition captures default DM and player agent behavior under neutral/ambiguous goal conditions (no explicit lethal or non-lethal instructions).

### Additional Hypothesis: Intention-Lethality Mismatch

Beyond the baseline, there is a hypothesis that **player agents intending suppressing fire or less-lethal actions (e.g., shock baton, warning shots) are having those intentions misjudged by the DM as lethal attacks**, with the DM glossing over the non-lethal intent and applying full lethal damage to PCs anyway. This mismatch between player intention and DM adjudication is a key research question the baseline data can help investigate.
