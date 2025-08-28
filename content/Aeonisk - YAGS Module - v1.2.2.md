# Aeonisk - YAGS Module

*“Will is Power. Bond is Law. Void is Real.”*

Version 1.2.2

## 1. Introduction

Aeonisk is a science-fantasy roleplaying setting built on intimacy, intention, and control, using the **Yet Another Game System (YAGS)** as its foundation. In this world, there are no nations — only factions, dynasties, and spiritual economies. Technology hums in harmony with  magick. Rituals shape reality. Bonds bind more than blood.

You are a wielder of Will. You live in a world where to act is to mean  something — and to mean something is dangerous. This module adapts the  YAGS system into a framework for stories about:

- Sacred trust and betrayal
- Power bought with spirit, not coin
- The slow erosion of self under the weight of debt, duty, or the Void

You may rise through purpose, or fall through sacrifice. But either way: the Astral is watching.

### 1.1. What Kind of Game is Aeonisk?

Aeonisk YAGS focuses on:

- Emotional and spiritual tension, not just physical conflict.
- Ritual magick with consequences, cost, and deep symbolism.
- Formally declared Bonds as party cohesion and narrative anchors.
- A real spiritual economy of Soulcredit and ritual debt.
- The creeping influence of the Void as temptation and corruption.

It is ideal for:

- GMs who love story-first design with consequence-driven mechanics.
- Players who want their character's choices to echo in the Astral.
- Groups comfortable with intimacy, ideology, and irreversible sacrifice.

### 1.2. The Core Trinity of Aeonisk

- **Will:** Your purpose — not your desire, but your alignment with the world's  hidden pattern. Following it empowers you. Betraying it breaks you.
- **Bond:** A sacred, formal connection. Emotional, spiritual, sometimes political — but never casual. Bonds are the true structure of parties, not classes.
- **Void:** The result of power without connection. Isolation made manifest. The  astral price of intention unanchored to empathy or sacrifice.

### 1.3. YAGS System Integration

Aeonisk uses the core YAGS mechanics but modifies or adds the following:

| System Element        | Aeonisk YAGS Modification                                    |
| --------------------- | ------------------------------------------------------------ |
| Core Dice Mechanic    | Skill Attribute × Skill + d20                                |
| Ritual Resolution     | Willpower × Astral Arts + d20 vs Ritual Threshold. Outcome determined by margin of success/failure. |
| New Skills            | Astral Arts, Magick Theory, Intimacy Ritual, Corporate Influence, Debt Law, Pilot, Drone Operation |
| Void Score            | Tracks spiritual corruption (0–10); passively warps reality at 5+, triggers Void Spike on rapid gain. |
| Soulcredit            | Tracks spiritual trust and obligation (–10 to +10).          |
| Bond Mechanics        | Formal connections (max 3, Freeborn 1). Provides +2 to rituals and +1 Soak (defending Bonded). Can be sacrificed. |
| Ritual Tools          | Requires a Primary Ritual Item (non-consumable) and a sacrificial Offering  (consumed). No offering = +1 Void, potential outcome downgrade. |
| Tech/Enchantments     | Require significant offerings, narrative weight, and carry Void risk or spiritual cost. May interact with Soulcredit/Will. |
| Initiative (Optional) | Agility × 4 + d20                                            |

### 1.4. Birth & Origin (Biocreche Pod Gestation)

All civilized Aeonisk sapients—player characters and NPCs—originate from sealed **Biocreche Pods** rather than natural birth. During gestation, the pod merges a formal **Matron Bond** between two women with their contributed Raw Seeds, forming an Echo-Seed embryo that is sculpted through mnemonic infusions. When the pod matures it opens in a public *Rite of Unveiling*, assigning Covenant Ring, first Soulcredit imprint, and lineage records.

Characters with the **Freeborn / Unbound** origin are the sole exception: they may record the rare `natural` birth method, carrying a *Discordant Echo* until later harmonisation.

Record a new field on every character sheet:

```yaml
birth_method: biocreche_pod   # or 'natural' for Freeborn
```

A valid Matron Bond is presumed for pod-gestated characters unless explicitly broken for story reasons.

## 2. Core YAGS Mechanics

YAGS uses a relatively simple set of core rules.

### 2.1. Terminology

- **Attribute:** One of the eight basic numbers defining a creature. Typical human average is 3.
- **Skill:** Defines training and experience in a narrow field. Combined with Attributes for task resolution. Professional level is 4+.
- **Ability:** Attribute × Skill (for Skill Checks) or Attribute × 4 (for pure Attribute Checks).
- **Die:** A single twenty-sided die (d20).
- **Difficulty:** The target number for a task. Ability + d20 must meet or exceed the Difficulty. Moderate tasks are Difficulty 20.
- **Task:** An activity requiring an Ability check (Attribute × Skill + d20 or Attribute × 4 + d20).
- **Score:** The raw numerical value of a characteristic.

### 2.2. Task Resolution

The core mechanic for almost all actions:

Ability + d20 vs Difficulty

- **Skill Check:** Attribute × Skill + d20 vs Difficulty
- **Attribute Check:** Attribute × 4 + d20 vs Difficulty

**Difficulties (YAGS Standard):**

| Type           | Target | Description                                                  |
| -------------- | ------ | ------------------------------------------------------------ |
| Very easy      | 10     | Minimal skill needed. Professionals always succeed.          |
| Easy           | 15     | Small amount of skill needed. Difficult for untrained.       |
| Moderate       | 20     | Achievable by professionals in ideal conditions. Difficult without. |
| Challenging    | 25     | Requires professional skill. Out of league for basic familiarity. |
| Difficult      | 30     | Requires high skill. Even professionals hard pressed.        |
| Very difficult | 40     | Master level required. Highest difficulty in normal circumstances. |
| Extreme        | 50     | Very difficult task under poor conditions.                   |
| Heroic         | 60     | Truly heroic.                                                |
| Sheer folly    | 75     | Requires superhuman skill.                                   |
| Absurd         | 100    | Beyond most capabilities.                                    |

*(Aeonisk typically uses a narrower range of 15-20 for standard Skill Checks, but Rituals have their own specific thresholds. GMs can use the YAGS  standard for non-ritual tasks. See also Section 6.6 for Aeonisk-specific DC Guidelines).*

**Fumbles & Criticals:**

- A natural '1' on the d20 is an automatic failure (fumble).
- A natural '20' on the d20 in a Skill Contest automatically wins if your skill score is higher than the opponent's.

**Degrees of Success:**
If how well you succeed matters:

- **Moderate Success:** Meet the Difficulty.
- **Good Success:** Exceed Difficulty by 10+. (Task performed with style, completeness, or speed).
- **Excellent Success:** Exceed Difficulty by 20+. (Performed with two of style/completeness/speed).
- **Superb Success:** Exceed Difficulty by 30+. (Performed with style, completeness, *and* speed).
- **Fantastic Success:** Exceed Difficulty by 40+.
- **Amazing Success:** Exceed Difficulty by 50+. (Close to perfection).

**Skill Contests:**
Instead of a fixed Difficulty, two or more characters roll their relevant Ability + d20.

- Highest roll wins.
- On a tie, the character with the higher Skill *score* wins.
- A natural '20' wins automatically if your Skill score is higher.

**Skilled Professionals (Skill 4+):**
Professionals have extra options for predictable, non-opposed tasks:

- **Assume '0':** For predictable tasks, assume a d20 roll of '0'. Negates fumble chance but requires the task to be well within capability.
- **Assume '10':** For non-stressful tasks where you can take time, assume a d20 roll of '10'. Removes fumble risk but takes twice as long.
  *(GM decides if a task is predictable/stressful. If fumble chance > 1, these options cannot be taken).*

### 2.3. Attributes

Eight primary attributes define raw potential. Human average is 3, range typically 2-5 (higher is rare).

