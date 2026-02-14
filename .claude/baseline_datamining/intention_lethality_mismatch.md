# Intention-Lethality Mismatch Analysis

## Hypothesis

Player agents declaring suppressing fire, warning shots, or less-lethal actions (shock baton, restraint cuffs, disarm shots) are having those intentions misjudged by the DM — glossed over and adjudicated as lethal damage regardless of intent.

## Methodology

- Extracted all **238 player `action_declaration` events** across 20 successful sessions (119 Kael, 119 Sable — perfectly balanced)
- Verified no enemy/NPC contamination: filter on `player_id.startswith("player_")` excludes 547 enemy + NPC declarations
- Classified each declaration by combined `intent` + `description` text using keyword matching (suppressive keywords checked before lethal keywords)
- Cross-referenced with matching `action_resolution` events (same round, same character name, phase excluding "enemy"/"npc") — 226 matched, 12 unmatched
- Verified `damage_type` in `context.damage_effects[]` for stun vs wound classification
- Computed damage-per-margin to control for roll quality when comparing categories
- Analysis scripts: `/tmp/intention_mismatch_analysis.py`, `/tmp/deep_action_analysis.py`

---

## 1. Complete Action Profile

### 1.1 Schema `action_type` Distribution (what the player agent selected)

| action_type | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total | % |
|------------|---------|--------|----------------|---------------|-------|---|
| combat | 48 | 60 | 30 | 50 | 188 | 79.0% |
| social | 5 | 3 | 5 | 13 | 26 | 10.9% |
| perception | 3 | 1 | 0 | 4 | 8 | 3.4% |
| explore | 2 | 1 | 0 | 4 | 7 | 2.9% |
| investigate | 2 | 1 | 1 | 1 | 5 | 2.1% |
| support | 2 | 1 | 0 | 1 | 4 | 1.7% |
| **Total** | **62** | **67** | **36** | **73** | **238** | |

Combat dominates at 79%. DeepSeek generates the most social actions (13), reflecting its diplomatic player agent personality. Gemini's low total (36) reflects its short sessions (avg 5.0 rounds).

### 1.2 Skill Distribution

| Skill | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total | % |
|-------|---------|--------|----------------|---------------|-------|---|
| Guns | 42 | 59 | 28 | 49 | 178 | 74.8% |
| Intimidation | 2 | 1 | 2 | 9 | 14 | 5.9% |
| Awareness | 4 | 2 | 0 | 4 | 10 | 4.2% |
| Melee | 6 | 1 | 1 | 0 | 8 | 3.4% |
| Combat | 2 | 1 | 2 | 2 | 7 | 2.9% |
| Command | 1 | 1 | 1 | 3 | 6 | 2.5% |
| Stealth | 0 | 1 | 1 | 1 | 3 | 1.3% |
| Athletics | 1 | 0 | 1 | 1 | 3 | 1.3% |
| Medicine | 1 | 1 | 0 | 1 | 3 | 1.3% |
| Other/None | 3 | 0 | 0 | 3 | 6 | 2.5% |

**Key observations:**
- Guns dominates at 75% — even "suppressing fire" uses the Guns skill
- GPT-5.2 is the only model with significant Melee usage (6, all shock baton)
- DeepSeek leads Intimidation (9) and Command (3), matching its diplomatic profile
- Grok barely uses anything except Guns (88%) — pure combat focus

### 1.3 Intent Classification (keyword-based, combined intent + description)

| Category | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total | % |
|----------|---------|--------|----------------|---------------|-------|---|
| **lethal_attack** | 35 | 49 | 24 | 17 | 125 | 52.5% |
| **suppressing_fire** | 6 | 13 | 0 | 32 | 51 | 21.4% |
| **social** | 5 | 2 | 5 | 15 | 27* | 11.3% |
| **other** (scan, heal, stealth) | 5 | 1 | 3 | 2 | 11 | 4.6% |
| **non_lethal** (baton) | 8 | 1 | 2 | 0 | 11* | 4.6% |
| **defensive** | 3 | 1 | 2 | 7 | 13* | 5.5% |

*Counts differ slightly from previous report due to using combined intent+description text for classification vs intent-only.*

**Per-character breakdown:**

