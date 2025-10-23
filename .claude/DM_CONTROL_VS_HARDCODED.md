# Aeonisk YAGS Multi-Agent System: DM-Controlled vs Hardcoded Analysis

## Executive Summary

The Aeonisk multi-agent system has a **hybrid architecture** where:
- **Core mechanics and formulas are hardcoded** (dice, attributes, skills, damage calculation, difficulty scaling)
- **DM narration and adjudication are AI-driven** (LLM-generated, narrative-based)
- **Story/scenario content is mostly AI-generated** with some hardcoded templates
- **Combat and enemy AI are hybrid** (templates hardcoded, tactics LLM-driven, spawn locations DM-narrated)

---

## Part 1: HARDCODED/STATIC SYSTEMS

### 1.1 Core Game Mechanics (mechanics.py)

#### Difficulty Class (DC) System - FULLY HARDCODED
```
Difficulty Enum (canonical YAGS):
- TRIVIAL = 10
- EASY = 15
- ROUTINE = 18 (default combat, pressured checks)
- MODERATE = 20 (uncertain outcomes)
- CHALLENGING = 22 (requires focus)
- DIFFICULT = 26 (extreme, multi-stage)
- VERY_DIFFICULT = 30 (desperate)
- FORMIDABLE = 35 (nearly impossible)
- LEGENDARY = 40 (exceptional circumstances)

Dynamic Adjustments:
- Base DC by action_type: combat(18), social(18), sensing(20), technical(20)
- Ritual actions: +4 to base DC (always Challenging minimum = 22)
- Scene void level 4-6: +2 to DC
- Scene void level 7+: +4 to DC
```
**Classification: HARDCODED** - This is canonical Aeonisk YAGS rules, not DM decision

#### Action Resolution Formula - FULLY HARDCODED
```
Roll d20 (1-20)

SKILLED ACTION:
  Ability = Attribute × Skill
  Total = Ability + d20
  Example: Strength(3) × Combat(5) + d20 = 15 + d20

UNSKILLED ACTION:
  Ability = Attribute - 5
  Total = Attribute + d20 - 5
  Example: Strength(3) + d20 - 5 = -2 + d20

MARGIN = Total - Difficulty

OUTCOME TIER (based on margin):
- Critical Failure: margin ≤ -20
- Failure: margin < 0
- Marginal: 0-4
- Moderate: 5-9
- Good: 10-14
- Excellent: 15-19
- Exceptional: 20+
```
**Classification: HARDCODED** - YAGS core mechanic, non-negotiable

#### Outcome Tier System - HARDCODED
Seven-tier quality system determines narrative quality and mechanical benefits/costs. DM uses these tiers to narrate the quality of success or failure, but the tiers themselves are fixed.

### 1.2 Void Corruption System (mechanics.py)

#### Void Scoring Caps - HARDCODED
```
Per-action cap: Max +1 void
Per-round cap: Max +2 void per character
Per-scene cap: Max +3 void automatic (Codex Nexum canonical)

High-risk rituals can opt-in to bypass scene cap
Character dissolution: Void ≥ 10 (automatic defeat)

Void Corruption Levels (descriptive):
- 0: Pure
- 1-2: Touched
- 3-4: Shadowed
- 5-6: Corrupted
- 7-8: Consumed
- 9+: Lost to Void
```
**Classification: HARDCODED** - Core progression system

#### Void Trigger Keywords - PARTIALLY HARDCODED
```python
void_triggers = {
    'void_exposure': 1,
    'ritual_shortcut': 1,
    'bond_betrayal': 2,
    'void_manipulation': 1,
    'corrupted_tech': 1,
}
```
These triggers are checked automatically, but the **DM's narration** determines what triggers apply (via outcome_parser.py parsing narrative for keywords).

### 1.3 Skill Mapping System (skill_mapping.py)