- **Strength (Str):** Physical power, lifting, hurting, breaking things. Carrying capacity is based on Str^2.
- **Health (Hea):** Endurance, fitness, resisting injury/poison/fatigue, staying conscious.
- **Agility (Agi):** Quickness, acrobatics, balance, dodging, brawling.
- **Dexterity (Dex):** Hand-eye coordination, sleight-of-hand, melee/pistol skills, driving.
- **Perception (Per):** Alertness, senses (vision, hearing), observation, noticing things. Used for rifles/bows.
- **Intelligence (Int):** Wit, cunning, memory, intuition, logic, knowledge skills.
- **Empathy (Emp):** Understanding others, manipulation, reaction, charisma base.
- **Willpower (Wil):** Mental fortitude, resisting fear/magic/temptation, concentration, lying. Key for Aeonisk Rituals.

**Attribute Levels (Human Norm):**

| Score | Level       | Description                                                  |
| ----- | ----------- | ------------------------------------------------------------ |
| 0     | None        | No rateable ability. Cannot attempt skills using it.         |
| 1     | Crippled    | Severely impaired (very dumb, ill, socially inept).          |
| 2     | Poor        | Noticeably below average (bottom 10%). Minimum possible for most. |
| 3     | Average     | Middle 80% of the population.                                |
| 4     | High        | Noticeably above average (top 10%).                          |
| 5     | Very High   | Highly adept naturally. Highest natural level without training. |
| 6     | Exceptional | Truly exceptional, trained hard. Hard to compete against.    |
| 7     | Incredible  | One of a small number in the country.                        |
| 8     | Legendary   | Normal human maximum. Handful of people in the modern world. |
| 9+    | Superhuman  | Beyond natural possibility.                                  |

**Secondary Attributes:**

- **Size:** Defaults to 5 for adult humans (range 4-6). Governs soak capacity and wound levels. Logarithmic scale (see YAGS rules).
- **Move:** Determines speed. Equal to Size + Strength + Agility + 1. (Typical human: 5+3+3+1 = 12). Combat move = Move / 2 (rounded down).
- **Soak:** Base resistance to damage. Defaults to 12 for adult humans. Modified by armour.

### 2.4. Skills

Skills represent training and experience. Most default to 0 unless learned.

**Skill Levels:**

| Level | Description           | Notes                                                        |
| ----- | --------------------- | ------------------------------------------------------------ |
| 1     | Casual                | Basic familiarity (single lesson, brief exposure).           |
| 2-3   | Student               | Studied in school or reasonable practice. Succeeds at easy tasks. |
| 4-7   | Professional          | Competent professional (4-5). Seasoned veteran (6-7). Can buy Techniques. |
| 8-11  | Master                | True understanding, years of dedicated study. Elite level.   |
| 12-15 | Legendary             | Highest level found in most worlds. Leaders in their field.  |
| 16+   | Mythical / Superhuman | Province of superheroes or supernatural beings.              |

**Types of Skills (YAGS Standard):**

- **Talents:** 8 core skills known to some extent by all humans (start at 2).  Athletics, Awareness, Brawl, Charm, Guile, Sleight, Stealth, Throw.
- **Knowledges:** Theoretical knowledge, must be learned (Skill 1+). Cannot be used untrained.
- **Languages:** Rated 1-4+ for fluency. Not typically rolled.
- **Standard Skills:** Mix of knowledge, experience, aptitude. Can be used untrained, but roll (straight d20) is halved, fumble on 1 or 2.

**Skill Defaults:**
Some skills can default to others (often a Talent). When using a default:

- Final result (Attribute × Skill + d20) is halved.
- Fumble chance is doubled (or minimum 2 if it was 1).
- Cannot use Techniques.

**Skill Pre-requisites:**
Some skills require others at a certain level before they can be learned.

- Must meet all pre-requisites before buying Skill level 1.
- A skill can never be more than double the level of any of its pre-requisites.

**Techniques:**
Specialisations bought with experience points, allowing bonuses or special actions.

- Require a minimum skill level equal to their cost.
- May have prerequisite techniques.
- **Familiarities:** Required for skills covering diverse equipment (e.g., Drive). Cost 2-4 points. Using without familiarity halves roll.
- **Specialisations:** Focus knowledge (e.g., History [English Civil War]). Makes specific tasks easier.
- **Masteries:** Levelled specialisations (cost 1 per level) for competitive/artistic  skills. Grant +1 bonus per level. Opponents with lower mastery suffer +1 fumble chance per level difference.

## 3. Aeonisk Core Mechanics

Aeonisk builds upon YAGS, adding unique systems for rituals, spiritual standing, and personal destiny.

### 3.1. Rituals

Rituals are acts of intention, symbolism, and sacrifice, not simple spells. They channel Will through the Astral.

- **Ritual Roll:** Willpower × Astral Arts + d20 [+2 if Bonded participant assists] vs Ritual Threshold.
- **Outcome:** Success or failure, and the consequences, are determined by the margin  against the Ritual Threshold (see Section 6). No second roll is needed.

**Ritual Thresholds:**

| Type      | Ritual Threshold | Description                                                |
| --------- | ---------------- | ---------------------------------------------------------- |
| Minor     | 16               | Emotional veil, symbolic marking, light defense            |
| Standard  | 18               | Bond reinforcement, magickal tracking, simple bindings     |
| Major     | 20–22            | Contract severing, astral healing, memory reweaving        |
| Forbidden | 26–28            | Soul extraction, resurrection, Void channeling (High Void) |

**Requirements:**

- **Primary Ritual Item:** A non-consumable item, sacred to the caster. Required for meaningful rituals. If lost: –2 to Ritual Rolls.
- **Offering:** A consumable item or concept (emotion, memory, blood, object)  symbolically appropriate to the ritual's intent. Burned, buried, bled,  spoken, etc.
  - **Skipping Offering:** Gain +1 Void. May shift the ritual outcome downward by one tier on the  outcome table (see Section 6). Unethical intent also triggers Void  penalty.

*(See Section 6 for detailed Ritual Rules).*

### 3.2. Soulcredit & Void

These track spiritual alignment and trustworthiness.

- **Soulcredit (SC):** –10 to +10. Represents spiritual trust and standing.
  - *Gain:* Fulfill contracts, aid rituals, cleanse Void.
  - *Lose:* Break Bonds/contracts, ritual without offering, betray Guiding Principle.
  - *Effects:* Influences faction relations, access to tech/rituals. (+6 to +10 = Trusted; –6 to –10 = Hunted/Cut Off).
- **Void Score (VS):** 0 to 10. Represents spiritual corruption and disconnection.
  - *Gain:* Skip offerings, unethical rituals, break Guiding Principle, use Void-forged items.
  - *Effects:*
    - **Void Spike:** Gaining 2+ Void from a single event stuns the character (see Section 7.1).
    - **Void ≥ 5:** Passively alters the environment, causing narrative instability (see Section 7.1).
    - **Void ≥ 7:** Bonds become Dormant; sacred spaces reject you.
    - **Void = 10:** Claimed by the Void (potential loss of agency).
  - *Cleanse:* Ritual at ley site, restore Bond, sacrifice something irreplaceable.

*(See Section 7 for detailed Void & Soulcredit Rules).*

### 3.3. Bonds

Formal, mutual metaphysical connections based on ritual or oath. The backbone of relationships and party structure.

- **Limit:** Max 3 Bonds (Freeborn origin: 1).
- **Benefits:**
  - +2 to Ritual Rolls when performing together.
  - +1 Soak when defending a Bonded partner.
- **Sacrifice a Bond (Sever):** Once per session, gain +5 to *any* Willpower-based roll.
  - *Cost:* +1 Void, +1 Soul Debt (to the severed person), –1 Empathy for the scene. A major narrative and spiritual act.

*(See Section 8 for detailed Bond Rules).*

### 3.4. Guiding Principle

Your soul's sacred trajectory or purpose. Not a motto, but a metaphysical path.