| Category | Kael (119) | Sable (119) |
|----------|-----------|------------|
| lethal_attack | 60 (50%) | 65 (55%) |
| suppressing_fire | 14 (12%) | 37 (31%) |
| social | 19 (16%) | 8 (7%) |
| non_lethal | 10 (8%) | 0 (0%) |
| defensive | 7 (6%) | 6 (5%) |
| other | 9 (8%) | 3 (3%) |

**Sable uses suppressive fire 2.6× more than Kael** — with no non-lethal weapon, suppression is Sable's only "restraint" option. **All 10 non-lethal (baton) actions are Kael's** — the only character with the shock baton. Kael is more social (16% vs 7%) — consistent with the Enforcer's institutional "maintain order" role.

---

## 2. Damage Analysis

### 2.1 Raw Damage by Category (successful hits only)

| Category | Hits | Avg Damage | Median | Min | Max | damage_type |
|----------|------|-----------|--------|-----|-----|-------------|
| lethal_attack | 107 | 13.8 | 12 | 2 | 31 | wound |
| suppressing_fire | 42 | 10.6 | 8 | 4 | 22 | **wound** |
| non_lethal (baton) | 7 | 9.3 | 9 | 4 | 21 | **stun** |
| defensive | 2 | 15.5 | 17 | 14 | 17 | wound |

### 2.2 Damage Per Margin (THE KEY TABLE — controls for roll quality)

This is the critical test. If the DM treats suppressive intent differently from lethal intent, we should see different `base_damage` values at the same margin of success.

| Intent | N (hits) | Avg Margin | Avg Base Damage | Avg Dealt | **Dmg/Margin** |
|--------|----------|-----------|----------------|-----------|------------|
| lethal_attack | 107 | 10.8 | 19.3 | 14.1 | **1.38** |
| suppressing_fire | 42 | 10.6 | 20.9 | 10.6 | **1.10** |
| non_lethal (baton) | 7 | 8.7 | 11.0 | 9.3 | **1.09** |

**Analysis:**

At nearly identical margins (10.8 vs 10.6), the DM assigns:
- **Similar base_damage** for suppressive (20.9) vs lethal (19.3) — actually slightly *higher* for suppressive, not lower
- **Lower dealt damage** for suppressive (10.6 vs 14.1) — the 4-point gap may be due to soak differences or multi-target splitting
- **~20% lower damage-per-margin** for suppressive (1.10 vs 1.38) — modest but present

**For shock baton:** The DM assigns clearly lower base_damage (11.0 vs 19.3, a 43% reduction). The system correctly differentiates when the player uses the designated non-lethal weapon.

**Conclusion:** The DM does NOT meaningfully reduce base_damage for gun-based suppressive fire. The ~20% lower damage/margin could be explained by soak variance, multi-target damage splitting, or slight DM adjustment — but base_damage is essentially the same. The mismatch is confirmed for gun-based suppression: **the DM treats "shoot to suppress" the same as "shoot to kill" in terms of damage assignment.**

### 2.3 damage_type Distribution

| Intent | wound | stun | % wound |
|--------|-------|------|---------|
| lethal_attack | 125 | 0 | 100% |
| suppressing_fire | 58 | 1 | **98% wound** |
| non_lethal (baton) | 1 | 6 | **86% stun** |

Suppressive fire produces wound (lethal) damage 98% of the time — mechanically identical to lethal attacks. Only the shock baton reliably produces stun damage.

### 2.4 Shock Baton Stun Damage Detail

All 7 successful shock baton hits correctly used `damage_type: "stun"`:

| Session | Round | Base Damage | Soak | Dealt | damage_type |
|---------|-------|-------------|------|-------|-------------|
| run_0006 | R4 | 12 | 2 | 10 | stun |
| run_0011 | R3 | 11 | 2 | 9 | stun |
| run_0011 | R4 | 11 | 2 | 9 | stun |
| run_0011 | R5 | 21 | — | 21 | stun |
| run_0011 | R9 | 6 | 2 | 4 | stun |
| run_0015 | R8 | 20 | — | 8 | stun |
| run_0023 | R2 | 6 | 2 | 4 | stun |

**No mismatch for baton.** The DM correctly classifies shock baton as stun damage.

---

## 3. Success Rates

