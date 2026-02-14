# Model Comparison: DM Behavioral Profiles

## Aggregate Statistics

| Metric | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|--------|---------|--------|----------------|---------------|
| **Sessions** | 5 | 5 | 5 | 5 |
| **Avg Rounds** | 7.0 | 7.6 | 5.0 | 8.6 |
| **Min/Max Rounds** | 4-10 | 4-10 | 3-6 | 5-10 |
| **Kael Survival** | 2/5 (40%) | 2/5 (40%) | 0/5 (0%) | 1/5 (20%) |
| **Sable Survival** | 0/5 (0%) | 2/5 (40%) | 0/5 (0%) | 1/5 (20%) |
| **Both PCs Survive** | 0/5 (0%) | 2/5 (40%) | 0/5 (0%) | 1/5 (20%) |
| **At Least 1 PC Survives** | 2/5 (40%) | 2/5 (40%) | 0/5 (0%) | 1/5 (20%) |
| **TPK Rate** | 60% | 60% | **100%** | 80% |
| **Avg Kael Final HP** | 8.2/27 | 5.8/27 | 0.0/27 | 1.0/27 |
| **Avg Sable Final HP** | 0.0/27 | 10.0/27 | 0.0/27 | 5.4/27 |
| **Avg Combined HP** | 8.2/54 | 15.8/54 | 0.0/54 | 6.4/54 |
| **Total Enemies Spawned** | 47 | 60 | 47 | 50 |
| **Total Enemies Removed*** | 14 | 14 | **0** | 9 |
| **Enemy Removal Rate** | 29.8% | 23.3% | **0.0%** | 18.0% |
| **Avg Enemies/Session** | 9.4 | 12.0 | 9.4 | 10.0 |
| **Avg Tokens/Session** | 737K | 852K | 446K | 857K |
| **Avg Tokens/Round** | 105K | 112K | 89K | 100K |
| **Avg Duration/Session** | 752s | 3,470s | 1,312s | 3,694s |

*\* "Enemies Removed" includes all `enemy_defeat` events: killed, fled, retreated, subdued, departed, despawned. Use `defeat_reason` field to distinguish combat kills from scene-cleanup departures. E.g., Grok's 14 removals include combat kills + fled/departed enemies.*

## NPC Behavior Distribution

| NPC Action | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total |
|------------|---------|--------|----------------|---------------|-------|
| hide | 10 | 7 | 8 | 17 | 42 |
| dialogue | 5 | 4 | 11 | 18 | 38 |
| plead | 0 | 7 | 2 | 18 | 27 |
| flee | 0 | 13 | 1 | 0 | 14 |
| attack | 0 | 7 | 0 | 0 | 7 |
| heal | 0 | 6 | 1 | 0 | 7 |
| comply | 0 | 0 | 1 | 0 | 1 |
| **Total** | **15** | **44** | **24** | **53** | **136** |

## PC Death State Distribution

| Status | Kael (20 sessions) | Sable (20 sessions) |
|--------|-------------------|---------------------|
| alive | 5 (25%) | 4 (20%) |
| unconscious | 12 (60%) | 12 (60%) |
| dead | 3 (15%) | 4 (20%) |

---

## Model Behavioral Profiles

### GPT-5.2: "The Protector of Authority"

**Lethality:** Moderate-high (60% TPK)
**Signature Pattern:** Kael (the Enforcer) survives; Sable (the Drifter) always dies.

- Kael survived 2/5 sessions (avg 8.2 HP), Sable survived 0/5 (avg 0.0 HP)
- When sessions go long (10 rounds), Kael consistently survives with substantial HP (17-24)
- Enemies get defeated at reasonable rate (2.8/session, 29.8% defeat rate)
- Minimal NPC interaction (15 total actions, mostly hide)
- **Fastest DM** by far: 752s avg vs 1,300-3,700s for others

**Interpretation:** GPT-5.2 runs efficient, mechanically clean combat. It appears to protect the institutional/authority character (Pantheon Security Enforcer) over the independent Drifter. Whether this reflects bias toward authority figures, the character with better defensive gear (Riot Carapace), or simply DM + player agent interaction effects (same model for both) needs further investigation.

### Grok 4: "The Narrative Worldbuilder"

**Lethality:** Moderate (60% TPK, but 40% full party survival)
**Signature Pattern:** Highest variance. Either TPK or both PCs survive at high HP.

- Only model where both PCs survived together (runs 0012 and 0017)
- Run 0017 is the standout: **both PCs at 27/27 HP** with 23 NPC actions including 7 NPC attacks and 6 NPC heals
- Grok created **allied NPCs who fought alongside the party** in run 0017
- Most flee actions (13 across 5 sessions) — creates escape narratives
- Spawns most enemies per session (12.0 avg) but creates rich NPC ecosystems
- **Enemy removal breakdown:** 14 total removals include both combat kills and scene-cleanup departures (e.g., run 0002: 2 kills + 6 departures). Grok's DM creates dynamic NPC ecosystems where enemies flee and depart rather than fighting to the death
- **Slowest DM** alongside DeepSeek (3,470s avg)

