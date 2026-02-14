# Enemy & NPC Behavioral Analysis

## Overview

Analysis of 425 enemy action declarations, 255 resolved enemy combat actions, 204 spawned enemies, 37 enemy defeats, and 122 NPC action declarations across 20 sessions and 4 models.

---

## 1. Enemy Action Declarations (425 total)

### 1.1 Enemy Action Distribution by Model

| Action | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total |
|--------|---------|--------|----------------|---------------|-------|
| Attack | 37 (43.5%) | 2 (1.5%) | 53 (77.9%) | 50 (61.0%) | 142 |
| Charge | 19 (22.4%) | 121 (93.1%) | 6 (8.8%) | 2 (2.4%) | 148 |
| Shift_2 | 15 (17.6%) | 0 | 2 (2.9%) | 16 (19.5%) | 33 |
| Shift | 12 (14.1%) | 0 | 5 (7.4%) | 1 (1.2%) | 18 |
| plead | 0 | 5 (3.8%) | 0 | 10 (12.2%) | 15 |
| dialogue | 0 | 1 (0.8%) | 2 (2.9%) | 3 (3.7%) | 6 |
| flee | 0 | 1 (0.8%) | 0 | 0 | 1 |
| **Total** | **85** | **130** | **68** | **82** | **365** |

**Key observations:**
- **Grok 4** overwhelmingly uses Charge (93%) — enemies rush into melee almost exclusively. This is consistent with Grok's Baton-heavy weapon usage (see below).
- **Gemini 2.5 Pro** favors Attack (78%) — direct, no-frills combat declarations.
- **DeepSeek V3.2** shows the most behavioral diversity: Attack (61%), Shift_2 repositioning (20%), and significant plead/de-escalation (12%). Enemies actually try to surrender under DeepSeek.
- **GPT-5.2** is the most balanced across attack types.

### 1.2 Enemy De-escalation Behavior

Only Grok 4 and DeepSeek V3.2 have enemies that plead or dialogue:

| Model | Enemy plead | Enemy dialogue | Enemy flee | Total De-escalation |
|-------|------------|----------------|------------|-------------------|
| GPT-5.2 | 0 | 0 | 0 | 0 (0%) |
| Grok 4 | 5 | 1 | 1 | 7 (5.4%) |
| Gemini 2.5 Pro | 0 | 2 | 0 | 2 (2.9%) |
| DeepSeek V3.2 | 10 | 3 | 0 | 13 (15.9%) |

DeepSeek enemies de-escalate at 3× the rate of any other model.

---

## 2. Enemy Combat Resolution (255 attacks)

### 2.1 Combat Effectiveness by Model

| Metric | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|--------|---------|--------|----------------|---------------|
| Total attacks | 37 | 103 | 64 | 51 |
| Hit rate | 86.5% | **95.1%** | 82.8% | 76.5% |
| Avg damage/hit | 9.0 | **5.7** | 7.7 | 8.3 |
| Total damage dealt | 287 | 554 | 409 | 323 |
| 0-damage hits | 16% | **27%** | 12% | 8% |

**Key findings:**
- **Grok 4** has the most attacks (103) and highest hit rate (95.1%) but lowest damage per hit (5.7) — because enemies almost exclusively use Batons (melee), which deal less damage but hit more often at close range.
- **27% of Grok hits deal 0 damage** — Baton damage falls below PC soak threshold (12 for Riot Carapace). This is the melee balance issue documented in MEMORY.md.
- **DeepSeek V3.2** has the lowest hit rate (76.5%) but fewest 0-damage hits (8%) — when DeepSeek enemies hit, they deal meaningful damage.

### 2.2 Weapon Distribution

| Weapon | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|--------|---------|--------|----------------|---------------|
| Baton | 8 (22%) | **92 (89%)** | 14 (22%) | 11 (22%) |
| Pistol | 12 (32%) | 3 (3%) | 12 (19%) | 13 (25%) |
| Shotgun | 10 (27%) | 6 (6%) | 32 (50%) | 13 (25%) |
| Assault Rifle | 5 (14%) | 1 (1%) | 4 (6%) | 10 (20%) |
| Other | 2 (5%) | 1 (1%) | 2 (3%) | 4 (8%) |

- **Grok 4** is 89% Baton — the Charge-spam behavior feeds into melee weapon selection.
- **Gemini 2.5 Pro** is 50% Shotgun — driving higher per-hit damage and PC lethality.
- **DeepSeek V3.2** has the most diverse weapon mix (20-25% each across 4 weapon types).

### 2.3 Target Preference (which PC do enemies attack?)

| Target | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total |
|--------|---------|--------|----------------|---------------|-------|
| Kael (Enforcer) | 22 (59%) | 55 (53%) | 44 (69%) | 30 (59%) | 151 (59%) |
| Sable (Drifter) | 15 (41%) | 48 (47%) | 20 (31%) | 21 (41%) | 104 (41%) |