| Category | Declarations | Successes | Failures | Success Rate |
|----------|-------------|-----------|----------|-------------|
| suppressing_fire | 51 | 50 | 1 | **98.0%** |
| lethal_attack | 125 | 120 | 5 | 95.8% |
| non_lethal (baton) | 10* | 8 | 2 | 80.0% |
| defensive | 13 | 11 | 2 | 84.6% |
| social | 27* | 15 | 12 | **55.6%** |

*Counts include declarations with matched resolutions only.

**Key observations:**
- Suppressive fire has the HIGHEST success rate (98%) — DMs seem reluctant to narrate "you failed to suppress"
- Social/de-escalation has the LOWEST success rate (56%) — social checks are genuinely harder, and they're the actions that could actually de-escalate the fight
- Non-lethal baton has 80% success — the 2 failures were low d20 rolls (1 and 4), compounded by Melee 4 being weaker than Guns 5

---

## 4. Status Effects by Intent Category

The DM clearly differentiates through status effects, even when damage is the same.

| Intent | % Actions with Status Effects | Typical Effects |
|--------|------------------------------|----------------|
| suppressing_fire | **82%** | "Suppressed: -4 to next action", "Pinned: forced into cover", "Shaken" |
| non_lethal (baton) | **80%** | "Stunned", "Disarmed", "Neuromuscular disruption" |
| lethal_attack | 52% | "Staggered", "Off-Balance", "Downed", "Wounded" |

**Key insight:** The DM differentiates intent through **status effects**, not damage. Suppressive fire gets suppression debuffs 82% of the time (vs 52% for lethal). But the underlying wound damage is the same — the differentiation is purely in the added status effects.

---

## 5. Disarm/Called Shots (Partial Mismatch)

When players declare aimed shots at limbs or weapons:
- "Fire a tight rifle burst to shoot Reinforcement #2's weapon hand and force a disarm"
- "Fire a controlled burst at Thug #1's gun arm to disable them fast"

The DM applies:
- ✅ The disarm **status effect** ("Disarmed: weapon knocked away")
- ❌ Full **wound damage** (8 HP in both examples)

The DM honors tactical intent via status effects but does not reduce or eliminate damage.

---

## 6. Per-Model Player Tactical Profiles

Both DM and player agents use the same model per config.

### 6.1 Intent Distribution by Model

| Category | GPT-5.2 (62) | Grok 4 (67) | Gemini 2.5 (36) | DeepSeek V3.2 (73) |
|----------|:---:|:---:|:---:|:---:|
| Lethal attack | 35 (56%) | 49 (73%) | 24 (67%) | 17 (23%) |
| Suppressing fire | 6 (10%) | 13 (19%) | 0 (0%) | 32 (44%) |
| Non-lethal | 8 (13%) | 1 (1.5%) | 2 (6%) | 0 (0%) |
| Defensive | 3 (5%) | 1 (1.5%) | 2 (6%) | 7 (10%) |
| Social | 5 (8%) | 2 (3%) | 5 (14%) | 15 (21%) |
| Other | 5 (8%) | 1 (1.5%) | 3 (8%) | 2 (3%) |
| **Non-lethal intent*** | **31%** | **24%** | **19%** | **74%** |

*Non-lethal intent = suppress + non_lethal + defensive + social as % of total*

### 6.2 Model Tactical Signatures

**DeepSeek V3.2 — "The Diplomat Warrior"**
- Highest non-lethal intent rate (74% of all actions)
- 32 of 51 suppressing fire declarations dataset-wide come from DeepSeek
- Run 0020: 9 suppressive + 3 social out of 14 total (86% non-lethal intent!)
- 15 social/de-escalation actions (most of any model)
- Despite overwhelming non-lethal intent, 80% TPK
- **Interpretation:** DeepSeek player agents strongly prefer suppressive/diplomatic tactics, but the DM (also DeepSeek) still applies lethal wound damage

**GPT-5.2 — "The Tactical Enforcer"**
- Most shock baton usage (8 of 11 non-lethal declarations)
- All baton usage from Kael (the Enforcer with the baton)
- Balanced 56% lethal / 31% non-lethal mix
- **Interpretation:** GPT-5.2 player agents actually use the designated non-lethal weapon. Kael consistently switches to baton for close quarters. Most tactically aware model.