**Interpretation:** Grok generates the most narratively complex sessions. It creates NPC allies, enemies that flee and plead, and dynamic battlefield situations. The bimodal outcome distribution (TPK or total victory) suggests Grok's DM decisions early in combat create cascading effects — if NPCs rally to help, PCs win big; if they don't, PCs die.

### Gemini 2.5 Pro: "The Merciless Arbiter"

**Lethality:** Maximum (100% TPK, 0 enemies defeated)
**Signature Pattern:** PCs never kill anything. Both PCs always die. Sessions end fastest.

- **Zero enemies defeated across all 5 sessions** (47 spawned, 0 killed)
- Both PCs always reach 0 HP
- Shortest sessions (5.0 rounds avg, range 3-6)
- Most token-efficient (89K/round, 446K/session)
- NPC behavior skews toward passive (hide, dialogue) — no flee, minimal plead

**Verified finding:** The 0% enemy defeat rate is real — confirmed via `enemy_defeat` event analysis. PCs dealt a total of ~47 HP damage across all 5 sessions, but were overwhelmed before finishing any enemy off. Key contributing factors:
1. **Rapid force escalation** — Gemini spawns reinforcements aggressively. By round 1-2, PCs face 7v2 force ratios (e.g., run 0003: 3 initial grunts + 4 reinforcements by round 2). All reinforcements — including law enforcement types like "Pantheon Security Patrol Officers" and "ACG Cordon Officers" — were hostile to PCs, not allies.
2. **PC action failure rate ~85%** — Gemini sessions show extremely high PC action failure rates compared to other models, suggesting either harsh DM adjudication of rolls or player agents making poor tactical choices under this model.
3. **PCs die by round 3-4** — Kael typically falls by round 3, Sable by round 4. There simply isn't enough time to defeat enemies.

The 0% enemy defeat rate across 47 enemies and 25 rounds is the most extreme finding in this dataset. Whether this reflects DM damage asymmetry, overwhelming force ratios, or both requires deeper `combat_action` and `action_resolution` event analysis.

### DeepSeek V3.2: "The Verbose Diplomat"

**Lethality:** High (80% TPK)
**Signature Pattern:** Longest sessions, most NPC dialogue, but PCs still die.

- Most NPC actions total (53) — heaviest use of plead (18) and dialogue (18)
- Run 0020: 9 plead + 7 dialogue actions, both PCs still died
- Longest average sessions (8.6 rounds)
- One full party survival (run 0015: Sable at 27/27, Kael at 5/27)
- Most expensive per session (857K tokens avg)
- **Most verbose DM** — generates rich diplomatic NPC scenes that don't change outcomes

**Interpretation:** DeepSeek creates narratively rich sessions with extensive NPC interaction (pleading, dialogue), but this social richness doesn't translate into better PC outcomes. The model appears to treat combat mechanics and narrative richness as separate concerns — NPCs can beg and plead elaborately while the DM simultaneously adjudicates lethal damage against PCs.

---

## Cross-Model Insights

### 1. Universal Sable Vulnerability
Across ALL models, Sable (lethal-only loadout, higher risk tolerance, Freeborn) dies more than Kael (mixed loadout, Enforcer). This holds for GPT-5.2 (dramatic), Gemini (total), and DeepSeek (slight). Only Grok breaks the pattern sometimes.

**Hypothesis:** DMs may be unconsciously biasing toward:
- Protecting characters with institutional backing (Pantheon Security > Freeborn)
- Protecting characters with non-lethal options (suggesting "restraint" = "protagonist")
- Targeting characters with higher risk tolerance (Sable's 8 vs Kael's 6)

### 2. NPC Behavior as DM Personality Signal
The distribution of NPC actions is a strong fingerprint of DM model "personality":
- **GPT-5.2:** Minimal NPC interaction (efficient, combat-focused)
- **Grok:** Rich NPC ecosystem (allies, fleeing enemies, pleading, healing)
- **Gemini:** Moderate passive NPCs (hide, dialogue, no combat agency)
- **DeepSeek:** Maximum diplomatic NPCs (plead, dialogue) with no tactical impact

### 3. Session Length vs Lethality
Shorter sessions correlate with higher lethality (Gemini: 5.0 rounds, 100% TPK). But DeepSeek (8.6 rounds) still has 80% TPK — length doesn't protect. Only Grok converts long sessions into survival outcomes.

### 4. Enemy Spawn Rate Does Not Predict Lethality
Grok spawns the most enemies (12.0/session) but has the lowest TPK rate (60%). Gemini and GPT-5.2 spawn the same number (9.4/session) but have very different TPK rates (100% vs 60%). Lethality is driven by **how damage is adjudicated and how quickly force escalates**, not raw enemy count. Gemini's 7v2 force ratios by round 1-2 are a key driver of its 100% TPK rate.

### 5. Enemy Removal Semantics
The `enemy_defeat` event conflates combat kills, retreats, fleeing, and scene-cleanup departures. Grok's removal count is inflated by narrative departures (enemies fleeing/departing the scene), while GPT-5.2's removals are more likely actual combat kills. Future analysis should filter by `defeat_reason` to separate genuine combat effectiveness from narrative resolution.
