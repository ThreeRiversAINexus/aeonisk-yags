# ML Training Scenario Library

**Purpose:** Comprehensive session config collection designed for maximum ML training data diversity, covering all underrepresented mechanics, skill archetypes, and gameplay scenarios.

**Created:** 2025-01-12
**Total Scenarios:** 15 long-campaign configs (10-20 turns each)
**Total Estimated Gameplay:** ~250 turns across all scenarios

---

## Overview

This library addresses critical gaps in existing session configs:
- **70% combat bias** → Balanced across combat, social, investigation, economic, ritual
- **Underutilized Aeonisk mechanics** → Seeds, Bonded weapons, exotic gear, ritual depth
- **Limited skill diversity** → Healer, tech specialist, diplomat, void specialist archetypes
- **Weak non-combat resolution** → Investigation, negotiation, exploration scenarios

**Design Philosophy:**
- **Long campaigns** (10-20 turns) for consequence depth and relationship building
- **Balanced exotic mix** (50% configs feature Bonded/Glyph/Void/Spirit-Weave gear)
- **Good AND odd teams** (cohesive cooperation vs. internal conflict dynamics)
- **Seeds in inventory** (Raw, Attuned, Hollow - FIRST configs to include Seeds!)
- **Moral complexity** (no clear villains, systemic issues, consequence branching)

---

## Scenario Catalog

### 01. Healer/Support - Outbreak at Terminus Outpost
**File:** `01_healer_support/medic_rescue_mission.json`
**Turns:** 15 | **Party:** 3 | **Void Level:** 6
**Tactical:** Disabled (Non-Combat Focus)

**Characters:**
- Sanctuary Vael (Resonance Communes) - Medicine 6, Counsel 5, Drip Veil Projector
- Enforcer Kael Thross (Pantheon Security) - Combat 5, Investigation 5, Union Heavy Pistol
- Void Theorist Iris Kain (Tempest Industries) - Astral Arts 6, Attunement 5, void 4

**Scenario:** Void-tainted plague outbreak at remote mining station. 12 sick NPCs need stabilization, limited medical supplies making traditional healing dangerous. Team tensions: Healer wants to save everyone, Enforcer wants quarantine/cleanup, Researcher wants to study contagion. Resource scarcity forces moral choices.

**Mechanics Tested:**
- Medicine checks for NPC stabilization
- Resource depletion (medical supplies clock)
- Void environmental hazards (void_level 6)
- Competing player goals (save vs. contain vs. research)
- Moral dilemma (triage decisions under scarcity)

**ML Training Value:** First healer/support archetype (Medicine 6), non-combat crisis resolution, NPC-heavy scenario, resource management, moral tension between humanitarian aid and threat containment.

---

### 02. Tech Specialist - Data Vault Infiltration
**File:** `02_tech_specialist/hacker_drone_heist.json`
**Turns:** 18 | **Party:** 3 | **Void Level:** 2
**Tactical:** Enabled (Stealth/Hacking Focus, Combat if Failed)

**Characters:**
- Ghost Protocol Zyn (Tempest Industries) - Hacking 6, Systems 6, Drone Operation 5
- Whisper Shade (Freeborn) - Stealth 6, Awareness 6, Wraithroot Vineblade (Spirit-Weave)
- Fixer Mira Voss (ACG) - Charm 6, Guile 5, Debtbreaker Sidearm (Contract weapon)

**Scenario:** Infiltrate Sovereign Nexus data vault to extract compromising Bond contract records. Must bypass biometric locks, surveillance drones, glyph wards, security patrols. Social cover as maintenance crew. Success = clean extraction, failure = combat escape or capture.

**Mechanics Tested:**
- Hacking/Systems checks
- Drone operation and countermeasures
- Stealth infiltration clocks
- Security response escalation
- Social deception (cover story maintenance)
- Electronic warfare

**ML Training Value:** First tech specialist archetype (Hacking 6, Drone Operation 5), infiltration-focused gameplay, stealth vs. combat branching, exotic weapons (Wraithroot Vineblade, Debtbreaker Sidearm).

**Exotic Gear:** Wraithroot Vineblade (+2 DMG, +1 hit when defending Bond, dream warnings), Debtbreaker Sidearm (locks if SC < 0, fires track-tags)

---

### 03. Pure Diplomat - The Seed Trade Summit
**File:** `03_pure_diplomat/negotiation_standoff.json`
**Turns:** 20 | **Party:** 3 | **Void Level:** 3
**Tactical:** Disabled (Zero Combat Scenario)