#### Skill Aliases - HARDCODED MAPPING
```
Social Skills:
  charm, social, persuasion, empathy → "Charm"
  guile, deception → "Guile"

Combat Skills:
  combat, melee, brawl, guns → respective skills

Investigation:
  investigation, investigation, perception, search → "Awareness"

Rituals:
  astral arts, ritual, attunement → "Astral Arts"
  MUST use Willpower (enforced by validate_ritual_mechanics)

Technical:
  tech, craft, tech/craft, technology → "Tech/Craft"
  drone operation, pilot → respective skills
```
**Classification: HARDCODED** - Player LLM agents use these to normalize skill names

#### Ritual Mechanics Validation - HARDCODED RULES
```python
def validate_ritual_mechanics(action_type, attribute, skill):
    """Enforce ritual mechanics rules with proper skill routing."""
    
    if action_type == 'ritual':
        if skill == 'Intimacy Ritual':
            return (Willpower, Intimacy Ritual)
        elif skill == 'Magick Theory':
            return (attribute, skill)  # Investigation of rituals OK
        else:
            # All other rituals: MUST use Willpower + Astral Arts
            return (Willpower, Astral Arts)
    
    return (attribute, skill)
```
**Classification: HARDCODED** - Cannot be overridden by DM

### 1.4 Soulcredit System (mechanics.py)

#### Soulcredit Gain Triggers - HARDCODED KEYWORDS
```
+1: Fulfill contract/oath (success required)
+1: Aid another's ritual with offering
+2-3: Void cleansing ritual (3 if margin 10+, else 2)
+2: Public ritual aligned with principles (margin 5+)
+1: Uphold faction tenets at personal cost
+1: Ritual success with strong resonance (margin 10+)
```

#### Soulcredit Loss Triggers - HARDCODED KEYWORDS
```
-2: Break ritual contract/oath/bond
-2: Refuse/default on ritual debt
-3: Betray declared guiding principle
-2: Actions contradicting faction tenets
-1: Ritual failure from negligence
```

These are **keyword-based** and checked via outcome_parser by parsing DM narration, but the **values are hardcoded**.

**Classification: HARDCODED** - The delta values and trigger conditions are canonical

### 1.5 Attributes & Skills System

#### Standard Attributes (YAGS Canonical) - HARDCODED
```
Primary Attributes:
- Strength, Agility, Endurance, Perception
- Intelligence, Empathy, Willpower, Charisma, Size

Attribute Range: Typically 1-5 (humans)
- 1: Below average
- 2-3: Average
- 4: Above average
- 5: Exceptional
- 6+: Superhuman (rare)

Health Calculation: Health = Size × 2 (hardcoded)
```
**Classification: HARDCODED** - YAGS core, read from character config

#### Core Skills - HARDCODED DEFINITIONS
Skill list is canonical to YAGS, though actual skill values come from character config.

### 1.6 Combat Mechanics (enemy_templates.py)

#### Enemy Templates - HARDCODED STAT BLOCKS
```
grunt: 15 HP, standard attributes (3-4), skill 3-4
elite: 25 HP, boosted attributes (4-5), skill 4-5
sniper: 20 HP, high perception, ranged focus
boss: 40 HP, high willpower/attributes, adaptive tactics
enforcer: 30 HP, high strength, intimidation
ambusher: 18 HP, high agility/stealth, ambush tactics
```

**Classification: HARDCODED** - Template definitions are static

#### Weapon Library - HARDCODED STATS
```
Each weapon (pistol, rifle, sniper rifle, etc.) has:
- Skill requirement (Guns, Melee, Brawl, etc.)
- Attack/Defence modifiers
- Damage values
- Damage type (wound, stun, mixed)
- Range increments (for ranged)
- Rate of fire
- Special properties (void_corrupted, armor_piercing, suppress, etc.)

Example - Pistol:
  skill: Guns
  damage: 4
  load: 1 (encumbrance)
  range: 5/10/20 (short/medium/long)
  rof: 2 (rate of fire)
  capacity: 15 rounds
```

**Classification: HARDCODED** - Weapon stat blocks are canonical YAGS

#### Armor Library - HARDCODED SOAK VALUES
```
Each armor provides:
- Coverage (partial/full)
- Soak reduction (2-6 points)
- Load/encumbrance penalty
- Special properties

Example - Tactical Vest:
  soak: 3
  load: 2
  coverage: torso + arms
```