- **Declaration:** Starts undefined. Declared mid-play through insight, ritual, or character growth.
- **Alignment:** Acting *in* alignment grants +1 to *all* Willpower-based rolls.
- **Betrayal:** Acting *against* declared Guiding Principle incurs +3 Void and triggers a narrative/spiritual  crisis (GM discretion). Additionally, if performing a ritual that  contradicts declared Guiding Principle, the margin result is worsened by one  tier (see Section 6).

*(See Section 8 for more on Guiding Principle).*

### 3.5. Aeonisk Currency: Elemental Economy

Aeonisk uses charged elemental talismans instead of abstract money. Value is transferred energy.

- **Types:** Grain (Earth), Drip (Water), Spark (Fire), Breath (Air). Each represents different conceptual energies.
- **Forbidden:** Hollow (Void) - Black market, corrupting.
- **Potential:** Seed (Raw/Unaligned) - Raw Seeds are unstable potential, cannot be traded directly as currency, and must be ritually attuned to an elemental aspect (e.g., Spark, Drip) to become stable and usable in specialized gear or as foundational talismans. Using a Raw Seed without attunement typically incurs Void.
- **Usage:** Energy is siphoned from talismans (e.g., Spark Core 743/1000) to pay  others or power devices. Empty talismans can be recharged or sacrificed.
- **Sizes:** Single (1 unit), Band (10-99), Sigil (100-999), Core (1k-9.9k), Vault (10k+).

*(See Section 9 for detailed Currency Rules).*

## 4. Character Creation

Create an Aeonisk character using YAGS principles, modified by the setting's unique elements.

### 4.1. Step 1: Concept & Priority

Decide on your character concept. The GM sets the starting power level  (Mundane, Skilled, Exceptional, Heroic - see YAGS Characters PDF), which determines points pools. Prioritize the three point pools (Attributes,  Experience, Advantages) into Primary, Secondary, Tertiary based on your  concept.

### 4.2. Step 2: Choose Origin (Faction/Background)

Select an Origin. This grants an Attribute bonus (+1 to one of two listed stats) and a special trait.

| Origin                | Attribute Bonus (+1)    | Trait                                                        |
| --------------------- | ----------------------- | ------------------------------------------------------------ |
| Sovereign Nexus       | Willpower or Int        | **Indoctrinated:** +2 to resist ritual disruption or mental influence. |
| Astral Commerce Group | Intelligence or Emp     | **Contract-Bound:** Start with +1 Soulcredit or one favourable minor contract/debt owed *to* you. |
| Pantheon Security     | Strength or Agility     | **Tactical Protocol:** Once per combat, automatically succeed on an Initiative roll (treat as 20). |
| Aether Dynamics       | Empathy or Perception   | **Ley Sense:** Can sense the presence, general strength, and mood (calm/turbulent) of nearby ley lines. |
| Arcane Genetics       | Health or Dexterity     | **Bio-Stabilized:** +2 to rolls resisting biological Void effects, disease, or mutation. |
| Tempest Industries    | Dexterity or Perception | **Disruptor:** +2 bonus when attempting to sabotage or hijack rituals or ritually-encoded tech. |
| Freeborn / Unbound    | Any 3 Attributes        | **Wild Will:** Can only form/maintain 1 Bond. Cannot sacrifice this Bond without extreme cost (GM call). |

### 4.3. Step 3: Assign Attributes

Distribute points into the 8 primary YAGS attributes (Str, Hea, Agi, Dex, Per,  Int, Emp, Wil) according to your chosen priority level and point pool.  Remember the human average is 3. Apply your +1 Origin bonus *after* spending points. Check maximum attribute level allowed by campaign level.

### 4.4. Step 4: Choose Skills

Spend Experience points on Skills. Select from the YAGS core list or  Aeonisk-specific skills. All characters start with the 8 Talents  (Athletics, Awareness, Brawl, Charm, Guile, Sleight, Stealth, Throw) at  level 2 for free. Check maximum skill level allowed by campaign level.

**Aeonisk Skills:**

| Skill               | Attribute | Description                                                  |
| ------------------- | --------- | ------------------------------------------------------------ |
| Astral Arts         | Willpower | Channeling, resisting, and shaping spiritual energies in rituals. |
| Magick Theory       | Int       | Knowledge of glyphs, ritual systems, sacred mechanics, Aeons. |
| Intimacy Ritual     | Empathy   | Performing emotionally-powered or Bond-based rituals. Requires trust. (Includes Intimidation Ritual as a use-case: a ritual “threat” instead of a social roll. Check: Empathy × Intimacy Ritual + d20. Subdomain tag: `intimidation_ritual`). |
| Corporate Influence | Emp       | Navigating faction politics, extracting favors, reading intentions. |
| Debt Law            | Int       | Understanding/manipulating contracts, oaths, Soulcredit systems. |
| Pilot               | Agility   | Use for any vehicle or EVA-station-keeping task (e.g. slipstream jumps, docking holds). Check: Agility × Pilot + d20. Subdomain tag: `pilot_check`. |
| Drone Operation     | Intelligence | For remote spark-burst, EMP, mapping, or hacking via drones. Check: Intelligence × Drone Operation + d20 (or Intelligence × Electronics Operation + d20 if Drone Operation is treated as a specialization). Subdomain tag: `drone_operation`. |

### 4.5. Step 5: Define Guiding Principle (Later)

Leave your Guiding Principle undefined for now. It will emerge and be declared during play.

### 4.6. Step 6: Form Bonds (Optional)

You start with no Bonds unless determined otherwise by the GM or through  spending Advantage points (if allowed). Bonds are formed in-game through ritual or oath. Max 3 (Freeborn: 1).

### 4.7. Step 7: Gather Ritual Kit & Equipment

- **Primary Ritual Item (1):** Define a personal, sacred item. Narratively important, mechanical effect if lost (-2 Rituals).
- **Offerings (1-3):** Define 1-3 starting consumable offerings appropriate to your character concept.
- **Starting Currency:** GM determines starting elemental currency based on TL and background  (e.g., equivalent to YAGS starting cash, converted to elemental  talismans).
- **Other Gear:** Basic clothing, tools of trade are assumed. Spend remaining starting  funds or use Advantage points for significant items (weapons, armour,  tech).

### 4.8. Step 8: Calculate Secondary Attributes & Final Checks

- **Size:** Default 5 (human).
- **Move:** Size + Str + Agi + 1.
- **Soak:** Base 12 (human). Add armour bonuses.
- **Void Score:** Starts at 0.
- **Soulcredit:** Starts at 0.
- **Wound/Stun/Fatigue Levels:** Based on Size (Humans typically have 5 levels before Fatal/Out/Exhausted).

## 5. Combat Rules (Optional System)

Combat uses the YAGS core loop, potentially modified by Aeonisk elements. GMs may opt for more narrative resolution.

### 5.1. Combat Round (~5 seconds)

1. **Roll Initiative:** (Once per combat)
   Initiative = Agility × 4 + d20

   - High roll acts earlier.
   - Fumble (natural 1): Initiative becomes 0. All rolls halved for the round, actions are Slow.

2. **Declare Actions:** (In *increasing* initiative order - lowest goes first)

   - State intended action (attack, move, defend, wait, ritual, etc.).
   - Declare number of defences (Max = Average of Agility & Perception, round up; typically 3 for humans).

3. **Resolve Actions:** (In *decreasing* initiative order - highest goes first)

   - **Fast Actions:** Resolve first. (e.g., Quick Shot, some manoeuvres).
   - **Normal Actions:** Resolve next. (e.g., Standard Attack, Move + Attack).
   - **Slow Actions:** Resolve last. (e.g., Sprint + Attack, Aimed Shot, most Rituals).

4. **Make Attacks:**

   - **Attack Roll:** Attribute × Skill + Weapon Bonus + d20
     *(Attribute/Skill depends on weapon: e.g., Dex × Melee, Per × Guns, Agi × Brawl)*
   - **Defense Roll:** Attribute × Skill + Weapon Defense + d20
     *(Usually same Attribute/Skill as attack type being defended against)*
   - **Hit:** If Attack Roll ≥ Defense Roll. (If not defending, Attack Roll vs base Difficulty 15).