**Characters:**
- Mediator Lyris Venn (ACG) - Charm 6, Persuasion 5, Debt Law 6
- Harmonizer Sael (Resonance Communes) - Counsel 6, Insight 6, Empathy 5
- Advocate Thren Koss (Freeborn) - Persuasion 6, Guile 5, Investigation 5

**Scenario:** Three-faction summit over Seed harvesting rights (ACG wants monopoly, Communes claim spiritual sanctity, Freeborn demand labor rights). All factions have valid grievances. Must broker compromise preventing summit collapse → trade war. Failure modes: walkout, violence, one faction dominates.

**Mechanics Tested:**
- Charm/Persuasion/Counsel checks (pure social)
- Insight for reading NPCs
- Faction reputation (3 trust clocks: ACG, Commune, Freeborn)
- Social clocks (summit tension, treaty progress)
- NPC attitude shifts
- Compromise crafting

**ML Training Value:** Pure diplomat archetype (Charm 6, Persuasion 6, Counsel 6), ZERO combat scenario, multi-faction negotiation with 5 social clocks, moral trade-offs in diplomacy, failure = social collapse (not death).

---

### 04. Void Specialist - Breach Study
**File:** `04_void_specialist/dissolution_advocate.json`
**Turns:** 16 | **Party:** 3 | **Void Level:** 8
**Tactical:** Enabled (Pantheon Enforcers May Intervene)

**Characters:**
- Dissolution Theorist Kael Rift (Tempest) - Void Lore 6, Astral Arts 6, Attunement 6, void 5, Ash Pulse Pike
- Watcher Thane Vael (Pantheon Security) - Combat 5, Investigation 5, Shrike Cannon
- Observer Lyss Kain (Fractal Praxis) - Astral Arts 5, Investigation 6, Science 5, void 2

**Scenario:** Study active void breach to prove dissolution is controllable evolution. Lead researcher at void 5 approaching critical threshold. Must collect breach data, perform void exposure experiments, document reality warping, avoid Pantheon cleansing squad. Void 6+ triggers reality warping, void 7+ risks dissolution spiral.

**Mechanics Tested:**
- Void Lore checks
- Void accumulation (starting void 5, highest in any config)
- Reality warping at void 6-7+
- Ritual consecration/desecration
- Void cleansing rituals
- Environmental void hazards (void_level 8)
- Faction pursuit (Pantheon antagonists)

**ML Training Value:** Void specialist archetype (Void Lore 6, Attunement 6, starting void 5), void threshold mechanics testing (6-7+ effects), ritual consequence systems, Pantheon antagonist faction, moral ambiguity (is dissolution evolution or death?).

**Exotic Gear:** Ash Pulse Pike (Void-Infused, +4 DMG, stuns astral 1 round, +2 void on crit), Shrike Cannon (Glyph-Encoded, +6 DMG, ignores tier I-II ritual shields)

---

### 05. Investigation/Mystery - The Gestator's Death
**File:** `05_investigation_mystery/murder_at_gestation_pod.json`
**Turns:** 14 | **Party:** 3 | **Void Level:** 1
**Tactical:** Disabled (Investigation Focus)

**Characters:**
- Inspector Veyra Kross (Pantheon Security) - Investigation 6, Awareness 6, Insight 5
- Forensic Analyst Kael Ren (Arcane Genetics) - Systems 6, Science 6, Investigation 5
- Witness Liaison Mira Thane (House of Vox) - Charm 6, Insight 6, Counsel 5

**Scenario:** Gestator found dead in pod chamber with void contamination marks. Evidence suggests Bond corruption ritual gone wrong, sabotage, or accidental void exposure. 6 NPC witnesses with conflicting testimonies, partial security logs, ritual residue. Tribunal deadline: 10 rounds to present case with evidence. Red herrings: jealous co-worker, corporate espionage, secret Bond affair.

**Mechanics Tested:**
- Investigation/Awareness/Insight checks
- NPC witness interviews
- Forensic evidence analysis (Systems/Science)
- Time pressure (tribunal deadline clock)
- Reveal mechanics (red herrings)
- Lie detection (Insight)

**ML Training Value:** Investigation-led scenario, murder mystery structure with 6+ NPC witnesses, forensic analysis, time-pressure clock, red herring navigation, evidence-based reasoning, moral choice (truth vs. political pressure).

---