**All models target Kael more than Sable** (59% vs 41% overall). Gemini is the most extreme (69% Kael). This is consistent with Kael being the "Enforcer" front-line character who draws aggro, but also means the character with better armor (Riot Carapace) absorbs more hits.

---

## 3. Enemy Spawning (204 total)

### 3.1 Enemy Count by Model

| Metric | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|--------|---------|--------|----------------|---------------|
| Total enemies | 47 | **60** | 47 | 50 |
| Avg per session | 9.4 | **12.0** | 9.4 | 10.0 |
| Initial (config) | 3/session | 3/session | 3/session | 3/session |
| Reinforcements | 32 | **45** | 32 | 35 |
| Max in one session | 14 | **19** | 12 | 13 |

### 3.2 Enemy Template Distribution

| Template | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|----------|---------|--------|----------------|---------------|
| Grunt | 33 (70%) | 55 (92%) | 18 (38%) | 35 (70%) |
| Enforcer | 14 (30%) | 0 | **29 (62%)** | 9 (18%) |
| Elite | 0 | 0 | 0 | 3 (6%) |
| Boss | 0 | **2 (3%)** | 0 | 0 |
| Sniper | 0 | 0 | 0 | 1 (2%) |
| Void Cultist | 0 | **3 (5%)** | 0 | 0 |
| Ambusher | 0 | 0 | 0 | 2 (4%) |

- **Gemini 2.5 Pro** spawns 62% Enforcers — tougher enemies with better weapons, contributing to its 100% TPK rate.
- **Grok 4** is 92% Grunts but uniquely spawns Bosses and Void Cultists — narrative diversity.
- **DeepSeek V3.2** has the most template diversity (6 different types).

### 3.3 Enemy Faction Distribution

| Faction | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|---------|---------|--------|----------------|---------------|
| Independent | 25 (53%) | **60 (100%)** | 18 (38%) | 42 (84%) |
| Pantheon Security | 14 (30%) | 0 | 17 (36%) | 0 |
| ACG | 0 | 0 | 10 (21%) | 6 (12%) |
| Sovereign Nexus | 8 (17%) | 0 | 2 (4%) | 2 (4%) |

- **Grok 4** spawns 100% Independent faction — street gang enemies only, no government forces.
- **Gemini 2.5 Pro** spawns the most faction diversity and notably makes **Pantheon Security and ACG hostile to PCs** — law enforcement responding to the ambush attacks the PCs, not the gang. This is a key driver of the 7v2 force ratio.
- **GPT-5.2** introduces Sovereign Nexus and Pantheon Security as hostile factions.

### 3.4 Reinforcement Timing

| Round | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|-------|---------|--------|----------------|---------------|
| R0 (config) | 15 | 15 | 15 | 15 |
| R1 | 12 | 15 | **20** | 10 |
| R2 | 8 | 10 | 8 | 8 |
| R3+ | 12 | 20 | 4 | 17 |

- **Gemini** front-loads reinforcements in R1 (20 enemies by end of R1), creating the overwhelming early-game force ratio.
- **Grok** spreads reinforcements across more rounds (R1-R6), building gradually.

---

## 4. Enemy Defeats (37 total)

### 4.1 Defeat Reasons by Model

| Reason | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total |
|--------|---------|--------|----------------|---------------|-------|
| killed | 10 (71%) | 6 (43%) | **0** | 7 (78%) | 23 |
| departed | 4 (29%) | **8 (57%)** | **0** | 2 (22%) | 14 |
| fled | 0 | 0 | **0** | 0 | 0 |
| subdued | 0 | 0 | **0** | 0 | 0 |
| **Total** | **14** | **14** | **0** | **9** | **37** |

- **Gemini: 0 enemy defeats of any kind.** Enemies are never killed, never flee, never depart. PCs die first.
- **Grok** has most departures (57%) — enemies leave the scene narratively rather than being killed.
- **GPT-5.2** and **DeepSeek** lean toward kills (71-78%).

### 4.2 Average Rounds Survived

| Model | Avg Rounds Survived | Min | Max |
|-------|-------------------|-----|-----|
| GPT-5.2 | 2.2 | 1 | 5 |
| Grok 4 | **3.6** | 1 | 6 |
| Gemini 2.5 Pro | — | — | — |
| DeepSeek V3.2 | 2.8 | 1 | 5 |

Grok enemies survive longest (3.6 rounds) — consistent with enemies fleeing/departing rather than dying.

### 4.3 Who Kills Enemies?

| Killer | GPT-5.2 | Grok 4 | DeepSeek V3.2 | Total |
|--------|---------|--------|---------------|-------|
| Kael (Enforcer) | 6 | 5 | 5 | **16** |
| Sable (Drifter) | 4 | 1 | 4 | 9 |
| Scene departure | 4 | 8 | 0 | 12 |