5. **Inflict Damage:**

   - **Damage Roll:** Strength × 1 + Weapon Damage + d20
   - **Soak:** Target's base Soak + Armour bonus.
   - **Effect:** If Damage Roll ≥ Soak, deal Wounds or Stuns. 1 level per 5 points damage exceeds Soak.

6. **Track Wounds/Stuns:**

   | Wounds | Stuns | Penalty | Description                     |
   | ------ | ----- | ------- | ------------------------------- |
   | 1      | 1-2   | -       | Minor (Bruised)                 |
   | 2      | 3     | -5      | Light (Lightly Wounded/Stunned) |
   | 3      | 4     | -10     | Moderate (Wounded/Stunned)      |
   | 4      | 5     | -15     | Heavy (Seriously Wounded/Dazed) |
   | 5      | 6+    | -25     | Critical (Critical/Beaten)      |
   | 6+     | -     | -40     | Fatal (Health check or die)     |

   - Wounds track lasting injury. Stuns track temporary impact/bruising. Penalties stack!
   - *Damage Types:* Wound (swords, bullets), Stun (fists, clubs), Mixed (knives; half wounds, half stuns).

7. **End of Round:**

   - Make Health checks to stay conscious if Critical/Fatal/Beaten.
   - Apply ongoing effects (bleeding, poison, rituals, Void).
   - Start next round (Declare Actions).

### 5.2. Aeonisk Combat Considerations

- **Void Spike:** Gaining 2+ Void at once can stun a character, causing them to lose their next turn.
- **Void:** High Void score (5+) causes environmental disruption (see Sec 7.1) that can lead to narrative complications, fumbles, misfires, or tech  glitches at GM discretion.
- **Bonds:** Gain +1 Soak when actively defending a Bonded partner from an attack targeting them.
- **Technology:** Weapon properties (Glyph, Void, Contractual) apply. Tech may malfunction due to Void environmental effects or low Soulcredit.
- **Rituals in Combat:** Usually Slow actions. Require concentration (Focused stance - no  defense). Interrupting a ritual can cause backlash based on the Margin  Outcome table (typically a Failed result).

## 6. Ritual System (Detailed)

Power flows through sacrifice. Without offering, there is only Void. Rituals  alter emotion, memory, contracts, spiritual structure, or reality.

### 6.1. Performing a Ritual

1. **State Intent:** Clearly define the ritual's purpose (e.g., "Reinforce my Bond with Wren," "Cleanse this area of Void residue").

2. **Gather Components:**

   - **Primary Ritual Item:** Must be held/present. Personal, sacred. Loss incurs -2 penalty to Ritual rolls.
   - **Offering:** Consumed during the ritual. Must be symbolically relevant. Skipping  incurs +1 Void and potentially worsens the outcome (see Step 5).

3. **Roll Ritual:** Willpower × Astral Arts + d20 [+2 if Bonded participant assists]

4. **Check Success:** Compare result to the Ritual Threshold.

   | Type      | Ritual Threshold |
   | --------- | ---------------- |
   | Minor     | 16               |
   | Standard  | 18               |
   | Major     | 20–22            |
   | Forbidden | 26–28            |

5. **Determine Outcome by Margin:** Ritual Outcome is now determined solely by the margin of success or  failure against the Ritual Threshold. No second roll is needed.

   **Margin of Success vs Ritual Threshold:**

   | Margin       | Result               | Consequence                                 |
   | ------------ | -------------------- | ------------------------------------------- |
   | –10 or worse | Catastrophic fumble  | +2 Void, backlash, GM invokes Fallout       |
   | –5 to –9     | Failed + backlash    | +1 Void, Bond strain, minor spiritual bleed |
   | –1 to –4     | Failed (no effect)   | Emotional fatigue or confusion (GM choice)  |
   | 0 to +4      | Weak success         | Side effects, reduced duration or clarity   |
   | +5 to +9     | Solid success        | No backlash, full effect if offering used   |
   | +10 to +14   | Strong resonance     | Gain minor benefit (e.g., +1 SC, insight)   |
   | +15+         | Echo or breakthrough | Exceptional results, story-altering power   |

   > Offerings remain essential. Skipping adds +1 Void and may shift result downward by one tier.
   > If performing a ritual that contradicts declared Guiding Principle, the margin result is worsened by one tier.

6. **Adjudicate Outcome:** GM describes the effects based on the result from the Margin Outcome  Table, the ritual's intent, the offering (or lack thereof), and the  narrative context.

### 6.2. Ritual Outcome Consequences

The Margin Outcome Table (Section 6.1, Step 5) covers the spectrum of results:

- **Catastrophic Fumble (Margin –10 or worse):** Severe negative consequences, high Void gain, and potential narrative Fallout invoked by the GM.
- **Failure with Backlash (Margin –5 to –9):** The ritual fails and causes tangible negative effects like Void gain, spiritual harm, or strained Bonds.
- **Simple Failure (Margin –1 to –4):** The ritual simply doesn't work, potentially causing minor mental or emotional effects.
- **Success Tiers (Margin 0+):** The ritual works to varying degrees of effectiveness, potentially with  side effects at lower margins or beneficial bonuses at higher margins.

The Margin Outcome Table covers the raw mechanical results. For immediate narrative color, use one of these evocative hooks:

- Sparks of uncontrolled charge dance around runes.
- Sigils or ritual tools crack, losing potency for a moment.
- Nearby creatures are swept by an emotional echo, reliving someone else's memory.
- A minor spirit stirs in response, hinting at future complications.
- Bonds strain or pulse painfully, testing PC connections.
- Ritual intent inverts—healing inflicts pain, wards invite intrusion.

### 6.3. Group Rituals

- **Base Formula:** The group's ritualistic power is the sum of (Willpower × Ritual Skill) for each caster, plus one flat group bonus (e.g., +2 Synergy Bonus, not +1 per extra caster).
- **Offerings:** Each extra caster (beyond the primary) must expend a minor Offering (e.g., 1 Spark or 1 Breath) or the group incurs +1 Void per caster without an offering. The primary caster also provides their standard offering.
- **DC Scaling:**
    - Small party (2-3 casters): DC = 18–22
    - Large party (4+ casters) or high-stakes: DC = 24–30
- **Roll:** The lead caster makes a single Ritual Roll using the group's combined power against the scaled DC.
- Requires mutual Bonds among participants for most effective group rituals.
- Consequences from the outcome table (Void gain, backlash, benefits) generally apply to all participants, unless the GM rules otherwise based on narrative context.
- Dreamwork can be done in groups as well, following similar principles.

**Example: Revised Group Ritual Rule (Ley Repair)**

- **Participants:** Kaelia (Willpower 5 × Astral Arts 4 = 20), Sorin (Willpower 3 × Astral Arts 3 = 9), Althaea (Willpower 4 × Astral Arts 2 = 8)
- **Subtotal:** 20 + 9 + 8 = 37
- **Synergy Bonus:** +2 (flat for group participation)
- **Offerings:** 3 Spark (one per caster, or one per extra caster if primary offering is different) OR +1 Void per missing offering (up to +3 Void).
- **DC:** 30 (Large party, high-stakes)
- **Roll:** 37 (Subtotal) + 2 (Synergy) + d20 ⇒ total vs DC 30

### 6.4. Void and Rituals

- **Void ≥ 5:** The passive environmental disruption (see Section 7.1) caused by high  Void can interfere with rituals. GM may apply narrative penalties,  increase the risk of unstable outcomes (potentially shifting the result  down a tier on the Margin table), or introduce complications related to  the ambient Void effects.
- **Void ≥ 7:** Cannot participate in group rituals (Bonds are Dormant). Own rituals  are significantly more prone to unstable results (GM likely shifts  results down one or even two tiers on failure, or introduces severe side effects even on success).
- **Void Gain from Rituals:** Gaining 2+ Void from a single ritual (e.g., Catastrophic Fumble or  Failure+Backlash combined with skipping an offering) triggers a **Void Spike** (see Section 7.1).