### 06. Economic Pressure - Debt Collection
**File:** `06_economic_pressure/debt_spiral_desperation.json`
**Turns:** 17 | **Party:** 3 | **Void Level:** 4
**Tactical:** Enabled (Potential Combat if Deals Go Bad)

**Characters:**
- Desperate Vex (Freeborn) - Stealth 5, Combat 4, soulcredit -5, 1 Drip cash
- Debt-Burdened Sael (Resonance Communes) - Astral Arts 5, Charm 4, soulcredit -4
- Grifter Kael (Freeborn) - Guile 6, Charm 5, soulcredit -3, 2 Drip cash

**Scenario:** Three characters drowning in ACG debt (SC -3 to -5). Offered high-risk job: smuggle illegal hollow seeds for 15 Drip payment. Legal work pays 2 Drip, not enough for 5 Drip minimum payment due in 8 rounds. Consequences: miss payment = repo agents, accept job = void exposure + criminal record. Vendors refuse service to negative SC characters.

**Mechanics Tested:**
- Soulcredit tracking and penalties
- Currency scarcity (only 4 Drip total starting cash, need 5)
- Vendor soulcredit gating (lockouts)
- Debt payment deadline clock
- Moral choice (illegal high-pay vs. legal poverty)
- Resource management under desperation

**ML Training Value:** Economic pressure system (all negative SC), currency scarcity, vendor lockouts, debt payment clock, moral compromises from desperation, repo agent NPC antagonists, consequence depth regardless of choice.

---

### 07. Faction Politics - The Breach Site Alliance
**File:** `07_faction_politics/three_way_alliance.json`
**Turns:** 18 | **Party:** 3 | **Void Level:** 7
**Tactical:** Enabled (External Threat + Potential PvP)

**Characters:**
- Void Researcher Arden (Tempest) - Astral Arts 6, Void Lore 5, void 4, Hollowed Repeater
- Codex Enforcer Lyss (Sovereign Nexus) - Combat 5, Debt Law 5, SC 7, Shrike Cannon
- Liberator Kael (Freeborn) - Combat 5, Stealth 5, Guile 5, SC -1

**Scenario:** Three factions discover ancient ritual site simultaneously. External threat: void cultists trying to destroy site. Forced cooperation to defend site, but each faction wants exclusive archive access. Tempest wants void research, Nexus wants to suppress dangerous knowledge, Freeborn wants to liberate information. Betrayal opportunities throughout.

**Mechanics Tested:**
- Multi-faction reputation (3 factions)
- Competing PC goals within party
- Shared external threat cooperation
- Betrayal mechanics
- Trust/suspicion clocks
- Potential PvP if alliance breaks

**ML Training Value:** Multi-faction party (Tempest vs. Nexus vs. Freeborn), competing goals (research vs. suppression vs. liberation), uneasy alliance dynamics, betrayal opportunities, potential PvP, trust erosion mechanics.

**Exotic Gear:** Hollowed Repeater (Void weapon, damage scales with void score, accuracy ↓ if Bonds > 0), Shrike Cannon (Glyph-Encoded, +6 DMG)

---

### 08. Ritual Consequences - The Ascension Gone Wrong
**File:** `08_ritual_consequences/failed_ascension_ritual.json`
**Turns:** 15 | **Party:** 3 | **Void Level:** 3 → 9
**Tactical:** Enabled (Void Manifestations + Panicked NPCs)

**Characters:**
- Ritualist Veyra Lune (Resonance Communes) - Astral Arts 6, Attunement 6, Magick Theory 5
- Containment Specialist Thane Kross (Tempest) - Systems 6, Attunement 5, Astral Arts 5, void 3
- Spiritual Guide Sael Thren (Resonance Communes) - Counsel 6, Charm 5, Astral Arts 5

**Scenario:** Failed ascension ritual catastrophically backfires: void backlash spreading through sanctuary, reality warping (walls bleeding, time loops), 15 NPCs in panic, bonded pair corrupted into void-touched entities. Must: contain breach, evacuate civilians, stabilize/mercy-kill corrupted victims, perform counter-ritual. Moral choice: risky counter-ritual (may worsen) vs. evacuate and let Pantheon destroy site.

**Mechanics Tested:**
- Ritual failure consequences
- Void environmental escalation (void 3 → 9)
- Reality warping effects
- NPC panic/rescue
- Soulcredit penalties for unsanctioned rituals
- Counter-ritual mechanics
- Moral choice (contain vs. evacuate, mercy killing)