**Classification: HARDCODED** - Static armor definitions

#### Position System - HARDCODED RANGES
```
Engaged: 0-5m (melee range, direct contact)
Near-Enemy: 5-25m (short range, tactical distance)
Far-Enemy: 25-50m (rifle range)
Extreme-Enemy: 50m+ (sniper/artillery range)

Each position determines:
- Melee attack feasibility
- Ranged attack penalties
- Visibility/detection difficulty
```

**Classification: HARDCODED** - Position range definitions are static

#### Damage Calculation - HARDCODED FORMULAS
```
DAMAGE = Strength + Weapon Damage - Soak

Wounds Conversion (YAGS):
  Every 5 damage = 1 wound
  Character defeated when Health ≤ 0

Example:
  Strength 4 + Pistol(4) - Enemy soak(2) = 6 damage
  6 damage / 5 = 1 wound inflicted on enemy
```

**Classification: HARDCODED** - Core YAGS combat math

---

## Part 2: DM-CONTROLLED (AI-DRIVEN) SYSTEMS

### 2.1 Scenario Generation

#### Dynamic Scenario Generation - DM-CONTROLLED
The DM LLM generates complete scenarios with:
```
Theme: DM-generated or template-selected
Location: DM-generated (with guidance to use canonical locations)
Situation: DM-generated (2-4 sentences)
Void Level: DM-generated (0-10 scale, suggested 2-4 for most)
Clocks: DM-generated with semantic metadata
- Each clock has: name, max, description, advance_means, regress_means, filled_consequence
```

**Classification: DM-CONTROLLED** - Generated via LLM prompt to DM agent

#### Scenario Templates - PARTIALLY HARDCODED
The system includes **hardcoded fallback templates** for:
- Vendor-gated scenarios (6 templates with required purchases)
- Combat scenarios (12 templates with enemy spawns)
- General scenarios (can be LLM-generated)

**Vendor-Gated Template Example:**
```python
{
    'theme': 'Locked Tech Gate',
    'location': 'Sealed Research Facility (Arcadia)',
    'situation': 'The facility requires a Scrambled ID Chip...',
    'void_level': 3,
    'required_purchase': 'Scrambled ID Chip',
    'clocks': [
        ('Security Lockdown', 6, '...'),
        ('Data Extraction', 6, '...'),
        ('Rival Team', 5, '...')
    ]
}
```

**Classification: HYBRID**
- Templates themselves are hardcoded
- DM can override via LLM generation
- When force_vendor_gate=true or force_combat=true, templates are used
- Otherwise, DM generates via LLM

#### Scene Clocks - DM-GENERATED SEMANTICS
When DM generates a scenario, each clock gets semantic metadata:
```
advance_means: "What it means when clock advances" (DM provides)
regress_means: "What it means when clock regresses" (DM provides)
filled_consequence: "What happens when clock fills" (DM provides)
  - Can include [SPAWN_ENEMY: ...] for mechanical clocks
  - Can include [PIVOT_SCENARIO: ...] for narrative clocks
```

**Classification: DM-CONTROLLED** - DM's narration determines clock semantics

### 2.2 Adjudication & Action Resolution

#### Difficulty Calculation - HYBRID
```
DC Base by action_type (hardcoded):
  combat: 18
  social: 18
  sensing/investigation: 20
  technical: 20

DC Adjustments (hardcoded):
  + void_level_pressure (based on scene void)
  + ritual penalty (+4 if ritual)

Result used by DM (hardcoded formula)
```

**Classification: HYBRID**
- Base DCs are hardcoded
- DM can suggest custom DCs in narration
- But the core calculate_dc() function returns a hardcoded value

#### Narration Generation - DM-CONTROLLED
After mechanical resolution, DM LLM generates narrative description:
```
Input: 
  - Player's declared intent
  - Action type/description
  - Mechanical roll result
  - Outcome tier (Failure/Marginal/Moderate/Good/Excellent/Exceptional)

DM LLM Response:
  - 2-3 paragraph cinematic narration
  - Describes consequences
  - References clocks, void, enemies, etc.
```