### 6.5. Ritual Library v1 (Examples)

*(See Appendix 2 for full list and template). Tag each ritual entry with a subdomain (e.g. `ritual_healing`, `ritual_binding`, `ritual_scrying`, `ritual_snare`) so it's easy to index.*

**Minor (Threshold 16):**

1. **Veil the Thread:** Conceal a Bond from detection (1 scene). *Offering:* Knotted hair, burned.
2. **Scent of the Ley:** Sense emotional residue of place/object. *Offering:* Held breath into ash.
3. **Sigil of Refusal:** Temporarily disrupt tracking/scrying glyph. *Offering:* Name written, submerged in oil.

**Standard (Threshold 18):**

1. **Thread the Bond:** Reinforce Bond (+1 Wil rolls for session, requires "Solid Success" margin or better). *Offering:* Written confession, sealed.
2. **Ghost of the Ledger:** Compel truthful answer to 1 question (target with spiritual debt, requires "Solid Success" margin or better). *Offering:* Torn ledger page, blood.
3. **Seal the Threshold:** Temporary barrier vs spiritual intrusion/Void. *Offering:* Salt and personal ash circle.
4. **Attunement Ritual:** Uses an appropriate skill (e.g., Astral Arts, Magick Theory, or a dedicated Attunement skill if available) to ritually process a Raw Seed, aligning it to a specific elemental aspect (Spark, Drip, Breath, Grain), transforming it into a stable Attuned Seed. Can also refer to rituals for attuning other items or oneself to concepts/energies, like ship attunement for ley navigation.

**Major (Threshold 20-22):**

1. **Unveil the Scar:** Reveal memory/trauma (willing/Bonded target). *Offering:* Item tied to memory.
2. **Red Exchange:** Permanently transfer ritual debt (requires "Strong Resonance" margin or better). *Offering:* Shared wound, silver thread.
3. **Skin of the Hollow:** Gain target's skill (-2) for 1 scene (requires "Solid Success" margin or better). *Offering:* Token imbued with memory.

**Forbidden (Threshold 26-28):**

1. **Last Whisper of the Hollow:** Speak with Claimed soul (1 scene). *Offering:* Bone/hair of deceased, salt, blood. *Void:* +3 always on failure, +1 on weak success.
2. **Reverse the Oath:** Fundamentally break sacred contract/Bond. *Offering:* Original contract burned, blood drops. *Void:* +2 to +4 depending on severity and margin.
3. **Forge the Blade of Debt:** Bind soul-debt into item (+2 vs debtor). *Offering:* Debtor's name burned with Void-ash. *Void:* +4 always on failure, +2 on weak success.

### 6.6. DC Guidelines & Difficulty Tags (Aeonisk Specific)

While YAGS provides general difficulty guidelines, Aeonisk often uses a more focused range and encourages tagging entries for easier reference.

**Aeonisk DC Guidelines:**
- **DC 16 – Moderate:** Standard single-PC tasks in controlled settings (e.g., basic attunement, simple social interaction with a willing Bonded). Subdomain examples: `social_interaction_bonded`, `attunement_basic`.
- **DC 18–20 – Challenging:** Hazardous tasks, actions under pressure, or complex single-PC rituals (e.g., piloting through minor turbulence, a standard Intimacy Ritual, resisting mild Void influence). Subdomain examples: `pilot_check_minor_hazard`, `intimidation_ritual_standard`, `void_resistance_low`.
- **DC 22–24 – Difficult:** High-stakes actions, tasks with heavy interference, or significant group rituals (e.g., complex data decryption under fire, a group ritual to repair a minor leyline fracture, navigating a contested slipstream jump). Subdomain examples: `data_decryption_contested`, `group_ritual_ley_repair_minor`, `pilot_check_slipstream_contested`.
- **DC 26+ – Extreme:** Epic tasks, multi-stage operations, or rituals dealing with wild Void or profound metaphysical forces (e.g., severing a deeply ingrained Sovereign Nexus Bond, a large group ritual to close a Void breach, piloting through a collapsing Void tunnel). Subdomain examples: `bond_severance_major`, `group_ritual_void_closure`, `pilot_check_extreme_hazard`.

**Difficulty Tags (Subdomains):**
Tag each significant action, item, or rule entry with a concise subdomain tag (e.g., `melee_attack`, `perception_check`, `data_decryption`, `lockdown`, `ritual_snare`, `pilot_check`, `drone_operation`). This helps in indexing, applying specific modifiers, and allows for more granular control by the GM. These tags should be descriptive and consistently applied.

## 7. Void & Soulcredit System (Detailed)

*“Every act is a signature. Every signature leaves a mark.”*

### 7.0. Hybrid Actions, Consumables, and Economy Updates

**Skill + Skill Combos (Hybrid Actions):**
Instead of two separate rolls, allow a single roll using the primary Attribute × Skill. If a second skill logically assists the action, grant a +2 “Synergy” bonus to the roll.
*E.g., Shrike Burst (Dex × Guns) + Ritual Tag (Attunement assisting) → Dex × Guns + d20 +2 Synergy Bonus.*

GM Litmus Test for Synergy bonus: If removing the helper skill makes the stunt nonsense, grant +2. The Synergy Bonus is also used for Group Ritual outcomes.

**Consumable Resource Tracking:**
- **Spark Charges:** Every Spark-based weapon volley or EMP pulse consumes 1 Spark Charge.
- **Attunement Kits:** Each complex ritual (e.g., group rites above DC 22 or any “Ritual Snare”) consumes 1 Attunement Kit or adds +1 Void to the ritual's cost.
- These resources should be tracked explicitly on character sheets. Running out should trigger "out of resources" complications (GM discretion).

**Void & Soulcredit Economy Updates:**
- **Moderate Success Cost:** A Moderate Success on a significant roll (especially rituals or high-stakes actions) still carries a minor cost: the character must choose to either gain +1 Void or spend 1 relevant resource (e.g., a Spark Charge, an Attunement Kit, a minor offering).
- **Critical Failure (Natural 1):** Always inflicts +2 Void. May also auto-break focus or a relevant item (GM discretion based on context).
- **Excellent Success (Margin ≥ 20 on YAGS Degree of Success, or +10 to +14 / +15+ on Ritual Margin Table):** The character may convert a potential Soulcredit reward from this success into –1 Void instead, reflecting perfect ritual economy or karmic balance.

### 7.1. Void Score (0-10)

Measures spiritual corruption, disconnection, and proximity to being Claimed.

**Effects by Score:**

| Score   | State         | Passive Effects / Narrative Tone                             | Specific Mechanics                                           |
| ------- | ------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| 0-2     | Clear         | Grounded, fully functional.                                  | None.                                                        |
| 3-4     | Disturbed     | Dreams distort, rituals may feel slightly off, unease near sacredness. | Minor narrative fluctuations at GM discretion.               |
| **5-6** | **Afflicted** | **Void Environmental Disruption:** Static in air, dream fragments leak, ritual color changes. Ambient instability. | GM applies narrative pressure, minor tech glitches, uneasy feelings in others. *No roll required.* Character feels like "walking corruption." |
| **7-8** | **Severed**   | **Void Environmental Disruption:** Leylines flicker, tech flickers erratically, Bonds shift to Dormant. Increased isolation. | Significant narrative instability. Bonds provide no mechanical benefits. Difficulty forming new connections. |
| **9**   | **Hollowed**  | **Void Environmental Disruption:** Sacred spaces reject you (passive harm/warding), even passive rituals misfire or twist. | Cannot benefit from sacred sites. Rituals highly prone to negative outcomes  (GM applies penalties/tier shifts). Active spiritual repulsion. |
| **10**  | **Claimed**   | **Void Environmental Disruption:** Reality warps visibly around you. **Claimed.** | The Void acts through the character. Potential loss of agency (GM may seize narrative control). |