**ML Training Value:** Ritual consequence depth, failed ritual fallout, void escalation from 3 → 9, reality warping mechanics, NPC rescue under duress, counter-ritual risk assessment, potential mercy killing decisions.

---

### 09. Bonded Weapons - The Stolen Bond
**File:** `09_bonded_weapons/bonded_blade_duel.json`
**Turns:** 16 | **Party:** 3 | **Void Level:** 2
**Tactical:** Enabled (Duel + Investigation + Conspiracy Combat)

**Characters:**
- Duelist Kael Ashblade (Freeborn) - Melee 6, Combat 5, Mnemonic Blade, Bondweave Mantle
- Rival Lyss Sparkveil (Resonance Communes) - Melee 6, Combat 5, Sparkspike Dagger, Echo-Lattice Gown
- Second Vex Oathbreaker (Freeborn) - Guns 6, Investigation 5, Oathpiercer Carbine

**Scenario:** Honor duel over stolen Bond contract accusation. Two duelists with Bonded weapons face off, but mid-fight evidence emerges: third party framed both to profit from their mutual destruction. Investigation pivot: discover conspirator while managing duel fallout. Bonded weapons create void risk (+1 void when used against Bonded targets).

**Mechanics Tested:**
- Bonded weapon mechanics (attunement, void penalties)
- Weapon-focused combat tactics
- Honor duel → investigation narrative pivot
- Conspiracy reveal mid-session
- Exotic armor (Spirit-Weave, Bonded)
- Moral choice (continue duel vs. unite)

**ML Training Value:** Exotic weapon showcase (ALL characters use Bonded/Glyph/Spirit-Weave gear), weapon attunement mechanics, Bonded weapon void consequences, honor duel structure, conspiracy storytelling, moral pivot point.

**Exotic Gear:**
- Mnemonic Blade (Bonded, +5 DMG, +2 DMG when trauma invoked, +1 void if used on Bond)
- Sparkspike Dagger (Bonded, +4 DMG, +1 DEF next turn if duel)
- Oathpiercer Carbine (Conventional, +DMG vs. ex-Bonds)
- Wraithroot Vineblade (Spirit-Weave, +2 DMG, +1 hit when defending Bond)
- Bondweave Mantle (Bonded armor, +4/+2, shares damage between Bonds)
- Echo-Lattice Gown (Spirit-Weave armor, +1, +1 DEF when aligned with principles)

---

### 10. Void Threshold Crossing - Beyond the Veil
**File:** `10_void_threshold_crossing/crossing_the_veil.json`
**Turns:** 14 | **Party:** 3 | **Void Level:** 6
**Tactical:** Enabled (Reality Manifestations + Pantheon Intervention)

**Characters:**
- Threshold Researcher Iris Veil (Tempest) - Void Lore 6, Astral Arts 6, Attunement 6, void 4, Ash Pulse Pike
- Medical Monitor Sanctuary Vael (Resonance Communes) - Medicine 6, Astral Arts 5, Drip Veil Projector
- Paranoid Observer Thane Kross (Pantheon Security) - Combat 5, Awareness 6, Shrike Cannon

**Scenario:** Void Theorist at void 4 intentionally pushes to void 6+ to access forbidden pre-Covenant knowledge. Experiment: controlled dissolution with medical monitor standing by. Reality warps at void 6 (wall phasing, dissolved soul echoes, time distortion), void 7 triggers dissolution spiral, void 8 = transformation point of no return. 6 rounds recovery window after void 7 before permanent change. Pantheon cleansing squad inbound (8 rounds ETA).

**Mechanics Tested:**
- Void threshold effects (void 6/7/8 specific mechanics)
- Reality warping phenomena
- Dissolution spiral mechanics
- Cleansing rituals under time pressure
- Medical stabilization (Medicine checks)
- Time-limited recovery window
- PC transformation as consequence
- Moral choice (knowledge vs. survival)

**ML Training Value:** Void threshold crossing mechanics (6 reality warping, 7 dissolution spiral, 8 transformation), intentional void accumulation experiment, reality instability, cleansing ritual desperation, time-limited recovery, PC transformation consequence, highest void character (void 4 → 8).

**Exotic Gear:** Ash Pulse Pike (Void-Infused), Shrike Cannon (Glyph-Encoded), Drip Veil Projector (Spirit-Weave, non-lethal, induces purge trance)

---