**Classification: DM-CONTROLLED** - LLM generates narrative freely

#### Outcome Parsing - HYBRID PARSING
After narration, outcome_parser.py extracts mechanical consequences:
```python
def parse_state_changes(narration, action, resolution, active_clocks):
    """Extract clocks, void, soulcredit from DM narration."""
    
    # Extract explicit markers (DM can include these):
    # 📊 Evidence Collection: +2 (found documentation)
    # ⚫ Void: +1 (exposed to corruption)
    # ⚖️ Soulcredit: -1 (questionable ethics)
    
    # If no explicit markers, use pattern matching:
    # Look for keywords in narration (void, danger, progress, etc.)
    # Categorize active clocks by themes
    # Auto-advance clocks based on patterns
```

**Classification: HYBRID**
- If DM includes explicit markers, those are used (DM-controlled)
- If DM forgets markers, automatic parsing attempts to extract (semi-hardcoded)
- Pattern matching for clock keywords is hardcoded

### 2.3 Round Synthesis

#### Synthesis Generation - DM-CONTROLLED
```
Input:
  - All individual action resolutions
  - Current clock states
  - Filled clocks (mandatory consequences)
  - Expired clocks
  - Void/soulcredit changes

DM LLM Task:
  "Write cohesive narrative (1-2 paragraphs) describing what happened.
   Consider timing (initiative), interactions, conflicts, cause & effect.
   MANDATORY: If clocks filled, describe consequences.
   MANDATORY: If using enemy spawn markers, include them in narration."

Output:
  - Narrative synthesis (free text, DM creative choice)
  - Can include [SPAWN_ENEMY: ...], [PIVOT_SCENARIO: ...] markers
```

**Classification: DM-CONTROLLED** - Creative narration with mandatory constraints

#### Constraint Enforcement on Synthesis - HYBRID
```
Hard Requirements (enforced):
  1. If clock filled with [SPAWN_ENEMY: ...] consequence, 
     DM MUST include that marker in narration
  2. If narrative clock filled, DM MUST use scenario marker:
     - [PIVOT_SCENARIO: ...] (theme change, same location)
     - [ADVANCE_STORY: ...] (objective complete, new scene)
     - [NEW_CLOCK: ...] (new pressure/opportunity)
  3. If [DESPAWN_ENEMY: ...] in filled consequence,
     that enemy is auto-removed

Guidance (in prompt, not enforced):
  - "Show how actions interacted"
  - "Reflect growing desperation if failing"
  - "Be vivid and cinematic"
```

**Classification: DM-CONTROLLED WITH CONSTRAINTS**
- Narrative is creative
- Mechanical markers are optional guidance
- If DM includes them, game processes them
- If DM forgets, automatic parsing tries to extract

### 2.4 Enemy AI & Combat

#### Enemy Agent System - HYBRID

**Enemy Spawning (triggered by DM):**
```
DM Narration includes: [SPAWN_ENEMY: name | template | count | position | tactics]

Game processing:
1. Parse marker from narration
2. Load template (hardcoded)
3. Create EnemyAgent instance
4. Set initial position/tactics (from marker)
5. Add to combat turn order
```

**Classification: DM-TRIGGERS** 
- DM decides when to spawn (via narration marker)
- Template and count are DM's choice
- Position and tactics are DM's choice

**Enemy Declaration Phase - HYBRID**
```
Each round, enemy agents:
1. Generate tactical prompt (hardcoded template-based)
2. Receive LLM call to decide next action:
   - Major action (Attack, Move, Buff, etc.)
   - Minor action (Move, Item use, etc.)
   - Defense token (against specific PC)
   - Shared intel (communicate with other enemies)
   
3. LLM decides tactic dynamically based on:
   - Combat situation (enemy health, ally status, ranges)
   - Battlefield layout (positions, cover)
   - Allies nearby (grouping behavior)
   - Player actions last round
```

**Classification: AI-DRIVEN (Hybrid)**
- Tactical prompts are templates (semi-hardcoded)
- LLM generates actual decisions (AI-driven)
- Templates guide behavior but don't dictate it