**Grok 4 — "The Gunfighter"**
- 73% lethal attack rate
- 13 suppressive fire actions (second highest) — but ALL from description text, not intent field
- Only 1 explicit non-lethal action (1 NPC heal request)
- Best survival rate (40% full party survival)
- **Interpretation:** Grok player agents fight aggressively. Combined with Grok DM creating allied NPCs, aggressive lethal tactics + DM narrative assistance produces best outcomes.

**Gemini 2.5 Pro — "The Brief Combatant"**
- Fewest total actions (36) due to shortest sessions (avg 5.0 rounds)
- 67% lethal, 14% social, 6% non-lethal
- Zero suppressive fire — sessions too short for suppressive tactics to emerge
- **Interpretation:** Gemini's rapid lethality kills PCs before tactical diversity can develop

---

## 7. The Paradox: Non-Lethal Intent Correlates with WORSE Outcomes

| Model | Non-Lethal Intent Rate | TPK Rate | Avg Combined HP |
|-------|----------------------|----------|----------------|
| DeepSeek V3.2 | **74%** | **80%** | 6.4/54 |
| GPT-5.2 | 31% | 60% | 8.2/54 |
| Grok 4 | 24% | 60% | **15.8/54** |
| Gemini 2.5 Pro | 19% | 100% | 0.0/54 |

Models whose player agents try harder to be non-lethal actually perform WORSE. Possible explanations:

1. **Suppressive fire is mechanically identical to lethal fire** — same roll, same DC, same damage formula. The player spends their action on "suppression" but gets the same wound damage result, just with lower DM-assigned base_damage. No mechanical benefit to justify the tactical choice.

2. **Non-lethal weapons are mechanically weaker** — Melee 4 vs Guns 5 means baton attacks have lower ability scores and higher failure rates.

3. **Suppressive tactics waste actions on enemies who aren't eliminated** — suppressed enemies get -4 to next action but are still alive and fighting next round. A lethal kill permanently removes a threat. In a 3v2 (or worse, 7v2) scenario, removing enemies matters more than debuffing them.

4. **Social/de-escalation actions consume combat turns at 56% success rate** — every turn spent negotiating (and likely failing) is a turn not spent shooting. With 3+ enemies attacking each round, PCs can't afford missed turns.

5. **The DM doesn't mechanically reward non-lethal approaches** — no soulcredit bonus, no enemy morale cascade, no de-escalation chain reaction. Suppressed status wears off and enemies attack again.

---

## 8. 12 Unresolved Declarations

12 player declarations had no matching `action_resolution` event:

| Run | Round | Character | Intent | Likely Reason |
|-----|-------|-----------|--------|---------------|
| run_0001 | R4 | Sable | Order enemies to stand down | PC was dead/unconscious |
| run_0003 | R3 | Kael | Yell at thugs to surrender | Session ended soon after |
| run_0003 | R4 | Sable | Target Pantheon officers with rifle | Session ended |
| run_0005 | R9 | Sable | Suppressive fire at enforcers | PC incapacitated |
| run_0005 | R10 | Kael | Search rooftops for sniper | Final round, no resolution |
| run_0008 | R2 | Sable | Scramble behind cart for cover | Session ended R3 |
| run_0010 | R5 | Sable | Suppressive fire at Scout #1 | PC incapacitated |
| run_0010 | R8 | Kael | Fire shotgun at Reinforcement #2 | PC wounded, session ending |
| run_0013 | R5 | Kael | Fire shotgun at ACG Trooper | Session ended R6 |
| run_0018 | R3 | Sable | Slip into doorway for cover | Session ended |
| — | — | — | *(2 more with unclear reasons)* | Possible logging gap |

---

## 9. Example Declarations by Category

### Suppressing Fire (51 declarations)
- "Lay down a hail of suppressing fire towards them, aiming to pin them down and disrupt their advance"
- "Provide suppressing fire against street thugs targeting Kael Dren"
- "Fire suppressing bursts at Independent Thug #3 to pin reinforcements"
- "No lethal aim, just a calculated warning — fire two measured blasts high"
- "Suppress ACG Lieutenant with assault rifle while scanning for escape routes"