### 11. Moral Dilemma - The Dissolution Village
**File:** `11_moral_dilemma/both_sides_valid.json`
**Turns:** 19 | **Party:** 3 | **Void Level:** 5
**Tactical:** Conditional (Combat Only if Players Choose Violence)

**Characters:**
- Former Enforcer Veyra Kael (Pantheon Security → Independent) - Investigation 6, Insight 5, void 2
- Commune Advocate Sael Thren (Resonance Communes) - Counsel 6, Charm 6, Persuasion 5, void 3
- Neutral Scientist Lyss Kain (Fractal Praxis) - Science 6, Investigation 6, Void Lore 5, void 2

**Scenario:** Remote Freeborn village practicing 'controlled dissolution' philosophy (voluntarily approaching void 6-7 as spiritual evolution). Nexus mandates cleansing (void >5 must be purged per Codex). Village elder: eloquent, shows happy community, claims freedom from forced reincarnation. Nexus rep: compassionate, shows dissolution catastrophe statistics. Team must recommend: enforce cleansing (cultural genocide but prevent catastrophe), grant exemption (preserve freedom but risk outbreak), or negotiate compromise. NO clear villain - both sides have compelling moral/practical arguments.

**Mechanics Tested:**
- Moral choice with systemic consequences
- NPC persuasion depth (both perspectives valid)
- Factional reputation (Village vs. Nexus)
- Investigation of both perspectives
- Player value alignment testing
- Consequence branching (all choices have severe outcomes)
- Systemic ethical exploration (autonomy vs. safety)

**ML Training Value:** Moral ambiguity with no clear villain, both-sides-valid conflict (spiritual freedom vs. public safety), player values challenged, NPC perspectives with compelling arguments, consequence depth for ALL choices, systemic ethics (bodily autonomy, paternalism, collective responsibility).

---

### 12. Time Pressure - Countdown to Breach
**File:** `12_time_pressure/countdown_to_breach.json`
**Turns:** 10 | **Party:** 3 | **Void Level:** 8
**Tactical:** Enabled (Rear Guard Combat)

**Characters:**
- Pilot Commander Jex Varn (Freeborn) - Pilot 6, Systems 5, Awareness 5
- Rear Guard Thresh (Pantheon Security) - Combat 6, Guns 6, Shrike Cannon, Breach Hammer
- Seal Ritualist Veyra Lune (Resonance Communes) - Astral Arts 6, Attunement 6

**Scenario:** Mining station void breach will destroy entire station in EXACTLY 10 rounds (external countdown). Three competing objectives: evacuate 50 civilian NPCs (requires 6 rounds), seal breach with ritual (requires 4 rounds + sacrifice of PC void score), recover critical research (requires 3 rounds). Ship capacity: 40 NPCs maximum. Cannot achieve all objectives - must choose priorities. At round 10 END: station explodes regardless of completion.

**Mechanics Tested:**
- External deadline (10 rounds HARD limit, not clock-based)
- Competing objectives (impossible to all achieve)
- Resource allocation under time pressure
- Triage decisions (who to leave behind? VIPs vs. civilians?)
- Evacuation logistics
- Sacrifice mechanics (seal ritual requires PC void sacrifice, 50% success)
- Rear guard combat while evacuating
- Absolute consequence (round 10 = death)

**ML Training Value:** External deadline pressure (not clock-based countdown), competing objectives with impossible trade-offs, triage ethics, resource allocation, sacrifice choices, logistics management, absolute consequence timing.

**Exotic Gear:** Shrike Cannon (+6 DMG), Breach Hammer (+7 DMG, breaks bonded tech)

---

### 13. Exploration/Discovery - Expedition Mu-12
**File:** `13_exploration_discovery/uncharted_moon_expedition.json`
**Turns:** 20 | **Party:** 3 | **Void Level:** Unknown
**Tactical:** Enabled (Unknown Hazards May Include Combat)

**Characters:**
- Expedition Pilot Arden Vex (Freeborn) - Pilot 6, Systems 5, Awareness 6, Investigation 5
- Archaeologist Lyss Kain (Fractal Praxis) - Investigation 6, Science 6, Magick Theory 5, void 3
- Artifact Interface Specialist Kael Rift (Tempest) - Attunement 6, Astral Arts 6, Systems 5, void 4