**Enemy Action Resolution:**
```
Enemy action goes through same mechanics as player actions:
1. Calculate DC (hardcoded formula)
2. Roll (hardcoded 1-20)
3. Resolve (hardcoded mechanics)
4. DM narrates outcome
5. Apply consequences

BUT: Enemy combat attacks have FULL breakdown:
  damage = {
    strength: enemy.strength
    weapon_dmg: weapon.damage_value
    d20: roll_result
    total: strength + weapon_dmg + roll
    soak: pc_armor_soak
    dealt: total - soak
  }

Player attacks have SIMPLIFIED logging:
  damage = {
    base_damage: inferred_from_narration
    soak: armor_value
    dealt: base_damage - soak
  }
```

**Classification: HARDCODED MECHANICS**
- Both enemy and player use same dice/math
- But enemy stats are fully known/tracked
- Player stats are inferred from narration (asymmetric)

### 2.5 Clocks & Consequences

#### Clock Creation - DM-CONTROLLED
DM creates clocks with semantic metadata:
```
create_scene_clock(
    name: str,           # DM provides
    maximum: int,        # DM provides (typically 4-10)
    description: str,    # DM provides
    advance_means: str,  # DM explains (e.g., "threat escalates")
    regress_means: str,  # DM explains (e.g., "danger reduced")
    filled_consequence: str  # DM provides (e.g., "something bad happens")
)
```

**Classification: DM-CONTROLLED** - Complete creative control

#### Clock Advancement - HYBRID
```
Method 1: Explicit DM markers in narration
  "📊 Evidence Collection: +2 (found documentation)"
  → Parsed by outcome_parser, applied directly

Method 2: Automatic pattern matching
  DM narration includes keyword "evidence"
  → outcome_parser categorizes clock as "investigation_clock"
  → If action succeeded, auto-advance by 1
  → If action failed, auto-regress by 1

Method 3: Queue system (batch application)
  To prevent cascade fills, clock updates are queued
  → Applied during synthesis phase
  → All queued updates processed together
  → Prevents multiple fills in one round
```

**Classification: HYBRID**
- DM can explicitly mark with 📊 emoji (conscious control)
- OR automatic parsing attempts to infer (semi-hardcoded)
- Batch application prevents cascades (hardcoded safety feature)

#### Clock Expiration - HARDCODED RULES
```
Timeout: Clock expires after timeout_rounds (auto-calculated)
  Small clocks (max ≤ 4): 4 rounds
  Medium clocks (max 5-6): 6 rounds
  Large clocks (max 7-8): 7 rounds
  Very large clocks (max 9+): 8 rounds

Expiration behavior:
  if clock.filled:
    → "force_resolve": Trigger consequences, then remove
  elif clock.current < max * 0.5:
    → "crisis_averted": Opportunity lost, threat passed
  else:
    → "escalate": Stalemate breaks, situation must resolve

DM sees expired clock warnings in synthesis prompt:
  "⏰ **Evidence Collection** (was 4/8) - CRISIS AVERTED
   The investigation window closed without resolution."
```

**Classification: HARDCODED** - Expiration rules are automatic/canonical

#### Filled Clock Consequences - HYBRID
When clock fills, DM sees filled consequence in synthesis prompt:
```
If filled_consequence contains [SPAWN_ENEMY: ...]:
  → Mechanical clock
  → DM includes marker in narration
  → Game auto-spawns enemy

If filled_consequence contains [PIVOT_SCENARIO: ...]:
  → Narrative clock
  → DM uses scenario marker to change theme
  → Same location, different situation

If filled_consequence contains [NEW_CLOCK: ...]:
  → Escalation clock
  → DM narrates new pressure emerging
  → Game creates new clock from marker

If filled_consequence has no markers:
  → DM must use a marker OR stall
  → System warns: "Narrative clock that fill WITHOUT scenario marker stall the story!"
```

**Classification: DM-CONTROLLED WITH SYSTEM SAFETY**
- DM controls narrative and marker usage
- System enforces consequences for filled clocks
- System auto-parses and applies markers

---

## Part 3: CONFIGURATION & CUSTOMIZATION

### 3.1 Session Configuration (session_config_*.json)