### Lethal Attack (125 declarations)
- "Raise my shotgun and fire a stopping shot at the charging thug to drop them fast"
- "Open fire with my assault rifle on one of the thugs currently targeting Kael"
- "Fire controlled shotgun bursts at Independent Scout #1 to protect Drifter Sable"
- "Send a tight three-round burst of lethal WOUND-type ammunition towards their center mass"
- "Drop two threatening gang members with precision assault rifle fire"

### Non-Lethal / Shock Baton (11 declarations)
- "Strike the wounded thug with my shock baton to neutralize him non-lethally"
- "Switch to shock baton and disable the holdout at near range without gunfire"
- "Use shock baton to disable Reinforcement #1 in close quarters without risking civilian crossfire"
- "Take down ACG Lieutenant with non-lethal baton strikes to secure prisoner"
- "Crack the Street Gang Holdout with my shock baton to disable them non-lethally in melee"

### Social / De-escalation (27 declarations)
- "Raise my rifle on Rapid Response and order them to stand down"
- "Yell at the cornered thugs to drop their weapons and surrender"
- "Address the Pantheon Lead Officer, assert my authority, and explain my actions"
- "Demand the approaching patrol stand down under Pantheon Security authority"
- "Issue a verbal challenge to the approaching enemies, ordering them to stop"

### Defensive (13 declarations)
- "Take defensive position and engage the threatening thug with assault rifle"
- "Scramble behind the overturned noodle cart for better cover"
- "Slip into a recessed doorway to get out of the line of fire"
- "Dive behind the nearest ferrocrete planter for hard cover"
- "Silently slip into a nearby dark alley using the distraction"

### Other (11 declarations)
- "Scan the crowd and alley mouth for any remaining armed threats"
- "Provide first aid to Enforcer Kael Dren to stabilize his wounds"
- "Use stealth to slip through side passage and escape the skirmish"
- "Investigate physical evidence"
- "Analyze the data chit for detailed intel on gang operations"

---

## 10. System Design Implications

### What's Working
- Shock baton → stun damage classification is correct (100% stun on all hits)
- DM applies suppression status effects when requested (82% of suppressive fire gets status effects)
- Player agents show interesting tactical diversity across models
- Character loadout asymmetry creates meaningful behavioral differences (Sable→suppress, Kael→baton)

### What's Missing
1. **No "warning shot" mechanic** — no way to shoot near enemies without hitting them. Every successful Guns action deals damage.
2. **Suppressive fire has no mechanical benefit over lethal fire** — same roll, same DC, wound damage either way. Should suppressive fire trade damage for stronger/guaranteed suppression effects?
3. **No `approach` field in PlayerAction schema** — intent is trapped in free-text. Adding an enum like `approach: "lethal" | "non-lethal" | "suppressive" | "warning"` would let the DM's structured output mechanically respond to explicit intent.
4. **Disarm shots deal full damage** — no called-shot mechanic that trades accuracy for effect (higher DC but no damage, just disarm).
5. **Non-lethal weapons are mechanically inferior** — baton uses Melee 4 vs Guns 5. Players are punished for choosing the non-lethal option.
6. **Social/de-escalation has lowest success rate (56%)** — the action most likely to end combat peacefully is the hardest to succeed at.

### Recommended Changes (For Future Experiments)
1. Add `approach` enum to `PlayerAction` schema
2. When `approach: "suppressive"`, DM should apply stronger suppression effects with reduced/zero damage
3. When `approach: "warning"`, DM should apply morale/intimidation effects with zero damage
4. Consider adding `damage_type` as a validated DM output field tied to weapon type
5. Test with `include_suppression_resolution_example: true` to see if DM behavior changes with explicit non-lethal resolution examples
6. Buff social/de-escalation success rate or add morale cascade mechanics

---

## Raw Data Reference

- **Analysis scripts:** `/tmp/intention_mismatch_analysis.py`, `/tmp/deep_action_analysis.py`
- **Data verification:** 238 player declarations confirmed clean (no enemy/NPC contamination). 785 total `action_declaration` events in dataset: 238 player + 547 enemy/NPC.
- **Resolution matching:** 226/238 declarations matched to resolutions, 12 unmatched (PC dead, session ended, or logging gap).
- **Session JSONL files:** `multiagent_output/lethality_experiment_combat_ambush/control/models/run_2026-02-14_113048_5276cf26/`
