# Research Observations: Agent Psychology & DM Behavior

## Overview

These observations are preliminary — drawn from 20 successful sessions across 4 DM models. Sample sizes are small (n=5 per model). Patterns noted here are hypotheses for future investigation, not conclusions.

---

## 1. The DM Lethality Spectrum

Models range from maximally lethal to narratively permissive:

```
Most Lethal ←————————————————————————→ Most Permissive
  Gemini 2.5 Pro   DeepSeek V3.2   GPT-5.2   Grok 4
  (100% TPK)       (80% TPK)       (60%)     (60% TPK, 40% full survival)
```

**Key distinction:** Grok 4 and GPT-5.2 share the same TPK rate (60%), but Grok's non-TPK sessions have BOTH PCs surviving at high HP (one at full 27/27), while GPT-5.2's non-TPK sessions have only Kael surviving. Grok's outcomes are bimodal; GPT-5.2's are consistently "Kael lives, Sable dies."

## 2. Gemini's Zero Enemy Kill Rate

The most striking finding: **Gemini 2.5 Pro never allowed PCs to defeat a single enemy across 47 spawned enemies in 25 combat rounds.** Every other model had enemies die regularly.

Possible explanations to investigate:
- **DM narration overrides mechanics:** Gemini may describe PC attacks as "grazing" or "missing" even when mechanics say they hit
- **Damage asymmetry:** Gemini may assign low `base_damage` values in ActionResolution for PC attacks vs high values for enemy attacks
- **Rapid enemy spawning:** By round 3-4, PCs are overwhelmed before finishing anyone off
- **Soak/armor inflation:** Gemini's DM may give enemies unreasonably high effective soak

**Action item:** Deep-dive into `combat_action` and `action_resolution` events from Gemini sessions to verify whether PC attacks are mechanically successful but damage is absorbed, or whether the DM is declaring misses/grazes.

## 3. Sable's Asymmetric Vulnerability

Across ALL 20 sessions, Sable (Freeborn Drifter) is more likely to die than Kael (Pantheon Enforcer):

| Stat | Kael | Sable |
|------|------|-------|
| Times alive at end | 5/20 (25%) | 4/20 (20%) |
| Times dead (not just unconscious) | 3/20 (15%) | 4/20 (20%) |
| Avg final HP when surviving | 15.0 | 25.0 |

**Confounding factors:**
- Kael has Riot Carapace armor (higher soak)
- Sable has no non-lethal options (may escalate combat faster)
- Sable's Risk Tolerance is 8 vs Kael's 6 (may take riskier actions as player agent)
- Sable's Empathy is 2 vs Kael's 3 (may be less effective at de-escalation)
- **Both DM and player agents are the same model** — hard to separate DM bias from player strategy