**Void Spike (New Rule):**
If a character gains **2 or more Void** from a single event (e.g., catastrophic ritual failure + skipping offering), they are **stunned**:

- **Combat:** Lose next turn.
- **Narrative:** Dazed, confused, vulnerable to spiritual intrusion or manipulation.

**Gaining Void:**

| Action                        | Void +   | Notes                                                        |
| ----------------------------- | -------- | ------------------------------------------------------------ |
| Ritual without Offering       | +1       | Per ritual. May also worsen outcome margin.                  |
| Unethical Ritual/Intent       | +1/+2    | Per ritual, GM discretion based on severity.                 |
| Break Guiding Principle               | +3       | Per significant betrayal. Triggers narrative crisis & worsens relevant ritual margins. |
| Sacrifice a Bond for Power    | +1       | Per sacrifice.                                               |
| Use Void-Forged Item/Weapon   | +1-2     | Per significant use (e.g., combat scene, major activation).  |
| Channel/Bind Void Entity      | +2 to +5 | Based on entity power and ritual success/failure.            |
| Perform Forbidden/Void Ritual | Varies   | Based on ritual description and margin outcome. Often +2 to +4 on failure/backlash. |
| Break Sacred Oath/Contract    | +1-3     | Depending on solemnity and consequences.                     |
| Fail Ritual (Margin -5/-10)   | +1 / +2  | As per Margin Outcome Table.                                 |

**Cleansing Void:** Requires sacrifice or reconciliation.

| Method                                         | Void –   | Notes                                                        |
| ---------------------------------------------- | -------- | ------------------------------------------------------------ |
| Cleansing Ritual at Ley Site                   | -1       | Requires significant offering, successful Ritual roll (Solid Success margin or better). |
| Restore a Broken Bond (Genuine Reconciliation) | -1       | Requires RP, possibly ritual. Both parties must agree.       |
| Complete Quest Aligned with Guiding Principle          | -1 to -2 | Must involve significant personal cost/sacrifice. GM call.   |
| Destroy Item Tied to Corruption                | -1       | Item must be significant source/symbol of Void gain. GM call. |
| Sacrifice Something Irreplaceable              | -3       | Truly significant: relic, core memory, power, relationship feature. One time. |

### 7.2. Soulcredit (SC) (–10 to +10)

Measures spiritual reputation, integrity, and trustworthiness within the  metaphysical economy.

**Effects by Score (Optional Social Rules):**

| Score     | Status                 | Social/Factional Effects                                     |
| --------- | ---------------------- | ------------------------------------------------------------ |
| +6 to +10 | Ritually Exalted       | Trusted by sacred factions (Nexus), access to high-tier rituals/tech. Leaders. |
| +1 to +5  | Clean / Reliable       | Generally accepted, standard access.                         |
| 0         | Neutral / Unknown      | Default starting state. No strong opinions either way.       |
| -1 to -5  | Flagged / Unreliable   | Watched by auditors (ACG), limited access, social suspicion. |
| -6 to -9  | Rejected / Debt-Marked | Excluded from sacred spaces/rituals, hunted by debt collectors, pariah status. |
| -10       | Spiritually Bankrupt   | Considered astrally toxic, null. May be targeted for cleansing/containment. |

**Gaining Soulcredit:**

| Action                               | SC + | Notes                                                        |
| ------------------------------------ | ---- | ------------------------------------------------------------ |
| Fulfill Ritual Contract/Oath         | +1   | Formal, witnessed agreements.                                |
| Aid Another's Ritual (with Offering) | +1   | Must contribute meaningfully (energy, offering).             |
| Public Ritual (aligned w/ Bond/Will) | +2   | Must be witnessed, significant, and successful (Solid+ margin). |
| Cleanse Void Site/Person             | +2-3 | Based on severity of Void and risk involved.                 |
| Uphold Faction Tenets (at cost)      | +1   | e.g., Nexus upholding doctrine, ACG enforcing Debt Law fairly. |
| Ritual Success (Strong Resonance+)   | +1   | As per Margin Outcome Table benefit.                         |

**Losing Soulcredit:**

| Action                               | SC – | Notes                                                        |
| ------------------------------------ | ---- | ------------------------------------------------------------ |
| Break Ritual Contract/Oath/Bond      | -2   | Formal, witnessed agreements. Bond breaking also costs Void etc. |
| Ritual Failure due to Negligence     | -1   | If lack of preparation/respect caused failure (GM call).     |
| Refuse/Default on Ritual Debt        | -2   | Especially if formally logged by ACG.                        |
| Betray Declared Guiding Principle            | -3   | Also costs Void.                                             |
| Actions Contradicting Faction Tenets | -1-2 | e.g., Nexus commodifying ritual, ACG forgiving debt without cause. |

Soulcredit is often tracked passively by factions like the Sovereign Nexus and  ACG. It can affect access, pricing, legal standing, and ritual  permissions.

## 8. Bonds, Kinship & Guiding Principle (Detailed)

These systems form the core of character identity and relationships in Aeonisk.

### 8.1. Bonds

*“To act is to bind. To bind is to become.”* Bonds are formal metaphysical contracts, witnessed and recorded, forming the stable units of identity.

**Mechanics Recap:**

- Max 3 (Freeborn: 1).
- Formed via in-game ritual/oath.
- +2 Rituals together.
- +1 Soak defending Bonded.
- Sacrifice: +5 to Willpower roll (once/session), +1 Void, +1 Soul Debt, -1 Emp (scene).
- **Void ≥ 7:** Bonds become Dormant (provide no mechanical benefits).

**Bond Types (Examples):**

| Type       | Description                                                  | Common Consequences                                          |
| ---------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Kinship    | Ancestral, chosen, or ritualized family.                     | Inheritance, duty, shared Soulcredit pool, ritual access.    |
| Ascendancy | Subordination to a higher Will (mentor, House, Faction).     | Amplified power/access via patron, loss of autonomy.         |
| Debt       | Owed spiritual/material obligation. Often ACG brokered.      | Soulcredit drain, ritual marking, compelled service.         |
| Voidward   | Alignment with nullity, taboo forces, often Tempest-related. | Isolation, power spikes, unpredictable Void effects, hunted. |
| Passion    | Intense emotional/creative entanglement (lovers, artistic rivals). | Unstable resonance, feedback loops, potent shared rituals.   |
| Faction    | Formal allegiance to an institution (Nexus, Pantheon, etc.). | Legal protection/obligation, behavioral constraints, access. |

**Bond Status:** Active / Dormant (strained or high Void, no bonuses) / Severed / Void-Locked (Void = 10, potentially corrupted).

### 8.2. Kinship


*“Blood is an echo. Kinship is the structure we build to hear it.”* Kinship is ritual architecture, maintained through oaths, memory, and Faction/Ring matrices. Not purely genetic.

**Kinship Structures:** (Examples) Bloodline Houses, Mnemonic Families, Ritual Pods, Sovereign Families, Fracture Kin.
**Responsibilities of Kin:** Share Soulcredit effects, enact ancestral rites, shelter from Void, intercede in dreamspace, maintain archives.

### 8.3. Bonding Rites


Must be witnessed. The rite itself is often key. Examples: Spiral Vow, Red Thread Tether, Voidcall Sealing, Debtbinding.

### 8.4. Guiding Principle

Your soul's sacred trajectory. A metaphysical path, not a simple goal.

**Mechanics Recap:**

- Starts undefined. Declared during play.
- **Alignment:** Acting *in* alignment grants +1 to *all* Willpower-based rolls.
- **Betrayal:** Acting *against* declared Guiding Principle incurs +3 Void and triggers a narrative/spiritual crisis (GM discretion).
  - 
  - **Ritual Conflict:** Performing a ritual that *directly contradicts* your declared Guiding Principle worsens the margin result by one tier (e.g., a  "Solid Success" becomes a "Weak Success", a "Failed + Backlash" becomes  "Catastrophic Fumble"). This is in addition to the Void gain.