#### Hardcoded vs Customizable Elements
```json
{
  "session_name": "combat_scenario_test",          // DM choice
  "max_turns": 3,                                   // DM choice
  "party_size": 2,                                  // DM choice (randomly selects)
  "output_dir": "./multiagent_output",              // System default
  "enable_human_interface": true,                   // DM choice
  "force_combat": true,                             // DM choice (hardcoded scenarios)
  "force_vendor_gate": false,                       // DM choice (hardcoded scenarios)
  "vendor_spawn_frequency": 2,                      // DM choice (fraction)
  
  "tactical_module_enabled": true,                  // System config
  "enemy_agents_enabled": true,                     // System config
  
  "enemy_agent_config": {
    "allow_groups": true,                           // System config
    "max_enemies_per_combat": 20,                   // System config
    "shared_intel_enabled": true,                   // System config
    "auto_execute_reactions": true,                 // System config
    "loot_suggestions_enabled": true,               // System config
    "void_tracking_enabled": true                   // System config
  },
  
  "agents": {
    "dm": { "llm": { ... } },                       // LLM config
    "players": [ { character definitions ... } ]    // Character pool
  }
}
```

#### Character Definitions - CUSTOMIZABLE
```json
{
  "name": "Enforcer Kael Dren",
  "pronouns": "he/him",
  "faction": "Pantheon Security",
  "personality": {
    "riskTolerance": 6,      // 1-10 scale, guides player decisions
    "voidCuriosity": 1,      // 1-10 scale
    "bondPreference": "neutral",
    "ritualConservatism": 9  // 1-10 scale
  },
  "goals": [
    "Investigate void-related crimes",
    "Track down illegal dissolution advocacy",
    "Maintain order through force when necessary"
  ],
  "attributes": {            // Read from config, used in mechanics
    "Strength": 3,
    "Agility": 4,
    // ... etc
  },
  "skills": {                // Read from config, used in mechanics
    "Combat": 5,
    "Investigation": 4,
    // ... etc
  },
  "inventory": {             // Used for vendor interactions
    "union_issue_pistol": 1,
    "riot_carapace": 1,
    // ... etc
  }
}
```

**Classification: CUSTOMIZABLE**
- All player definitions can be changed in config
- Personality traits influence agent LLM prompts
- Attributes/skills fed into mechanics formulas

### 3.2 LLM Models & Prompts

#### DM Prompts - CUSTOMIZABLE TEMPLATES
The DM receives system prompts for:
```
1. Scenario generation
   - Instructions to use canonical lore
   - Faction rules
   - Void level guidance
   - Clock creation requirements

2. Action adjudication
   - Difficulty calculation context
   - Narration tone guidelines
   - State change parsing instructions

3. Round synthesis
   - "Show how actions interacted"
   - "Consider timing and conflicts"
   - "Clock interpretation semantic guidance"
   - "Spawn enemies ONLY when clocks with [SPAWN_ENEMY:] fill"

4. NPC control
   - Vendor interaction scripts
   - Faction dialogue guidance
   - Ethical conflict handling
```

**Classification: CUSTOMIZABLE (but not in current session)**
- Prompts are in code (Python strings)
- Could be externalized to templates
- Currently static for each DM agent type

#### Player Prompts - CUSTOMIZABLE
Player agents receive:
```
1. Character background (from config)
2. Personality traits (from config)
3. Goals and faction info (from config)
4. Current scenario description
5. Previous actions/results
6. Request to declare next action
```

**Classification: CUSTOMIZABLE**
- Character configs drive personality
- Scenario dynamically provided
- Prompts adapt to party composition

---

## Part 4: SUMMARY TABLE