**Scenario:** Uncharted moon with pre-Covenant ruins. Team hired to survey, map, assess commercial/research value. Unknown challenges: unstable terrain, ancient security systems, alien ecosystem, artifacts with unpredictable effects, reality distortions. Discovery opportunities: technology, historical records, Seed deposits, void phenomena. Information control: what to report to Tempest? What to suppress? What to sell to highest bidder?

**Mechanics Tested:**
- Exploration/mapping (Investigation + Pilot + Systems synergy)
- Unknown hazard management
- Artifact interaction (Attunement checks, unpredictable effects)
- Information control decisions (factional loyalty vs. profit vs. public good)
- Discovery clocks
- Terrain traversal (Athletics + Pilot)
- Environmental storytelling (DM-improvised based on PC choices)
- Factional information brokering

**ML Training Value:** Exploration/discovery gameplay in unknown territory, environmental challenges without predetermined solutions, artifact analysis, information control ethics, surveying mechanics, discovery-driven narrative, pre-Covenant mystery speculation.

---

### 14. Calm Before Storm - The Quiet Days
**File:** `14_calm_before_storm/gathering_storm.json`
**Turns:** 18 | **Party:** 3 | **Void Level:** 1 → 10
**Tactical:** Enabled (But Combat Delayed Until Round 13+)

**Characters:**
- Security Auditor Veyra Kross (Pantheon Security) - Investigation 6, Awareness 6, Insight 5
- Inventory Specialist Thane Mereth (Sovereign Nexus) - Investigation 6, Systems 6
- Interview Specialist Mira Thane (House of Vox) - Charm 6, Insight 6, Counsel 5

**Scenario:** Assigned 'boring' routine duties at Nexus station: security audit (rounds 1-4), inventory reconciliation (rounds 5-7), witness interviews (rounds 8-10). Subtle wrongness escalates: inventory discrepancies (ritual components missing), witnesses have memory gaps, security logs corrupted, void scanner shows background void rising (1 → 2 → 3), NPCs exhibiting synchronized strange behavior. Round 11-12: revelation that gestator pods infiltrated by void cultist sabotage, mass dissolution ritual in progress. Round 13+: explosive crisis - cultists activate ritual, void breach, reality fracture. Early choices matter: investigated anomalies = clues, dismissed warnings = unprepared.

**Mechanics Tested:**
- Slow-burn pacing (8-10 rounds investigation before crisis)
- Subtle clue placement (hidden in 'routine' tasks)
- Dramatic tonal shift (bureaucratic tedium → existential horror)
- Consequences of early choices (ignored clues = harder crisis)
- Atmosphere building (creeping dread)
- NPC foreshadowing (behavioral tells predicting reveal)
- Investigation depth before combat payoff
- Environmental storytelling

**ML Training Value:** Slow-burn pacing testing patience/attention rewards, subtle environmental clues, dramatic tonal shift mechanics (calm → crisis), early-round choice consequences, atmosphere/dread building, 'boring assignment → horror reveal' narrative structure.

---

### 15. Seed Economy - Seed Wars
**File:** `15_seed_economy/seed_cartel_war.json`
**Turns:** 17 | **Party:** 3 | **Void Level:** 4
**Tactical:** Enabled (Cartel Combat)

**Characters:**
- Attunement Ritualist Veyra Lune (Resonance Communes) - Attunement 6, Astral Arts 6, 8 Raw + 3 Attuned + 2 Hollow Seeds
- Trade Negotiator Kael Voss (ACG) - Charm 6, Guile 6, Debtbreaker Sidearm, 4 Raw + 2 Attuned Seeds
- Cartel Enforcer Thresh Kain (Freeborn) - Combat 6, Guns 6, Hollowed Repeater, 6 Hollow + 2 Raw Seeds

**Scenario:** Two rival Seed cartels (Hollow Syndicate vs. Spirit Traders) fighting over territory. Team hired as neutral brokers. Seed mechanics: Raw Seeds degrade in 7 cycles (timer), Raw use gives +1 void (needs echo-calibrator + ritual altar for safe attuning), Attuned Seeds stable and valuable, Hollow Seeds dangerous (+1 void, unstable). Cartel tensions: Syndicate floods market with cheap Hollows, Traders maintain quality Attuned supply at high prices. Economic pressure: component scarcity, degradation timers, competing buyers.

**Mechanics Tested:**
- Seed economy (Raw/Attuned/Hollow mechanics)
- Ritual attuning processes (echo-calibrator + ritual altar)
- Degradation timers (7 cycles for Raw → Hollow)
- Void contamination from Raw/Hollow usage
- Black market economics (scarcity, price manipulation)
- Cartel faction dynamics
- Economic pressure decisions (quality vs. speed, safety vs. profit)
- Attunement checks for ritual success