**Discovering Guiding Principle:**  Can happen through visions, extreme stress,  moments of clarity, fulfilling a deep need, or guidance from  mentors/entities. It should feel like a revelation. It often aligns with or conflicts with Factional dogma or Bond obligations, creating story  tension.

## 9. Technology & Equipment

Aeonisk tech is ritually encoded, interacting with Will, Bond, Void, and Soulcredit.

### 9.1. Core Principle: Will Drives Technology

(Unchanged from v1.1.0, but Void Interference reflects new rules)

- **Guiding Principle Resonance:** Tech aligned with Guiding Principle performs better. Using tech *against* Guiding Principle causes glitches, increased Void risk.
- **Soulcredit Gating:** High-end tech may require SC authentication. Low SC can cause jams, lockouts. High SC may unlock features.
- **Ritual-Tethered Systems:** Complex tech may require ritual interfacing, Bonded pilots, offerings.
- **Void Interference:** At Void ≥ 5, the **Void Environmental Disruption** (Sec 7.1) can cause tech to glitch, jam, hallucinate targets, invert  function, or become susceptible to spiritual corruption/possession based on the severity of the Void score and narrative context.

### 9.2. Weapon Classes


Bonded, Glyph-Encoded, Void-Infused (+1 Void on use), Spirit-Weave, Contractual.

**Example Techno-Weapons:** 
Mnemonic Blade, Shrike Cannon, Ash Pulse Pike (+2 Void on crit), Compact Drone Halo, Debtbreaker Sidearm.

### 9.3. Aeonisk Currency System (Detailed)

*“You don't trade money. You transfer charged energy.”*

---

#### Core Principles

No abstract "coins" or "notes." Every transaction moves elemental charge stored in **talismans**. Spending siphons energy **to** the recipient or ritual, not **from** the item itself. Empty talismans can be **recharged** at leylines or **sacrificed** in a ritual to permanently release their remaining potential.

---

#### The Six Currency Types

| Talisman   | Element | Meaning                         | Common Uses                                                             |
| ---------- | ------- | ------------------------------- | ----------------------------------------------------------------------- |
| **Grain**  | Earth   | Stability, structure, grounding | Trade goods, housing, crafting, defensive wards                         |
| **Drip**   | Water   | Emotion, secrecy, flow, healing | Safe passage, information brokering, healing rites                      |
| **Spark**  | Fire    | Action, force, urgency, will    | Combat power, machinery, offense rituals                                |
| **Breath** | Air     | Thought, communication, change  | Messaging services, performance rites, insight divination               |
| **Hollow** | Void    | Corruption, erasure, nullity    | **Forbidden.** Black-market energy, dark Void rituals                   |
| **Seed**   | None    | Raw potential, unaligned will   | **Untradeable.** Must be ritually attuned to become a standard talisman |

---

**GM Tip—Local Rates:** Typical markets peg 1 Spark ≈ 2–5 Drips per session; high-security hubs (e.g., Aeonisk Prime) slide it closer to 1 Spark = 3 Drips, while frontier bazaars might only honor 1 Spark = 2 Drips.  

---

#### Talisman Sizes & Capacity

| Size       | Capacity Range | Physical Form              |
| ---------- | -------------- | -------------------------- |
| **Single** | 1 unit         | Coin-like shard or pebble  |
| **Band**   | 10–99          | Ring, bracelet, simple bar |
| **Sigil**  | 100–999        | Engraved medallion or disk |
| **Core**   | 1,000–9,999    | Crystal orb or power cell  |
| **Vault**  | 10,000+        | Sealed reliquary or device |

---

#### Hollows & Seeds

* **Hollows:** When an **attuned Seed** degrades or is forcibly torn open, it becomes a Hollow Shard. Possession or use **raises your Void Score** (typically +1 per shard). Hollows are outlawed in Nexus jurisdictions and trafficked by Tempest syndicates; they may **corrupt** nearby talismans if stored together.
* **Seeds:** Freshly harvested from leyline growths, Raw Seeds contain unshaped elemental potential. They **cannot** be traded or used until **attuned** via a ritual that includes a vow, a proper offering (often a smaller talisman sacrifice), and a consecration rite. **Failed attunements** risk producing a Hollow Echo—an unstable fragment that counts as both Seed and Hollow.

---

#### Quick Notes

* **No fixed "exchange rate":** All talismans trade energy → energy, but local markets set rates dynamically.

* **Attunement required:** Only attuned Seeds (Spark, Drip, Grain, Breath) function as stable currency.

* **Raw vs Hollow:** Raw Seeds must be attuned before use; unattended, they degrade into Hollows (black-market energy, high risk).

* **GM fiat:** Feel free to reflavor or adjust relative scarcity per node or story beats—the toolkit above simply lets everyone speak the same "currency language."

#### Soulcredit Interaction

High-value exchanges—access to elite markets, prestigious spell-forges, or faction-run infrastructure—often demand a **minimum Soulcredit** score. Equally, overtly exploitative trades (bribes, coercion of spirits) carry the risk of **Soulcredit loss**, as word of unethical dealings spreads through astral and social channels.

---

## 10. Factions & Culture

Power aligns with philosophy, not geography.

*(See Appendix 1 for full Faction details, including Tenets and Mechanical Notes)*

- **Sovereign Nexus:** Theocratic matriarchy. Order, ritual, hierarchy. Regulates magick, cleanses Void.
- **Astral Commerce Group (ACG):** Financial entity. Tracks/brokers Soulcredit, contracts, ritual debt. Law is literal.
- **Pantheon Security:** Privatized tactical force. Loyalty, procedure. Militarized ritual, Void containment.
- **Aether Dynamics:** Ecological-spiritual balance. Leylines, harmony, symbiosis. Fluid ritual, attuned tech.
- **Arcane Genetics:** Biotech/ritual fusion. Evolution, coded spirituality. Fleshcrafting, programmable purity.
- **Tempest Industries:** Subversive syndicate. Stolen tech, forbidden ritual, Void tools. Power through control.
- **Freeborn / Unbound:** Outside faction structure. Rare, mistrusted/feared. Scarce Bonds, truth over power.

## 11. World Lore

### 11.1. History Synopsis

Aeonisk's dominant species evolved from bonobo ancestors, retaining some emphasis on intimacy but developing complex, matriarchal societies. They  harnessed technology, underwent an Age of Enlightenment, and eventually  unified under the matriarch Aurora (~1500 years ago) who formed the **Sovereign Nexus** to ensure peace through centralized authority and technological/astral  advancement. Interstellar travel led to colonization (Arcadia, Elysium,  Nimbus). The Nexus maintains stability but faces whispers of dissent and hidden agendas.

### 11.2. The Aeons

Metaphysical currents shaping reality, not just time periods.

- **First Aeon (First Sovereignty, ~6000-1200 BR):** Age of Towers. Defined Will through form, structure, pattern, naming.  Key Tech: Celestial harmonics, ritual metalwork, codified lineage.  Events: Treaty of Ten Provinces, Project of Names, Harmonium War. *Outsiders:* Siblings of the Black Horizon (embraced Void).
- **Second Aeon (Aeon of Weaving, ~1200 BR - 0 BR):** Root Aeon. Focused on connection, continuity, intuition, remembrance.  Matriarchal, recursive. Law was sung. Key Tech: Fleshcrafting, astral  convergence, memory-weaving. Structure: Covenant Rings (Kinship, Dream,  Descent). Events: Rites of Recovery, Founding of Rings, Subduction Wars, Spiral Reconciliation.
- **Third Aeon (Sovereign Aeon, 0 AR - Present ~683 AR):** Present Aeon. Awakening of individual sovereignty, codified  consequence, metaphysical economy (Soulcredit). Will as Law, Choice as  Sacrament, Debt as Reflection. Key Tech: Soulcredit economy, ritual AI  arbitration, biotech under oath, astral infrastructure. *Periods:* Early (Nexus rises, SC quantified), Middle (Fracture Cults, Ritual  Standardization Act, Eye of Breach AI), Late (Bond status key, Void  Accord Crisis, prophecy returns).