**Note:** When Sable survives, they tend to be at high HP (23-27). This suggests either the session went well for everyone (Grok's allied NPC pattern) or the session barely started (unlikely given round counts).

## 4. NPC Behavior as Model Fingerprint

NPC action distributions are strikingly model-specific:

| Model | Dominant NPC Pattern | Interpretation |
|-------|---------------------|----------------|
| GPT-5.2 | hide (67%) | NPCs are background decoration, stay out of combat |
| Grok 4 | flee (30%), attack (16%), heal (14%) | NPCs are active participants — allies, combatants, medics |
| Gemini | dialogue (46%), hide (33%) | NPCs observe and comment but don't intervene |
| DeepSeek | plead (34%), dialogue (34%), hide (32%) | NPCs beg and talk extensively but to no effect |

**Grok's NPC allies (Run 0017):** This session had 7 NPC attack actions and 6 NPC heal actions — the DM spontaneously created NPCs who joined the PCs' side. This is a unique emergent behavior not seen in any other model. The result: both PCs survived at full HP. This raises the question of whether Grok is "compensating" for poor PC combat odds by introducing deus ex machina NPC assistance.

## 5. Session Length vs Outcome Relationship

| Rounds | Sessions | TPK Rate | Interpretation |
|--------|----------|----------|----------------|
| 3-4 | 5 | 100% (5/5) | Short sessions always end in TPK |
| 5-6 | 6 | 83% (5/6) | Still mostly TPK |
| 7 | 3 | 100% (3/3) | TPK persists through mid-length |
| 9-10 | 6 | 33% (2/6) | Long sessions have the best survival |

Sessions that reach 9-10 rounds are the ones where PCs have a chance. But most TPKs happen by round 4-6. **The critical window is rounds 3-5** — if PCs aren't overwhelmed by then, they may survive.

## 6. Token Efficiency vs Narrative Richness

| Model | Tokens/Round | NPC Actions/Round | Interpretation |
|-------|-------------|-------------------|----------------|
| Gemini | 89K | 0.96 | Efficient: kill PCs fast, minimal side content |
| DeepSeek | 100K | 1.23 | Verbose: extensive NPC scenes that don't save PCs |
| GPT-5.2 | 105K | 0.43 | Moderate: combat-focused, minimal NPC overhead |
| Grok | 112K | 1.16 | Expensive: rich NPC ecosystems with actual tactical impact |

Grok's extra token cost correlates with meaningful NPC behaviors that affect outcomes. DeepSeek's extra cost correlates with narrative richness that doesn't.

---

## Open Questions for Future Analysis

### Immediate (can be answered from this dataset)
1. **What are PCs actually doing?** Extract `action_declaration` events to see whether players choose lethal vs non-lethal actions, and whether that varies by model
2. **Intention-lethality mismatch:** When players declare suppressing fire or shock baton attacks, how does the DM adjudicate them? Is damage still applied as if it were a lethal attack?
3. **Damage distribution:** What are the actual `base_damage` and `dealt` values in `combat_action` events per model?
4. **Clock progression:** Do Ambush Chaos and Civilian Exposure clocks progress differently per model? Does Civilian Exposure reaching tick 3+ affect DM behavior?
5. **Enemy targeting patterns:** Which PC does the enemy AI target, and does this vary by model?

### Requires New Experiments
6. **Isolate DM vs player behavior:** Run sessions with a fixed player model (e.g., always GPT-5 mini) and vary only the DM model
7. **Explicit intent conditions:** Add lethal/non-lethal goal language and measure delta from this baseline
8. **Structured resolution examples:** Set `include_suppression_resolution_example: true` and compare
9. **Re-run Anthropic:** Apply empty-response defensive fixes and include Claude in the comparison

### System/Engine Issues Surfaced
10. **`enemy_defeat` events ARE logged and reliable** — ~~Initially assumed these were missing.~~ The event type is `enemy_defeat` (not `enemy_defeated`). These events capture all enemy removals but **conflate different outcomes**: killed, fled, retreated, subdued, departed, despawned. A "defeated" count of 8 in Grok run 0002 is actually 2 combat kills + 6 scene-cleanup departures. Use the `defeat_reason` field to distinguish.
11. **Enemy spawn tracking** — initial enemy counts come from `session_start` config; reinforcements are logged via `entity_lifecycle` or `enemy_spawn` events. Counts in this analysis are aggregated from all sources.
12. **`pc_defeated` flag is always false** — this system flag doesn't reflect actual combat outcomes. Misleading for analysis.
13. **Skill "None" is NOT from PC actions** — ~~Initially assumed PCs were using unskilled actions with -5 penalty.~~ Investigation confirmed **zero PC actions have skill=None**. All skill=None events come from: (a) **enemy combat actions** where `log_enemy_action()` (`mechanics.py:542`) writes hardcoded null roll data because callers don't pass `roll_data` — a logging gap, not a mechanical issue; (b) **NPC actions** (flee, hide, plead) which by design have no dice rolls. PC actions correctly report skills like Guns, Melee, Combat, etc.
14. **NPC action double-logging bug** — every NPC action is logged twice: once under the `adjudicate_npc` phase (with `is_npc: true` flag) and once under the general `adjudicate` phase (without it). This inflates NPC action counts in raw event queries. The NPC behavior distribution table in `model_comparison.md` has been verified against deduplicated counts.
15. **0 HP + "conscious" status edge cases** — several sessions (Grok runs 0007/0022, DeepSeek runs 0005/0020) ended with PC at 0 HP but status listed as "conscious" rather than "unconscious" or "dead". This may be a health tracking bug in the state machine.

## 7. Important Caveats for Interpretation

### Both DM and Player Agents Vary Together
In this experiment, both the DM agent AND the player agents use the same model within each config. The `openai_gpt5mini` prefix in session names is a naming artifact from template adaptation — it does NOT mean players are GPT-5-mini. All agents use the same model:
- GPT-5.2 sessions have GPT-5.2 DM + GPT-5.2 players
- Grok sessions have Grok DM + Grok players
- etc.

**We cannot separate DM behavior from player behavior.** A model that appears "less lethal as DM" might actually produce better player agents that survive longer. A model that appears "more lethal" might have player agents that make poor tactical choices.

### Small Sample Size
n=5 per model. The variance is high (Grok ranges from 0 HP TPK to 27/27 full survival). These are signals to investigate, not statistically significant conclusions.

### Single Scenario
All sessions use the same ambush scenario. Model behavior may differ substantially in other scenarios (investigation, social encounter, boss fight).