| System | Aspect | Hardcoded/Static | DM-Controlled | Notes |
|--------|--------|------------------|---------------|-------|
| **Dice Mechanics** | Roll, formula, math | ✓ | - | d20, Attr×Skill, margins |
| **Difficulty Classes** | Base DCs by action | ✓ | - | Routine=18, Challenging=22, etc. |
| **Attributes & Skills** | Names, ranges, meanings | ✓ | - | YAGS canonical list |
| **Outcome Tiers** | 7-tier quality system | ✓ | - | Failure through Exceptional |
| **Void Rules** | Caps, corruption levels, triggers | ✓ | - | +1/action, +2/round, +3/scene |
| **Soulcredit** | Gain/loss values, triggers | ✓ | - | +1 to -3 based on actions |
| **Scenario Generation** | Theme, location, situation | - | ✓ | LLM-generated or templated |
| **Scene Clocks** | Names, maximums, semantics | - | ✓ | DM creates with metadata |
| **Narration** | Action descriptions | - | ✓ | LLM generates freely |
| **Clock Advancement** | Automatic pattern matching | ✓ | - | But DM can mark explicitly |
| **Clock Expiration** | Timeout rules, consequences | ✓ | - | Auto-remove after N rounds |
| **Enemy Templates** | Stat blocks, HP, weapons | ✓ | - | Grunt/Elite/Boss, etc. |
| **Enemy Spawning** | When/where to spawn | - | ✓ | DM decides via [SPAWN_ENEMY: ...] |
| **Enemy Tactics** | Tactical decisions | - | ✓ | LLM agents decide each round |
| **Damage Calculation** | Formula: Str + Wpn - Soak | ✓ | - | YAGS core math |
| **Weapon/Armor Stats** | Damage, soak values | ✓ | - | Hardcoded library |
| **Filled Clock Consequences** | Marker processing | ✓ | - | Automatic parsing & spawn |
| **Round Synthesis** | Narrative composition | - | ✓ | DM LLM generates |
| **State Change Parsing** | Extracting mechanical changes | ✓ | - | Keyword-based patterns |

---

## Part 5: KEY DM DECISIONS

### What the DM Controls (AI-driven)
1. **Scenario selection** - Which theme/location/situation (LLM generated or templated)
2. **Scenario details** - Clocks, void level, NPC actions, vendor presence
3. **Narration quality** - How vivid/cinematic the descriptions are
4. **Action adjudication** - Interpreting player intent and narrating outcomes
5. **Enemy spawning** - When to trigger [SPAWN_ENEMY: ...] markers in narration
6. **Clock consequences** - What happens when clocks fill (within semantic guidance)
7. **Narrative pacing** - Synthesis, dramatic timing, tension escalation
8. **Ally/Enemy interactions** - NPC dialogue, faction reactions, social consequences

### What Cannot Be Changed (Hardcoded Rules)
1. **Difficulty scaling** - Formula for DC calculation
2. **Dice mechanics** - d20 roll system, Attr×Skill formula
3. **Outcome tiers** - Success quality levels
4. **Void caps** - Per-action, per-round, per-scene limits
5. **Soulcredit values** - Specific gains/losses per trigger
6. **Enemy stats** - Template definitions, weapons, armor
7. **Damage formula** - Str + Weapon - Soak
8. **Clock expiration** - Automatic removal after timeout
9. **Skill normalization** - Mapping variants to canonical forms

---

## Part 6: HYBRID SYSTEMS (The Interesting Parts)

### 6.1 Difficulty Calculation - HYBRID
```
Hardcoded Base DCs exist: 10, 15, 18, 20, 22, 26, 30, 35, 40
ROUTINE = 18, CHALLENGING = 22, DIFFICULT = 26, etc.

DM Can Influence:
  - Via action_type: combat(18), social(18), sensing(20), technical(20)
  - Via is_ritual: +4 penalty
  - Via scene_void_level: +2 to +4 adjustment
  - Via narration: "This is an extreme task" (LLM interprets action_type)

Result:
  If DM narrates a "challenging ritual under high void",
  mechanics will calculate DC = CHALLENGING(22) + ritual(+4) + void(+4) = 30
  But the individual components are hardcoded.
```