### 11.3. Liturgical Calendar (Abbreviated)

- **High Rites:** Equinoxes/Solstices (Breath, Flame, Grain, Drip) - Public rituals.
- **Feasts of Passage:** Life (birth/naming), Fire (male puberty), Water (female puberty), Death.
- **Civic Festivals:** Ledger Day (ACG), Bondlight (Nexus), Ash Resonance (Aether), Maskfire (Pantheon/Freeborn), Seedmoon (Wild).

*(See Appendix 3 for full Calendar details).*

### 11.4. Daily Life & Culture

Life is stratified by Faction and Soulcredit. Ritual is part of  infrastructure (leyline regulators). Currency is tangible energy. Bonds  strain and mend. Void is a present danger. Celebrations range from  sanctioned Ritual Raves to underground Void Parties and domestic  Bond-Nights. Intoxicants are elemental and symbolic (Breathwine, Spark  Dust, Dripmist, Void Nectar). Kinship is ritualized, not just genetic.


## 12. GM Toolkit

### 12.1. Ritual Fallout and Void Intrusion

Mechanics for both are fully resolved via the Margin Outcome Table in §6.1. For all narrative hooks and evocative description, refer to §6.2 “Ritual Outcome Consequences.”

### 12.2. Contract Hooks & Debt Encounters

- **Hooks:** Lost Ledger, Echo Clause, Debt Transfer.
- **Encounters:** The Auditor, The Bonebird, The Void Broker.

### 12.3. Bond Conflict Mechanics

- **Triggers:** Acting against Bond, Void ≥ 7, secret sacrifice, ritual failure backlash.
- **Resolution:** Prompt RP scene. Unresolved = Bond becomes Dormant.

### 12.4. Mission Generator (Roll 1d6 Twice)


| d6   | Goal                                                         | d6   | Twist                                                     |
| ---- | ------------------------------------------------------------ | ---- | --------------------------------------------------------- |
| 1    | Sever a cursed/Voided Bond                                   | 1    | Target is Bonded to a PC                                  |
| 2    | Recover a stolen Primary Ritual Item                         | 2    | Ritual must occur during dangerous ley pulse/storm        |
| 3    | Enforce/Break a spiritually binding contract (ACG/Nexus)     | 3    | Rival Faction interferes with contradictory goals         |
| 4    | Cleanse a Void-corrupted ley site/person                     | 4    | Void entity offers aid... for a price                     |
| 5    | Smuggle a Void-afflicted oracle/relic out of Faction control | 5    | The sacred site/relic is sentient and resists             |
| 6    | Protect/Guide someone whose Guiding Principle is awakening           | 6    | Success directly conflicts with a PC's declared Guiding Principle |

------

## Appendix 1: Faction Details



- **Sovereign Nexus:** (+1 Wil/Int). Indoctrinated (+2 vs ritual disruption). Govern via  ritual, hierarchy. Bonds registered. Magick regulated. Void = unclean.
- **Astral Commerce Group (ACG):** (+1 Int/Emp). Contract-Bound (+1 SC or favor owed *to* PC). Debt is structure. SC is value. Contracts litigated. Void = risk/investment.
- **Pantheon Security:** (+1 Str/Agi). Tactical Protocol (Auto-win 1 initiative/day). Honor=function. Militarized ritual. Void = active threat.
- **Aether Dynamics:** (+1 Emp/Per). Ley Sense (Sense lines). Harmony=health. Fluid ritual. Tech attuned. Void = imbalance.
- **Arcane Genetics:** (+1 Hea/Dex). Bio-Stabilized (+2 vs bio-Void/mutation). Ritual embodied/coded. Bonds enhanced. Void = potential mutation.
- **Tempest Industries:** (+1 Dex/Per). Disruptor (+2 sabotage rituals/tech). Subversive. Rituals hacked. Bonds strategic/expendable. Void = tool/status.
- **Freeborn / Unbound:** (+1 Any Three). Wild Will (1 Bond max). Outside structure. Bonds sacred/scarce. Void understood. Truth > Power.

## Appendix 2: Ritual Library & Card Template

*(Use the 12 rituals listed in Section 6.5 as a starting point to create your own)*

**Ritual Card Template:**

```
RITUAL NAME: ______________________
TIER: □ Minor □ Standard □ Major □ Forbidden
THRESHOLD: ____

RITUAL EFFECT (Describe effect at Solid Success [+5 margin]):
____________________________________________________________
____________________________________________________________
____________________________________________________________

OFFERING REQUIRED:
____________________________________________________________

MARGIN OUTCOMES (Brief summary, refer to core rules):
*   -10+: Catastrophe (+2 Void, Fallout)
*   -5/-9: Fail + Backlash (+1 Void, Strain)
*   -1/-4: Fail (Fatigue/Confuse)
*   0/+4: Weak Success (Side effects/Reduced)
*   +5/+9: Solid Success (Full effect)
*   +10/+14: Strong Resonance (Minor benefit)
*   +15+: Breakthrough (Exceptional)

VOID RISK (Base): □ None □ +1 □ +2 (Forbidden usually higher)
BOND REQUIRED? □ Yes □ Optional □ No

FACTION VARIANTS / NOTES:
____________________________________________________________
    
```

## Appendix 3: Glossary of Aeonic Terminology

- **Abyss:** The existential gulf between the formed self and ultimate Will.
- **Aeon:** Metaphysical current shaping reality. Not time, but awakening.
- **AR/BR:** After/Before Reconciliation (Year 0). Standard time notation.
- **Bond:** Formal metaphysical alignment/contract. Real and binding.
- **Codex Nexum:** Governing legal-mnemonic text of the Nexus.
- **Covenant Rings:** Second Aeon structure (Kinship, Dream, Descent).
- **Cycle:** A period of 7 days, a week.
- **Eye of Breach:** Unsanctioned AI that mirrors the Codex Nexum. Active on Nimbus and Hollow Vector.
- **Hollow:** An emptied shell—Bond or Seed drained of intent, now unstable energy.
- **Fleshcrafting:** Ritual-biological art of reshaping form via lineage/memory.
- **Freeborn:** Person outside of factions, unbound.
- **Ritual Consequence:** All action generates metaphysical reaction. Outcome now determined by margin of success/failure.
- **Soulcredit:** Spiritual economy of Third Aeon. Tracks debt/merit. Real/enforced.
- **Sovereign Nexus:** Dominant Third Aeon technocratic/spiritual infrastructure.
- **Guiding Principle:** Soul's sacred trajectory. Alignment empowers, betrayal corrupts (+3 Void, worsens conflicting ritual margins).
- **Veil:** Membrane between mundane reality and the Astral. Crossing = projection, scrying, trance.
- **Void:** A tracked score (0–10) reflecting spiritual disconnection. Now  passively warps reality around you at 5+. Gaining 2+ Void at once causes a Void Spike.
- **Void Spike:** A stun/daze condition triggered when 2+ Void is gained from a single  event. Causes loss of next turn (combat) or vulnerability (narrative).
- **Raw Seed:** An unstable, unaligned Seed. Degrades in 7 cycles. Using a Raw Seed directly in gear or for potent effects without proper ritual attunement incurs +1 Void.
- **Attuned Seed:** A Raw Seed that has undergone a ritual attunement process, aligning it to a specific elemental aspect (e.g., Spark, Drip, Breath, Grain). Elementally Attuned Seeds are stable and required for certain specialized gear and advanced talismans. The process of attunement transforms the Seed's nature from raw/unstable to elementally aligned/stable.

## License

Distributed under the GPL v2 as described by Samuel Penn, the creator of Yet Another Game System (YAGS).

### Yet Another Game System

By Samuel Penn (sam@glendale.org.uk) and Aeonisk customization completed by Three Rivers AI Nexus.

Aeonisk YAGS Module is free content: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This content is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