**ML Training Value:** FIRST config testing Seed economy mechanics (Raw/Attuned/Hollow), ritual attuning depth, echo-calibrator usage, degradation urgency, void contamination risks, black market economics, cartel politics, economic manipulation tactics. Total 29 Seeds across party (FIRST config with Seeds in starting inventory!).

**Exotic Gear:** Hollowed Repeater (Void weapon, damage scales with void score), Debtbreaker Sidearm (Contract weapon)

---

## Usage Guide

### Running a Scenario

```bash
# Activate venv
source .venv/bin/activate

# Run specific scenario
python3 scripts/run_multiagent_session.py \
  scripts/session_configs/ml_training_scenarios/01_healer_support/medic_rescue_mission.json
```

### Scenario Selection by Training Goal

**Non-Combat Mechanics:**
- 01 (Healer/Support) - Medicine, NPC stabilization
- 03 (Pure Diplomat) - Zero combat, all social
- 05 (Investigation) - Murder mystery, evidence gathering
- 13 (Exploration) - Discovery, mapping, artifact analysis

**Combat with Depth:**
- 02 (Tech Specialist) - Stealth/infiltration, electronic warfare
- 07 (Faction Politics) - Multi-faction conflict, potential PvP
- 09 (Bonded Weapons) - Exotic weapon showcase, honor duel
- 12 (Time Pressure) - Triage combat, evacuation logistics

**Ritual/Void Systems:**
- 04 (Void Specialist) - Void threshold mechanics, reality warping
- 08 (Ritual Consequences) - Failed ritual fallout, counter-ritual
- 10 (Void Threshold Crossing) - Intentional void accumulation, dissolution risk
- 15 (Seed Economy) - Ritual attuning, echo-calibrator usage

**Economic/Social Systems:**
- 06 (Economic Pressure) - Debt spiral, soulcredit scarcity
- 11 (Moral Dilemma) - Both-sides-valid conflict, ethical complexity
- 14 (Calm Before Storm) - Slow-burn pacing, investigation depth

**Exotic Weapons/Gear:**
- 02, 07, 09, 10, 12, 15 (all feature Bonded/Glyph/Void/Spirit-Weave gear)

### Team Dynamics

**Good Teams (Cohesive Cooperation):**
- 01 (Healer/Support) - Shared humanitarian goals despite tensions
- 03 (Pure Diplomat) - Complementary negotiation skills
- 05 (Investigation) - Detective/forensics/interviewer synergy
- 13 (Exploration) - Pilot/archaeologist/technician cooperation

**Odd Teams (Internal Conflict):**
- 06 (Economic Pressure) - Desperation-driven characters with clashing approaches
- 07 (Faction Politics) - Antagonistic factions forced to cooperate
- 11 (Moral Dilemma) - Characters with opposing ideological commitments
- 14 (Calm Before Storm) - Bureaucratic assignment masking deep conspiracy

---

## Mechanics Coverage Matrix

| Mechanic | Configs Testing |
|----------|----------------|
| **Medicine** | 01, 08, 10 |
| **Hacking/Systems** | 02, 05, 13 |
| **Charm/Persuasion** | 03, 05, 06, 14 |
| **Void Lore** | 04, 10, 13 |
| **Investigation** | 05, 11, 13, 14 |
| **Soulcredit Economics** | 06, 15 |
| **Multi-Faction Dynamics** | 03, 07, 11 |
| **Ritual Depth** | 08, 10, 15 |
| **Bonded/Exotic Weapons** | 02, 07, 09, 10, 12, 15 |
| **Void Threshold (6-7-8)** | 04, 10 |
| **Seed Economy** | 15 |
| **NPC Rescue/Interaction** | 01, 05, 08, 11 |
| **Time Pressure** | 05, 10, 12, 14 |
| **Moral Ambiguity** | 01, 06, 08, 11 |
| **Exploration/Discovery** | 13 |

---

## Character Archetype Coverage