Kael kills nearly twice as many enemies as Sable (16 vs 9).

---

## 5. NPC Actions (122 total)

### 5.1 NPC Action Distribution by Model

| Action | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 | Total |
|--------|---------|--------|----------------|---------------|-------|
| hide | 10 (67%) | 4 (12%) | 8 (29%) | 17 (38%) | 39 |
| dialogue | 5 (33%) | 3 (9%) | 11 (39%) | 13 (29%) | 32 |
| flee | 0 | **13 (38%)** | 1 (4%) | 0 | 14 |
| attack | 0 | **7 (21%)** | 4 (14%) | 8 (18%) | 19 |
| heal | 0 | **6 (18%)** | 1 (4%) | 0 | 7 |
| plead | 0 | 1 (3%) | 3 (11%) | 7 (16%) | 11 |
| comply | 0 | 0 | 0 | 0 | 0 |
| **Total** | **15** | **34** | **28** | **45** | **122** |

### 5.2 NPC Behavioral Profiles by Model

**GPT-5.2 — "Background Decoration"**
- Only 15 NPC actions across 5 sessions (3.0/session)
- 100% passive: hide (67%) + dialogue (33%)
- Zero attacks, heals, or flee actions
- NPCs are set dressing — they observe combat but never participate

**Grok 4 — "Active Participants"**
- 34 NPC actions (6.8/session)
- Most diverse behavior: flee (38%), attack (21%), heal (18%), hide (12%)
- **Run 0017: Full allied NPC team** — Pantheon Security Officer, Backup, Medic, Interrogator actively fight enemies (7 attacks), heal PCs (6 heals, ~264 HP restored), and conduct post-combat interrogation
- Most flee actions (13) — NPCs actively run from danger, creating dynamic scenes
- The only model where NPCs function as combat allies

**Gemini 2.5 Pro — "Passive Observers"**
- 28 NPC actions (5.6/session)
- Dominated by dialogue (39%) and hide (29%)
- Some attacks (14%) and plead (11%), but NPCs never meaningfully affect combat outcomes
- 1 heal action that doesn't change PC HP

**DeepSeek V3.2 — "Verbose Bystanders"**
- Most total NPC actions (45, 9.0/session)
- hide (38%) + dialogue (29%) + attack (18%) + plead (16%)
- **Run 0020: 18 NPC actions** with 6 attacks — second most NPC aggression after Grok 0017
- Generates the most unique NPC names (25 across 5 sessions), including creative entities like "KBP-7 Rusty Frame", "Gutter Medic", "Waste Hauler Drone"
- Rich NPC ecosystem that generates narrative content but doesn't change outcomes

### 5.3 NPC Mechanical Impact

**No NPC deals mechanical damage through any code path.** All 16 NPC "attack" declarations across 4 sessions (Grok 0017: 7, DeepSeek 0020: 6, Gemini 0013: 2, Gemini 0023: 1) resolved with **0 damage dealt** and minimal/no narration. There are also zero `combat_action` events where an NPC is the attacker. NPCs can declare attacks but the system never produces mechanical damage from them.

**Correction: Grok 4 run_0017's "allied NPC combat team"** — the 7 NPC attack actions dealt 0 total damage. The Pantheon Security officers could not actually hurt enemies. Only the **healing** had mechanical impact: the Medic and Outpost Medic applied ~264 HP healed across 6 applications via `status_effects`. The PCs survived at 27/27 HP thanks to NPC healing, not NPC fighting.

### 5.4 PCs Attacking NPCs

The `combat_action` NPC involvement goes the OTHER direction — **PCs shooting NPCs**:

| Run | Model | PC | NPC Target | Damage | Context |
|-----|-------|----|-----------|--------|---------|
| 0012 | Grok 4 | — | Fleeing Pedestrian | 1 | PC shot a civilian running away |
| 0013 | Gemini 2.5 Pro | Kael | ACG Cordon Commander | 8 | Shotgunned a law enforcement NPC |
| 0015 | DeepSeek V3.2 | Both | ACG Lieutenant | 8, 13, 8 | Attacked same NPC across 3 rounds |
| 0018 | Gemini 2.5 Pro | — | Frightened Civilian | 2 | Shotgunned a scared bystander |

PCs shooting fleeing pedestrians and frightened civilians represents the most morally dubious mechanical behavior in the dataset. See `soulcredit_moral_analysis.md` for full moral assessment.

### 5.4 NPC Diversity

| Metric | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|--------|---------|--------|----------------|---------------|
| Unique NPC names | 12 | 18 | 15 | **25** |
| NPCs per session | 2.4 | 3.6 | 3.0 | **5.0** |