### 6.2 Clock Advancement - HYBRID
```
Method 1: Explicit DM Markers (DM-controlled)
  DM includes: "📊 Evidence Collection: +2 (found documentation)"
  → System parses and applies exactly as marked

Method 2: Automatic Pattern Matching (Hardcoded)
  DM narrates: "The evidence cabinet is unlocked, revealing documents..."
  → outcome_parser identifies "investigation" keywords
  → Categorizes matching clock as "investigation_clock"
  → Auto-advances by 1 tick (hardcoded rule)
  → DM didn't explicitly mark, but system inferred

Method 3: Queue System (Hardcoded Safety)
  Multiple clocks could fill in one round
  → Queues all updates
  → Applies them together during synthesis phase
  → Prevents cascade of consequences
```

### 6.3 Outcome Parsing - HYBRID
```
Hardcoded Keyword Lists:
  danger_keywords = ['danger', 'threat', 'escalation', 'security', ...]
  investigation_keywords = ['investigation', 'evidence', 'discovery', ...]
  corruption_keywords = ['corruption', 'void', 'taint', ...]
  
Dynamic DM Narration:
  DM generates creative narrative describing action outcome
  
Automatic Extraction:
  If DM mentions these keywords, parser auto-advances relevant clocks
  If DM narrates success but doesn't mention progress, no clock advance
  If DM explicitly marks with 📊, those markers override pattern matching

Result:
  DM creative freedom + automatic mechanical consistency
```

### 6.4 Void Triggering - HYBRID
```
Hardcoded Triggers:
  'void_exposure': +1
  'ritual_shortcut': +1
  'bond_betrayal': +2
  'void_manipulation': +1
  'corrupted_tech': +1

DM Narration:
  DM writes: "The ritual backfires - you feel corruption seeping in"
  outcome_parser.parse_void_triggers() searches for keywords
  Finds "ritual" + "backfire" → matches 'ritual_shortcut' pattern
  
DM Optional Markers:
  DM can explicitly mark: "⚫ Void: +2 (exposed to corruption force)"
  outcome_parser finds emoji marker, uses exact value

Result:
  Automatic void tracking if DM doesn't mark
  Or explicit control if DM adds emoji marker
```

---

## Part 7: IMPLICATIONS FOR GAME BALANCE

### What This Means
1. **Core mechanics are fair & consistent** - Dice system, DCs, damage are hardcoded
2. **Narrative is emergent** - DM creates story, not following a script
3. **Mechanical consequences are automatic** - If DM mentions danger, game tracks it
4. **DM has creative freedom within guardrails** - Can narrate freely, but game enforces rules
5. **Scale-free clock system** - DM creates semantically meaningful clocks, game auto-tracks them

### Risk Areas
1. **If DM forgets to spawn enemies** - Mechanical clock will have unfilled consequences
2. **If DM never marks clocks** - Automatic pattern matching may miss nuance
3. **If DM narrates without keywords** - Clocks won't advance unless explicitly marked
4. **If DM ignores void caps** - Game will enforce them (DM can't exceed caps)
5. **If player defeats self-contradictory** - Game can't prevent mechanically invalid outcomes if DM narrates them

### How to Improve
1. **Require DM to use emoji markers** - 📊 for clocks, ⚫ for void, ⚖️ for soulcredit
2. **Add validation layer** - Check if filled clocks have consequences in narration
3. **Add clock constraint** - Warn DM if no clock advancement in 2+ rounds
4. **Profile DM narration** - Track what keywords/markers DM uses, provide feedback
5. **Make pattern matching transparent** - Show DM what clocks were auto-advanced and why

---

## Conclusion

The Aeonisk system achieves a **hybrid balance**:

**Hardcoded:**
- All mathematical formulas (dice, damage, DC)
- All game rules (void caps, soulcredit triggers, skill validation)
- All templates and stat blocks
- Safety features (clock expiration, cascade prevention)

**DM-Controlled:**
- Scenario creation and selection
- Narration quality and cinematic details
- Clock creation and consequence design
- Enemy spawning decisions
- Round synthesis and pacing

**Semi-Automatic (Hybrid):**
- Clock advancement (explicit markers OR pattern matching)
- Void tracking (explicit markers OR keyword detection)
- Outcome parsing (marker-based OR pattern-based)
- Narrative consequences (DM writes, system extracts mechanics)

This allows **maximum narrative flexibility** while maintaining **mechanical consistency** and **balance integrity**.