| Archetype | Primary Config | Secondary Configs |
|-----------|---------------|-------------------|
| **Healer/Support** | 01 | 08, 10 |
| **Tech Specialist** | 02 | 05, 13 |
| **Pure Diplomat** | 03 | 05, 06, 11 |
| **Void Specialist** | 04, 10 | 07, 13, 15 |
| **Investigator** | 05 | 11, 13, 14 |
| **Combat Specialist** | 07, 09, 12 | 02, 04, 08 |
| **Ritualist** | 08, 15 | 04, 10 |
| **Pilot/Navigator** | 12, 13 | 02 |
| **Enforcer/Security** | 14 | 01, 04, 05, 10 |
| **Negotiator/Fixer** | 03 | 02, 06, 15 |

---

## Exotic Gear Showcase

**Bonded Weapons:**
- Mnemonic Blade (09) - +5 DMG, +2 when trauma invoked, +1 void if used on Bond
- Sparkspike Dagger (09) - +4 DMG, +1 DEF next turn if duel

**Glyph-Encoded Weapons:**
- Shrike Cannon (04, 07, 10, 12) - +6 DMG, ignores tier I-II ritual shields

**Void-Infused Weapons:**
- Ash Pulse Pike (04, 10) - +4 DMG, stuns astral 1 round, +2 void on crit
- Hollowed Repeater (07, 15) - Damage scales with void score, accuracy ↓ if Bonds > 0

**Spirit-Weave Weapons:**
- Wraithroot Vineblade (02, 09) - +2 DMG, +1 hit when defending Bond, dream warnings
- Drip Veil Projector (01, 10) - Non-lethal, induce purge trance (Will 18)

**Contract Weapons:**
- Debtbreaker Sidearm (02, 15) - +4 DMG, fires track-tags, locks if SC < 0

**Conventional Weapons:**
- Union Heavy Pistol (02, 07, 11, 12, 13, 14) - +4 DMG, ubiquitous street sidearm
- Breach Hammer (12) - +7 DMG, breaks bonded tech (Will 15)
- Oathpiercer Carbine (09) - +DMG vs. ex-Bonds

**Exotic Armor:**
- Bondweave Mantle (09) - +4/+2, shares damage between Bonds
- Echo-Lattice Gown (09) - +1, +1 DEF when aligned with principles

---

## ML Training Data Diversity

**Combat Scenarios:** 8 configs (53%)
**Non-Combat Scenarios:** 4 configs (27%)
**Hybrid Scenarios:** 3 configs (20%)

**Exotic Gear Usage:** 8 configs (53%)
**Seeds in Inventory:** 1 config (15) - FIRST to include Seeds!

**Skill Archetype Representation:**
- Medicine 6: 1 config (01)
- Hacking 6: 1 config (02)
- Charm/Persuasion 6: 4 configs (03, 05, 14, 15)
- Void Lore 6: 2 configs (04, 10)
- Investigation 6: 5 configs (05, 11, 13, 14, 15)
- Attunement 6: 4 configs (08, 10, 12, 15)
- Combat 6: 3 configs (09, 12, 15)
- Pilot 6: 2 configs (12, 13)

**Void Distribution:**
- void 0: 8 characters
- void 1-2: 12 characters
- void 3-4: 9 characters (including void 4 → 8 progression in 10)
- void 5+: 2 characters (highest in existing configs)

**Soulcredit Distribution:**
- SC -5 to -3: 5 characters (economic pressure testing)
- SC -2 to 0: 12 characters
- SC 1-4: 18 characters
- SC 5-8: 10 characters

---

## Version History

**v1.0** (2025-01-12) - Initial release, 15 scenarios covering all priority gaps

---

## Future Expansion Ideas

**Additional Scenarios to Consider:**
- Dreamwork mechanics testing (currently not represented)
- Long-term campaign (50+ turns) with mechanical evolution
- Player-vs-player tournament structure
- Faction warfare (large-scale tactical)
- Ritual failure cascades (multi-session consequences)
- Bond formation/breaking arcs (relationship mechanics)
- Dissolution cult infiltration (social stealth)
- Pre-Covenant archaeological expedition (extended exploration)

**Gaps Remaining:**
- Dreamwork system (zero configs test this)
- Vehicle/ship combat
- Multi-session campaign arcs
- Large-scale faction warfare
- Bond relationship mechanics depth
- Soulcredit positive extremes (SC 10+)

---

## Credits

**Design:** Claude Code (Anthropic)
**Aeonisk Setting:** Three Rivers AI Nexus
**YAGS System:** Samuel Penn (GNU GPL v2)
**Tactical Module:** v1.2.3

**License:** Aeonisk Permissive Commercial License (APCL) v1

---

For questions or contributions, see main project README.md