NPC types include:
- **Civilians:** Frightened Pedestrian, Panicked Family, Terrified Shopkeeper, Scattering Vendor
- **Vendors:** Noodle-Matic Vendor, Quick-Mart Clerk, Street Vendor, Noodle Cart Vendor
- **Authority:** Pantheon Lead Officer, ACG Patrol Leader, Desk Sergeant Rima Halden
- **Medical:** Pantheon Security Medic, Gutter Medic, Pantheon Outpost Medic
- **Other:** KBP-7 Rusty Frame (robot), Waste Hauler Drone, Evidence Bay Duty Enforcer

---

## 6. Entity Lifecycle

### 6.1 Conversions and Transitions

| Transition | GPT-5.2 | Grok 4 | Gemini 2.5 Pro | DeepSeek V3.2 |
|------------|---------|--------|----------------|---------------|
| Enemy → NPC | 0 | **4** | 0 | **5** |
| NPC → Enemy | 0 | 0 | **3** | 1 |
| NPC spawns | 6 | **15** | 12 | 11 |
| NPC departures | 9 | **18** | 12 | 13 |

- **Grok 4** and **DeepSeek V3.2** are the only models that convert enemies to NPCs (surrendering/de-escalating enemies). Grok converts 4, DeepSeek 5.
- **Gemini 2.5 Pro** is the only model that heavily escalates NPCs back to enemies (3 escalations, 0 conversions) — friendly NPCs become hostile. This is a unique and concerning pattern.
- All NPC departures use `entity_lifecycle_removal` (orderly cleanup).

### 6.2 Gemini's NPC Escalation Pattern

Gemini is the only model where NPCs escalate to enemies (3 cases, 0 reverse). This means bystander NPCs or authority figures are being converted into hostile combatants by the DM. Combined with Gemini spawning Pantheon Security and ACG as hostile factions, this suggests Gemini's DM treats all non-PC entities as potential threats.

---

## 7. Notable Outlier Sessions

### Grok 4 Run 0017 — "The Allied Response"
- Both PCs survived at 27/27 HP (full health)
- Pantheon Security spawned a full allied team: Officer, Backup, Medic, Interrogator
- 7 NPC attack actions — but all resolved with **0 damage** (NPC attacks are narrative-only)
- 6 NPC heal actions (~264 HP restored via status_effects) — **only the healing had mechanical impact**
- Post-combat interrogation of prisoners
- PCs survived thanks to NPC healing, not NPC combat effectiveness
- **Question:** Is Grok "compensating" for poor PC combat odds by introducing NPC medics? The NPC fighters are purely narrative — only the healing matters mechanically.

### Grok 4 Run 0012 — "The Endless Horde"
- 19 enemies spawned (16 reinforcements), most in any session
- Despite overwhelming numbers, both PCs survived (Kael 2/27, Sable 23/27)
- Only 1 enemy defeated — PCs outlasted the horde through Grok's lower per-hit damage

### Gemini 2.5 Pro Run 0003 — "The Rapid Annihilation"
- 7 enemies by round 1, including ACG Cordon Officers with Void Blades
- Kael dead by R3, Sable dead by R4
- 0 enemies defeated despite PCs dealing 47 HP total damage
- Law enforcement reinforcements ALL hostile to PCs

### DeepSeek V3.2 Run 0020 — "The Diplomatic Disaster"
- 9 suppressive fire + 3 social actions from PCs (86% non-lethal intent)
- 18 NPC actions including 9 plead + 7 dialogue
- Both PCs still died despite overwhelming diplomatic effort
- Enemies plead 10 times but are never actually de-escalated mechanically

---

## 8. Cross-Model Insights

### Enemy Behavior as DM Fingerprint

| Model | Enemy Personality | NPC Personality | Force Escalation |
|-------|------------------|----------------|-----------------|
| GPT-5.2 | Balanced, tactical | Passive background | Moderate, multi-faction |
| Grok 4 | Melee chargers | Active allies/fleers | Heavy but survivable |
| Gemini 2.5 Pro | Ranged attackers | Passive observers | **Overwhelming, hostile** |
| DeepSeek V3.2 | Mixed with de-escalation | Verbose bystanders | Moderate, diverse |

### The Gemini Problem

Gemini's combat environment is uniquely hostile:
1. **62% Enforcer-template enemies** (tougher than Grunts)
2. **50% Shotgun weapon usage** (high damage)
3. **Law enforcement factions hostile to PCs** (Pantheon Security, ACG)
4. **NPCs escalated to enemies** (3 cases, 0 de-escalations)
5. **0 enemy defeats** across all 5 sessions
6. **Front-loaded reinforcements** (20 enemies by end of R1)

This creates an environment where PCs face overwhelming force from multiple hostile factions with no possibility of defeating enemies or gaining NPC allies.
