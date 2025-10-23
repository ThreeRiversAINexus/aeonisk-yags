# Enemy Agent System - Design Document v1.0

**Status:** Planning Phase - Not Yet Implemented
**Author:** Three Rivers AI Nexus
**Date:** 2025-10-22
**Related:** Aeonisk Tactical Module v1.2.3

---

## Executive Summary

This document specifies the design for autonomous enemy agents in the Aeonisk multi-agent TTRPG system. Enemy agents are AI-controlled combatants that participate in tactical combat using the Tactical Module v1.2.3 rules, make their own decisions via LLM prompts, and integrate with the existing declare/resolve combat flow.

**Key Features:**
- Autonomous AI decision-making (not DM-controlled)
- Group mechanics for scalability
- DM spawn/despawn control
- Full Tactical Module v1.2.3 integration
- Inter-agent tactical communication
- Void tracking and possession mechanics
- Config-gated feature flag

---

## 1. Core Philosophy

### 1.1 Autonomous Decision-Making
Enemy agents are **full AI participants** with their own LLM-driven decision making. They are NOT puppets controlled by the DM. The DM spawns/despawns them and sets their initial parameters, but they make their own tactical choices during combat.

### 1.2 Tactical Focus
Enemy prompts emphasize **tactical doctrine, threat assessment, and combat effectiveness** - not personality or roleplaying. They're combat agents optimized for tactical gameplay.

### 1.3 Group Abstraction
Multiple enemies can be represented as a **single agent** to manage performance and complexity. A "Grunt Squad" of 4 enemies acts as one tactical unit with scaled health/damage.

### 1.4 Integration with Existing System
Enemy agents participate in the **same declare/resolve phases** as player characters, using the same initiative system, action economy, and tactical rules.

---

## 2. Data Structures

### 2.1 EnemyAgent Class

```python
@dataclass
class EnemyAgent:
    """Represents an enemy or group of enemies in tactical combat."""

    # ============================================================
    # IDENTITY
    # ============================================================
    agent_id: str  # Unique ID, e.g., "enemy_grunt_squad_1"
    name: str  # Display name, e.g., "Syndicate Enforcers"
    template: str  # Template key, e.g., "grunt", "elite", "boss"

    # ============================================================
    # GROUP MECHANICS
    # ============================================================
    is_group: bool  # True if representing multiple enemies
    unit_count: int  # How many individuals (1 if solo)
    original_unit_count: int  # Starting count for attrition tracking

    # ============================================================
    # COMBAT STATS (YAGS-compatible)
    # ============================================================
    attributes: Dict[str, int]  # Agility, Strength, Perception, etc.
    skills: Dict[str, int]  # Brawl, Guns, Awareness, etc.
    health: int  # Current health
    max_health: int  # Maximum health
    soak: int  # Damage resistance
    wounds: int  # Wound count (uses Tactical Module wound ladder)

    # ============================================================
    # TACTICAL STATE
    # ============================================================
    position: Position  # {ring: str, side: str}
    initiative: int  # Current round initiative (re-rolled each round)
    defence_token: Optional[str]  # Which PC agent_id are they watching?
    tactical_token: Optional[TacticalToken]  # Claimed terrain advantage

    # ============================================================
    # DOCTRINE & BEHAVIOR
    # ============================================================
    tactics: str  # Combat doctrine (see section 2.3)
    threat_priority: str  # Target selection (see section 2.4)
    retreat_threshold: float  # Morale % (0.0-1.0)

    # ============================================================
    # AEONISK-SPECIFIC
    # ============================================================
    void_score: int  # 0-10 void tracking
    void_threshold: int  # Void level that triggers effects (usually 8)

    # ============================================================
    # EQUIPMENT
    # ============================================================
    weapons: List[Weapon]  # Available weapon loadouts
    armor: Optional[Armor]  # Armor and soak modifiers
    special_abilities: List[str]  # e.g., "void_surge", "grenade", "suppress"
    ammo: Dict[str, int]  # Ammo tracking per weapon type

    # ============================================================
    # STATE TRACKING
    # ============================================================
    status_effects: List[str]  # "stunned", "prone", "suppressed", etc.
    is_active: bool  # False if defeated/retreated
    spawned_round: int  # When they entered combat
    despawned_round: Optional[int]  # When they left combat

    # ============================================================
    # COMMUNICATION (NEW - Q2 Answer)
    # ============================================================
    shared_intel: Dict[str, Any]  # Tactical info shared with other enemy agents
```

### 2.2 Position Structure

```python
@dataclass
class Position:
    """Location in concentric ring battlefield (Tactical Module v1.2.3)."""
    ring: str  # "Engaged", "Near", "Far", "Extreme"
    side: str  # "PC", "Enemy"

    def __str__(self):
        return f"{self.ring}-{self.side}"

    def calculate_range(self, other: Position) -> tuple[str, int]:
        """
        Calculate range to another position using v1.2.3 rules.

        Returns:
            (range_name, penalty) e.g., ("Melee", 0), ("Far", -4)
        """
        # Same ring, same side = Melee
        if self.ring == other.ring and self.side == other.side:
            return ("Melee", 0)

        # Both in Engaged
        if self.ring == "Engaged" and other.ring == "Engaged":
            return ("Engaged", 0)

        # Different rings: calculate through center
        rings_apart = self._count_rings_between(other)

        if rings_apart == 0:
            return ("Engaged", 0)
        elif rings_apart == 1:
            return ("Near", -2)
        elif rings_apart == 2:
            return ("Far", -4)
        else:
            return ("Extreme", -6)
```

### 2.3 Tactical Doctrines

```python
TACTICAL_DOCTRINES = {
    "aggressive_melee": {
        "description": "Close to melee range and engage directly",
        "preferred_range": "Melee",
        "preferred_actions": ["Charge", "Attack_Melee"],
        "defence_priority": "closest_threat"
    },

    "defensive_ranged": {
        "description": "Maintain distance, use cover, suppress targets",
        "preferred_range": "Far",
        "preferred_actions": ["Attack_Ranged", "Suppress", "Claim_Cover"],
        "defence_priority": "highest_threat"
    },

    "tactical_ranged": {
        "description": "Balanced ranged tactics with positioning",
        "preferred_range": "Near",
        "preferred_actions": ["Attack_Ranged", "Shift", "Claim_Token"],
        "defence_priority": "optimal_target"
    },

    "extreme_range": {
        "description": "Stay at maximum distance, snipe priority targets",
        "preferred_range": "Extreme",
        "preferred_actions": ["Attack_Ranged", "Shift_Away"],
        "defence_priority": "high_value_target"
    },

    "ambush": {
        "description": "Infiltrate enemy side, strike vulnerable targets",
        "preferred_range": "Melee",
        "preferred_actions": ["Push_Through", "Attack", "Stealth"],
        "defence_priority": "weakest_target"
    },

    "support": {
        "description": "Provide covering fire, claim tactical positions",
        "preferred_range": "Near",
        "preferred_actions": ["Suppress", "Claim_Token", "Overwatch"],
        "defence_priority": "assist_allies"
    },

    "adaptive": {
        "description": "Respond dynamically to battlefield conditions",
        "preferred_range": "varies",
        "preferred_actions": ["any"],
        "defence_priority": "context_dependent"
    }
}
```

### 2.4 Threat Priority Systems

```python
THREAT_PRIORITIES = {
    "highest_threat": "Target PC with highest damage output or immediate danger",
    "weakest_target": "Target PC with lowest health or defenses",
    "objective_focus": "Prioritize tactical objectives over opportunistic targets",
    "closest_threat": "Target nearest PC in range",
    "high_value_target": "Target support/caster PCs over frontline",
    "assist_allies": "Coordinate with allied enemy agents",
    "optimal_target": "Target PCs not watching you (Flanking bonus)"
}
```

---

## 3. Spawn Mechanics

### 3.1 DM Marker Syntax

```
[SPAWN_ENEMY: name | template | count | position | tactics]
```

**Parameters:**
- `name` (required): Display name for agent/group
- `template` (required): Template key to load stats from
- `count` (required): Number of enemies (≥1, >1 creates group)
- `position` (required): Initial ring-side location (e.g., "Near-Enemy")
- `tactics` (optional): Override default template tactics

**Examples:**

```
[SPAWN_ENEMY: Syndicate Grunts | grunt | 3 | Near-Enemy | aggressive_melee]
[SPAWN_ENEMY: Void Cultist | elite | 1 | Far-Enemy | defensive_ranged]
[SPAWN_ENEMY: Ambush Team | grunt | 4 | Far-PC]  # Uses template default tactics
[SPAWN_ENEMY: Boss | boss | 1 | Engaged | adaptive]
```

### 3.2 Enemy Templates

Templates define stat blocks, equipment, and default behavior:

```python
ENEMY_TEMPLATES = {
    "grunt": {
        "attributes": {
            "Agility": 3,
            "Strength": 3,
            "Perception": 2,
            "Intelligence": 2,
            "Empathy": 2,
            "Willpower": 2
        },
        "skills": {
            "Brawl": 2,
            "Guns": 3,
            "Awareness": 2,
            "Athletics": 2
        },
        "health": 12,
        "soak": 4,
        "void_score": 1,
        "weapons": ["pistol", "baton"],
        "armor": "light_armor",
        "default_tactics": "aggressive_melee",
        "threat_priority": "closest_threat",
        "retreat_threshold": 0.3,
        "special_abilities": []
    },

    "elite": {
        "attributes": {
            "Agility": 4,
            "Strength": 4,
            "Perception": 4,
            "Intelligence": 3,
            "Empathy": 3,
            "Willpower": 3
        },
        "skills": {
            "Brawl": 3,
            "Guns": 4,
            "Awareness": 4,
            "Athletics": 3,
            "Stealth": 3
        },
        "health": 20,
        "soak": 6,
        "void_score": 2,
        "weapons": ["rifle", "combat_knife", "grenade"],
        "armor": "medium_armor",
        "default_tactics": "tactical_ranged",
        "threat_priority": "optimal_target",
        "retreat_threshold": 0.2,
        "special_abilities": ["suppress", "grenade"]
    },

    "sniper": {
        "attributes": {
            "Agility": 3,
            "Strength": 2,
            "Perception": 5,
            "Intelligence": 3,
            "Empathy": 2,
            "Willpower": 3
        },
        "skills": {
            "Guns": 5,
            "Awareness": 5,
            "Stealth": 4,
            "Athletics": 2
        },
        "health": 10,
        "soak": 3,
        "void_score": 1,
        "weapons": ["sniper_rifle", "pistol"],
        "armor": "light_armor",
        "default_tactics": "extreme_range",
        "threat_priority": "high_value_target",
        "retreat_threshold": 0.5,  # Retreat early
        "special_abilities": []
    },

    "boss": {
        "attributes": {
            "Agility": 5,
            "Strength": 5,
            "Perception": 5,
            "Intelligence": 4,
            "Empathy": 4,
            "Willpower": 5
        },
        "skills": {
            "Brawl": 4,
            "Guns": 5,
            "Awareness": 5,
            "Astral Arts": 4,
            "Athletics": 4
        },
        "health": 30,
        "soak": 8,
        "void_score": 3,
        "weapons": ["heavy_weapon", "void_blade"],
        "armor": "heavy_armor",
        "default_tactics": "adaptive",
        "threat_priority": "objective_focus",
        "retreat_threshold": 0.1,  # Fights to near-death
        "special_abilities": ["void_surge", "suppress", "grenade"]
    },

    "void_cultist": {
        "attributes": {
            "Agility": 3,
            "Strength": 3,
            "Perception": 3,
            "Intelligence": 3,
            "Empathy": 4,
            "Willpower": 5
        },
        "skills": {
            "Brawl": 2,
            "Astral Arts": 5,
            "Awareness": 3,
            "Intimacy Ritual": 4
        },
        "health": 15,
        "soak": 4,
        "void_score": 5,  # Already corrupted
        "weapons": ["ritual_blade", "pistol"],
        "armor": "robes",
        "default_tactics": "support",
        "threat_priority": "high_value_target",
        "retreat_threshold": 0.2,
        "special_abilities": ["void_surge", "ritual_attack"]
    }
}
```

### 3.3 Spawn Processing Logic

```python
def spawn_enemy(marker: str, combat_state: CombatState) -> EnemyAgent:
    """
    Parse spawn marker and create enemy agent.

    Example: [SPAWN_ENEMY: Grunts | grunt | 3 | Near-Enemy | aggressive_melee]
    """
    # 1. Parse marker
    parts = marker.split('|')
    name = parts[0].strip()
    template_key = parts[1].strip()
    count = int(parts[2].strip())
    position_str = parts[3].strip()
    tactics = parts[4].strip() if len(parts) > 4 else None

    # 2. Load template
    template = ENEMY_TEMPLATES[template_key]

    # 3. Parse position
    ring, side = position_str.split('-')
    position = Position(ring=ring, side=side)

    # 4. Create agent
    agent_id = f"enemy_{template_key}_{generate_unique_id()}"

    # 5. Scale for groups
    if count > 1:
        is_group = True
        # Health scaling: base × count × 0.7 (groups tougher total, weaker individually)
        max_health = int(template['health'] * count * 0.7)
    else:
        is_group = False
        max_health = template['health']

    # 6. Build agent
    agent = EnemyAgent(
        agent_id=agent_id,
        name=name,
        template=template_key,
        is_group=is_group,
        unit_count=count,
        original_unit_count=count,
        attributes=template['attributes'].copy(),
        skills=template['skills'].copy(),
        health=max_health,
        max_health=max_health,
        soak=template['soak'],
        wounds=0,
        position=position,
        initiative=0,  # Will be rolled
        defence_token=None,
        tactical_token=None,
        tactics=tactics or template['default_tactics'],
        threat_priority=template['threat_priority'],
        retreat_threshold=template['retreat_threshold'],
        void_score=template['void_score'],
        void_threshold=8,
        weapons=load_weapons(template['weapons']),
        armor=load_armor(template['armor']),
        special_abilities=template['special_abilities'].copy(),
        ammo=initialize_ammo(template['weapons']),
        status_effects=[],
        is_active=True,
        spawned_round=combat_state.current_round,
        despawned_round=None,
        shared_intel={}
    )

    # 7. Roll initiative
    agent.initiative = roll_initiative(agent)

    # 8. Add to combat roster
    combat_state.enemy_agents.append(agent)

    return agent


def roll_initiative(agent: EnemyAgent) -> int:
    """Roll initiative for enemy agent (Agility × 4 + d20)."""
    agility = agent.attributes.get('Agility', 2)
    roll = random.randint(1, 20)

    # Natural 1 = Initiative 0
    if roll == 1:
        return 0

    return (agility * 4) + roll
```

---

## 4. Group Mechanics

### 4.1 Health Scaling

**Formula:**
```
Group Health = Template Health × Unit Count × 0.7
```

**Examples:**
- 3 grunts: 12 × 3 × 0.7 = 25.2 → 25 health
- 4 grunts: 12 × 4 × 0.7 = 33.6 → 34 health
- 2 elites: 20 × 2 × 0.7 = 28 health

**Rationale:** Groups are tougher than single enemies but not linearly scaling (to avoid making 10 grunts = 120 health).

### 4.2 Damage Scaling

**Formula:**
```
Group Damage Bonus = +2 per additional unit (max +6)
```

**Examples:**
- 1 unit: +0 damage
- 2 units: +2 damage
- 3 units: +4 damage
- 4 units: +6 damage
- 5+ units: +6 damage (capped)

**Application:**
Group rolls attack once, on hit deals base weapon damage + group bonus.

### 4.3 Attrition

As group health decreases, unit count drops to represent casualties:

**Formula:**
```
Units Lost = floor((Max Health - Current Health) / (Max Health / Original Unit Count))
Current Unit Count = Original Unit Count - Units Lost
```

**Example:**
```
3-unit grunt group:
- Max Health: 25
- Health per unit: 25 / 3 ≈ 8.3

Combat:
- Takes 10 damage → 15/25 health (60%)
  - Units lost: floor((25 - 15) / 8.3) = floor(1.2) = 1
  - Current unit count: 3 - 1 = 2 units remain

- Takes another 10 damage → 5/25 health (20%)
  - Units lost: floor((25 - 5) / 8.3) = floor(2.4) = 2
  - Current unit count: 3 - 2 = 1 unit remains

- Takes 5 more damage → 0/25 health
  - Group defeated
```

**Prompt Updates:**
When unit count changes, update enemy agent prompts to reflect:
- "3 enemies remain" → "2 enemies remain" → "1 enemy remains (critically wounded)"

### 4.4 Action Economy

Groups act as **single agent**:
- 1 Major Action (whole group coordinates)
- 1 Minor Action
- 1 Reaction

This prevents 4 enemies = 4× prompts and 4× initiative slots.

---

## 5. Tactical Prompts

### 5.1 Prompt Structure

Enemy agents receive tactical prompts during **Declare Phase**:

```python
def generate_enemy_tactical_prompt(
    enemy: EnemyAgent,
    combat_state: CombatState
) -> str:
    """
    Generate tactical prompt for enemy agent decision-making.

    Includes:
    - Agent status (health, position, initiative)
    - Battlefield situation (PC targets, allied enemies)
    - Tactical options (movement, attacks, abilities)
    - Shared intel from other enemy agents (NEW - Q2)
    - Doctrine guidance
    - Structured output format
    """

    return f"""# TACTICAL COMBAT AGENT: {enemy.name}

## YOUR STATUS
{"=" * 60}
Unit Type: {enemy.template.upper()}
Unit Count: {enemy.unit_count} {"units" if enemy.unit_count > 1 else "unit"}
Health: {enemy.health}/{enemy.max_health} ({get_health_percentage(enemy)}%)
Wounds: {enemy.wounds} {"(CRITICAL)" if enemy.wounds >= 4 else ""}
Void Score: {enemy.void_score}/10 {get_void_status(enemy.void_score)}
Position: {enemy.position}
Initiative: {enemy.initiative}
Status Effects: {', '.join(enemy.status_effects) or 'None'}

## COMBAT DOCTRINE
{"=" * 60}
Tactics: {enemy.tactics}
Description: {TACTICAL_DOCTRINES[enemy.tactics]['description']}
Threat Priority: {enemy.threat_priority}
Retreat Threshold: {enemy.retreat_threshold * 100}% health

## BATTLEFIELD SITUATION
{"=" * 60}

### Enemy Targets (Player Characters):
{format_pc_targets(combat_state.players, enemy)}

Example output:
```
- Sable [PC-1]
  Position: Near-Enemy (MELEE RANGE to you)
  Initiative: 24 (acts before you)
  Health: ~70% (wounded)
  Defence Token: WATCHING YOU (-2 to hit them)
  Weapons: Melee (void blade), effective at this range
  Threat Level: HIGH (melee fighter at close range)

- Echo [PC-2]
  Position: Far-Enemy (FAR RANGE, -4 penalty)
  Initiative: 18 (acts after you)
  Health: ~90% (healthy)
  Defence Token: NOT watching you (+2 Flanking if you attack)
  Weapons: Ranged (rifle), suppressing fire capable
  Threat Level: MEDIUM (ranged, not immediate danger)

- Nyx [PC-3]
  Position: Engaged (NEAR RANGE, -2 penalty)
  Initiative: 15 (acts after you)
  Health: ~50% (bloodied)
  Defence Token: Watching Grunt Squad 2
  Weapons: Pistol + rituals
  Threat Level: MEDIUM (support caster, vulnerable)
```

### Allied Forces (Other Enemy Agents):
{format_allied_enemies(combat_state.enemies, enemy)}

Example output:
```
- Grunt Squad 2 [ALLY-1]
  Position: Near-Enemy
  Unit Count: 2 units remaining (down from 3)
  Health: ~40% (critical)
  Status: Engaging Sable

- Elite Sniper [ALLY-2]
  Position: Extreme-Enemy
  Unit Count: 1 unit
  Health: ~100% (healthy)
  Status: Providing covering fire
```

### Shared Tactical Intel (from allied enemies):
{format_shared_intel(enemy, combat_state)}

Example output:
```
From Grunt Squad 2:
- "Sable is primary threat, melee powerhouse, focus fire recommended"
- "Echo has grenade, watch for AoE next round"

From Elite Sniper:
- "Nyx is casting support rituals, interrupt if possible"
- "Cover available at Near-Enemy (I'm not using it)"
```

### Tactical Tokens Available:
{format_tactical_tokens(combat_state)}

Example:
```
- Cover (Near-Enemy) - UNCLAIMED
- High-Ground (Far-PC) - UNCLAIMED
- Ley-Node (Engaged) - CLAIMED by Nyx
```

## TACTICAL OPTIONS
{"=" * 60}

### Movement Options:
Current Position: {enemy.position}

- Minor Action: Shift 1 ring
  → Toward center: {get_shift_toward(enemy.position)}
  → Away from center: {get_shift_away(enemy.position)}

- Major Action: Shift 2 rings
  → {get_shift_2_options(enemy.position)}

- Major Action: Push Through
  → Cross to {opposite_side(enemy.position.side)} hemisphere (RISKY)

### Attack Options:
{format_weapon_options(enemy, combat_state)}

Example:
```
1. RIFLE (Primary)
   Range: Effective at Far/Near/Melee
   Damage: Strength(3) + Weapon(4) + d20 + Group Bonus(+4) = 11 + d20
   Special: RoF 3 (can use Suppress action)
   Ammo: 24/30

2. BATON (Melee)
   Range: Melee only
   Damage: Strength(3) + Weapon(2) + d20 + Group Bonus(+4) = 9 + d20

3. GRENADE (1 remaining)
   Type: Area Effect (targets ring-side location)
   Damage: DC 20 Agility save, 2d6 damage
   WARNING: Friendly fire if allies in blast zone
   Available targets:
     - Near-Enemy (would hit: Sable, Grunt Squad 2, YOU)
     - Engaged (would hit: Nyx, any allies there)
```

### Special Abilities:
{format_special_abilities(enemy)}

Example if has void_surge:
```
- VOID SURGE (Unlimited at Void ≤ 7, LOCKED at Void ≥ 8)
  Current Void: {enemy.void_score}/10
  Effect: +4 damage, auto-Shock on hit, +1 Stun to you, +1 Void
  Status: {"AVAILABLE" if enemy.void_score < 8 else "LOCKED (too corrupted)"}
```

### Defence Token Allocation:
CRITICAL DECISION - Must allocate to ONE PC

Current: {enemy.defence_token or "NONE (all PCs get Flanking +2!)"}

Benefits:
- PC you're watching: -2 penalty to hit you
- PCs you're NOT watching: +2 Flanking bonus vs you

Recommendation: {recommend_defence_token(enemy, combat_state)}

## TACTICAL ANALYSIS
{"=" * 60}

Range Analysis:
{analyze_ranges(enemy, combat_state)}

Example:
```
- MELEE RANGE: Sable (0 penalty)
- NEAR RANGE: Nyx (-2 penalty)
- FAR RANGE: Echo (-4 penalty)
- EXTREME RANGE: None

Doctrine '{enemy.tactics}' prefers: {TACTICAL_DOCTRINES[enemy.tactics]['preferred_range']}
Current position rating: {"OPTIMAL" or "SUBOPTIMAL - consider shifting"}
```

Threat Assessment:
{analyze_threats(enemy, combat_state)}

Example:
```
Based on priority '{enemy.threat_priority}':

1. PRIMARY THREAT: Sable
   - Melee range, high damage output
   - Watching you (hard to hit)
   - Recommendation: Maintain distance or focus fire with allies

2. OPPORTUNITY TARGET: Echo
   - NOT watching you (+2 Flanking)
   - At Far range (-4 penalty but Flanking offsets to -2)
   - Recommendation: Good target if ranged attack available

3. VULNERABLE TARGET: Nyx
   - Low health (50%), support role
   - Watching someone else (+2 Flanking)
   - Recommendation: Eliminate support caster if possible
```

Recommended Action (based on doctrine):
{suggest_action(enemy, combat_state)}

Example for "aggressive_melee" doctrine:
```
SUGGESTED: Charge Sable
REASONING: Doctrine favors melee engagement, Sable is closest threat
RISK: Sable is watching you (-2), charging gives you +2 damage but -2 defence
ALTERNATIVE: Attack Echo for Flanking bonus (+2) at range (-4) = net -2
```

## RETREAT ASSESSMENT
{"=" * 60}

Current Health: {get_health_percentage(enemy)}%
Retreat Threshold: {enemy.retreat_threshold * 100}%

Status: {get_retreat_status(enemy)}

{get_retreat_recommendation(enemy, combat_state)}

Example outputs:
```
Status: HOLDING (health above threshold)
Continue fighting.
```

```
Status: CRITICAL (health below threshold)
You may choose to retreat this round. If retreating, provide narration.
Allied enemies will be informed of your withdrawal.
```

## YOUR DECLARATION
{"=" * 60}

Provide your tactical decision in this EXACT format:

DEFENCE_TOKEN: [PC agent_id you're watching - REQUIRED]
MAJOR_ACTION: [Attack / Shift / Shift_2 / Charge / Suppress / Push_Through / Throw_Grenade / Retreat]
TARGET: [PC agent_id OR ring-side location if AoE]
WEAPON: [weapon name if attacking]
MINOR_ACTION: [Shift / Claim_Token / Reload / Disengage / None]
TOKEN_TARGET: [token name if claiming]
TACTICAL_REASONING: [1-2 sentences explaining your choice]
SHARE_INTEL: [Optional: info to share with allied enemies]

Example declarations:

```
DEFENCE_TOKEN: PC-1
MAJOR_ACTION: Attack
TARGET: PC-2
WEAPON: Rifle
MINOR_ACTION: None
TACTICAL_REASONING: Targeting Echo (PC-2) because they're not watching me (+2 Flanking bonus). Defence token on Sable (PC-1) to mitigate their melee threat.
SHARE_INTEL: Echo has grenade, recommend spreading out
```

```
DEFENCE_TOKEN: PC-1
MAJOR_ACTION: Throw_Grenade
TARGET: Near-Enemy
WEAPON: Grenade
MINOR_ACTION: Shift
TACTICAL_REASONING: Throwing grenade at Near-Enemy to hit Sable even though Grunt Squad 2 will take friendly fire - Sable is too dangerous to leave active. Shifting away from blast zone.
SHARE_INTEL: Grenade incoming at Near-Enemy, allied units should clear zone
```

```
DEFENCE_TOKEN: None
MAJOR_ACTION: Retreat
TARGET: None
WEAPON: None
MINOR_ACTION: None
TACTICAL_REASONING: Health critical (15%), below retreat threshold (30%). Falling back through maintenance corridor to regroup.
SHARE_INTEL: Withdrawing, recommend focus fire on Sable
```

---

**You are a tactical combat agent. Make optimal decisions based on battlefield conditions and your doctrine. Coordinate with allied enemy agents via shared intel. Prioritize tactical effectiveness.**
"""
```

### 5.2 Shared Intel System (NEW - Q2 Answer)

Enemy agents can share tactical information with each other:

```python
class SharedIntel:
    """Tactical information shared between enemy agents."""

    def __init__(self):
        self.intel_pool: List[Dict[str, Any]] = []

    def add_intel(self, source_agent: str, intel: str, round: int):
        """Add intelligence from an enemy agent."""
        self.intel_pool.append({
            "source": source_agent,
            "intel": intel,
            "round": round
        })

    def get_recent_intel(self, current_round: int, lookback: int = 2) -> List[str]:
        """Get intel from recent rounds."""
        recent = [
            f"From {item['source']}: {item['intel']}"
            for item in self.intel_pool
            if current_round - item['round'] <= lookback
        ]
        return recent

    def clear_old_intel(self, current_round: int, max_age: int = 3):
        """Remove stale intelligence."""
        self.intel_pool = [
            item for item in self.intel_pool
            if current_round - item['round'] <= max_age
        ]
```

**Usage:**
- Enemy declares: `SHARE_INTEL: Echo has grenade, recommend spreading out`
- System adds to shared intel pool
- Next round, other enemies see this intel in their prompts
- Creates emergent coordination without explicit commands

---

## 6. Combat Flow Integration

### 6.1 Round Structure

**Declare Phase (Ascending Initiative):**
1. Sort all combatants (PCs + Enemies) by initiative (ascending)
2. For each combatant in order:
   - If PC: Get player declaration (existing flow)
   - If Enemy: Generate tactical prompt, get LLM declaration
   - Parse and store declaration
3. Validate all declarations

**Fast Phase (Descending Initiative):**
1. Sort all combatants by initiative (descending)
2. For each combatant in order:
   - If has reaction trigger: Execute reaction
   - Auto-execute enemy reactions based on doctrine (Q5 answer)
3. Update combat state

**Slow Phase (Descending Initiative):**
1. Sort all combatants by initiative (descending)
2. For each combatant in order:
   - Execute declared major action
   - Execute declared minor action
   - Apply damage/effects
   - Update state
3. Narrate round results

**Cleanup Phase:**
1. Check wound thresholds (PCs + Enemies)
2. Apply group attrition (reduce unit counts)
3. Check retreat conditions
4. Remove defeated enemies
5. Clear stale intel
6. Narrate status changes
7. Re-roll initiative for next round

### 6.2 Initiative Re-rolling

**Every round start:**
```python
def reroll_initiative(combat_state: CombatState):
    """Re-roll initiative for all combatants."""

    # PCs
    for pc in combat_state.players:
        pc.initiative = roll_pc_initiative(pc)

    # Enemies
    for enemy in combat_state.enemy_agents:
        if enemy.is_active:
            enemy.initiative = roll_initiative(enemy)
```

### 6.3 Action Parsing

```python
def parse_enemy_declaration(declaration: str, enemy: EnemyAgent) -> EnemyDeclaration:
    """
    Parse structured enemy declaration.

    Expected format:
        DEFENCE_TOKEN: PC-1
        MAJOR_ACTION: Attack
        TARGET: PC-2
        WEAPON: Rifle
        MINOR_ACTION: Claim_Token
        TOKEN_TARGET: Cover
        TACTICAL_REASONING: ...
        SHARE_INTEL: ...
    """

    lines = declaration.strip().split('\n')
    parsed = {}

    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            parsed[key.strip()] = value.strip()

    return EnemyDeclaration(
        agent_id=enemy.agent_id,
        defence_token=parsed.get('DEFENCE_TOKEN'),
        major_action=parsed.get('MAJOR_ACTION'),
        target=parsed.get('TARGET'),
        weapon=parsed.get('WEAPON'),
        minor_action=parsed.get('MINOR_ACTION'),
        token_target=parsed.get('TOKEN_TARGET'),
        reasoning=parsed.get('TACTICAL_REASONING', ''),
        shared_intel=parsed.get('SHARE_INTEL', '')
    )
```

### 6.4 Auto-Execute Reactions (Q5 Answer)

```python
def auto_execute_enemy_reactions(
    enemy: EnemyAgent,
    trigger: ReactionTrigger,
    combat_state: CombatState
) -> Optional[Reaction]:
    """
    Automatically execute enemy reactions based on doctrine.

    Simple reactions (parry, dodge) are auto-executed.
    Complex reactions (spend token, overwatch) require prompting.
    """

    # Being attacked → Parry if able
    if trigger.type == "attacked" and enemy.can_parry():
        return Reaction(
            type="parry",
            agent=enemy.agent_id,
            target=trigger.attacker
        )

    # Overwatch trigger → Fire if set up
    if trigger.type == "movement" and enemy.has_overwatch():
        if is_in_overwatch_arc(enemy, trigger.target):
            return Reaction(
                type="overwatch_fire",
                agent=enemy.agent_id,
                target=trigger.target
            )

    # Complex decisions → Prompt (future enhancement)
    # For now, auto-execute simple heuristics

    return None
```

---

## 7. Despawn Mechanics

### 7.1 Automatic Despawn Conditions

**Health ≤ 0:**
```python
if enemy.health <= 0:
    enemy.is_active = False
    enemy.despawned_round = combat_state.current_round
    despawn_reason = "defeated"
    # DM narrates outcome and loot
```

**Retreat Declaration:**
```python
if enemy_declaration.major_action == "Retreat":
    enemy.is_active = False
    enemy.despawned_round = combat_state.current_round
    despawn_reason = "retreated"
    despawn_narration = enemy_declaration.reasoning
    # DM can expand on retreat outcome
```

**Group Attrition:**
```python
if enemy.is_group and enemy.unit_count <= 0:
    enemy.is_active = False
    enemy.despawned_round = combat_state.current_round
    despawn_reason = "eliminated"
```

### 7.2 Manual Despawn

DM can manually remove enemies:

```
[DESPAWN_ENEMY: agent_id | reason]
```

Examples:
```
[DESPAWN_ENEMY: enemy_grunt_1 | fled through airlock]
[DESPAWN_ENEMY: enemy_elite_2 | called for reinforcements and withdrew]
```

### 7.3 Loot Suggestions (Q6 Answer)

```python
def suggest_loot(enemy: EnemyAgent) -> str:
    """
    Generate loot suggestion based on template.
    DM can override or expand.
    """

    template = ENEMY_TEMPLATES[enemy.template]

    loot_items = []

    # Weapons
    for weapon in enemy.weapons:
        condition = "fair" if enemy.health > 0 else "damaged"
        loot_items.append(f"{weapon.name} ({condition})")

    # Armor
    if enemy.armor:
        condition = "damaged" if enemy.wounds > 2 else "fair"
        loot_items.append(f"{enemy.armor.name} ({condition})")

    # Credits
    credits = random.randint(10, 50) * enemy.unit_count
    loot_items.append(f"{credits} credits")

    # Special items (10% chance per unit)
    if random.random() < (0.1 * enemy.unit_count):
        loot_items.append("datapad with encrypted files")

    return f"Suggested loot: {', '.join(loot_items)}"
```

---

## 8. Void Mechanics for Enemies

### 8.1 Void Tracking

Enemies track void score (0-10) same as PCs:

```python
def apply_void_gain(enemy: EnemyAgent, source: str, amount: int):
    """
    Apply void gain to enemy.

    Sources: void_surge, ritual use, void environment, etc.
    """
    enemy.void_score += amount
    enemy.void_score = min(enemy.void_score, 10)  # Cap at 10

    # Check thresholds
    if enemy.void_score >= 8:
        # Lock out void abilities
        if "void_surge" in enemy.special_abilities:
            # Can no longer use void surge
            pass

    if enemy.void_score >= 10:
        # Void possession
        trigger_void_possession(enemy)
```

### 8.2 Void Possession (Q4 Answer)

When enemy reaches Void 10, same as PCs - possessed by the void:

```python
def trigger_void_possession(enemy: EnemyAgent):
    """
    Handle void possession for enemy agent.

    Q4 Answer: Same as PCs, becomes possessed by the void.
    """

    # Mark as possessed
    enemy.status_effects.append("void_possessed")

    # DM narrates dramatic transformation
    possession_narration = generate_possession_narration(enemy)

    # Options:
    # 1. Enemy becomes uncontrolled void threat (change tactics to "berserk")
    # 2. Enemy transforms into void creature (change template)
    # 3. Enemy self-destructs in void explosion (despawn with AoE)

    # For now: Transform tactics
    enemy.tactics = "berserk_void"
    enemy.threat_priority = "closest_threat"
    enemy.retreat_threshold = 0.0  # Never retreats

    # Notify DM for narration
    return {
        "event": "void_possession",
        "agent": enemy.name,
        "narration": possession_narration,
        "mechanical_effect": "Enemy now acts with berserk void tactics"
    }
```

### 8.3 Void Status Effects

```python
VOID_EFFECTS = {
    "0-4": "Stable",
    "5-7": "Corrupted (-2 to Empathy-based checks)",
    "8-9": "Heavily Corrupted (void abilities locked, unstable)",
    "10": "Void Possessed (uncontrolled, berserk)"
}
```

---

## 9. Configuration & Feature Flags

### 9.1 Session Config

```json
{
  "session_id": "combat_test_001",
  "tactical_module_enabled": true,
  "enemy_agents_enabled": true,
  "enemy_agent_config": {
    "allow_groups": true,
    "max_enemies_per_combat": 20,
    "shared_intel_enabled": true,
    "auto_execute_reactions": true,
    "loot_suggestions_enabled": true,
    "void_tracking_enabled": true
  }
}
```

### 9.2 Feature Gating

```python
def is_tactical_combat_enabled(session_config: dict) -> bool:
    """Check if tactical combat with enemy agents is enabled."""
    return (
        session_config.get("tactical_module_enabled", False) and
        session_config.get("enemy_agents_enabled", False)
    )


def spawn_enemy_if_enabled(marker: str, session_config: dict, combat_state: CombatState):
    """Only spawn enemies if feature is enabled."""
    if not is_tactical_combat_enabled(session_config):
        logger.warning("Enemy agents disabled, ignoring spawn marker")
        return None

    return spawn_enemy(marker, combat_state)
```

---

## 10. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
**Goal:** Basic enemy agent structure and spawning

**Tasks:**
1. Create `EnemyAgent` dataclass
2. Create `Position` class with range calculation (v1.2.3 rules)
3. Implement enemy template system
4. Implement spawn marker parsing
5. Implement basic tactical prompt generation
6. Add session config feature flags

**Deliverables:**
- Can spawn enemy agents from DM markers
- Enemy agents have valid stats and positions
- Basic prompts generated (no LLM integration yet)

### Phase 2: Combat Integration (Week 2)
**Goal:** Enemy agents participate in declare/resolve flow

**Tasks:**
1. Integrate enemy agents into initiative order
2. Implement declaration parsing
3. Implement action execution (attacks, movement)
4. Implement damage application
5. Implement basic despawn (health ≤ 0)

**Deliverables:**
- Enemy agents act in combat rounds
- Can attack PCs, move, take damage
- Defeated enemies despawn properly

### Phase 3: Group Mechanics (Week 3)
**Goal:** Multi-unit enemy groups work correctly

**Tasks:**
1. Implement health scaling for groups
2. Implement damage scaling for groups
3. Implement attrition (unit count reduction)
4. Update prompts to reflect unit count
5. Test group combat scenarios

**Deliverables:**
- Can spawn 3-unit grunt squad
- Group health/damage scales correctly
- Attrition reduces unit count appropriately

### Phase 4: Tactical Depth (Week 4)
**Goal:** Advanced tactical features

**Tasks:**
1. Implement shared intel system (Q2)
2. Implement doctrine-specific action suggestions
3. Implement threat analysis
4. Implement auto-execute reactions (Q5)
5. Implement retreat logic
6. Implement Defence Token allocation

**Deliverables:**
- Enemies coordinate via shared intel
- Enemies follow tactical doctrines
- Enemies retreat when appropriate
- Combat feels tactically interesting

### Phase 5: Void & Polish (Week 5)
**Goal:** Aeonisk-specific features and refinement

**Tasks:**
1. Implement void tracking for enemies
2. Implement void possession (Q4)
3. Implement loot suggestions (Q6)
4. Refine prompts based on testing
5. Optimize performance
6. Document DM usage guide

**Deliverables:**
- Void mechanics work for enemies
- Loot generation functional
- System ready for production use
- DM has clear instructions

---

## 11. Testing Scenarios

### Scenario 1: Basic Spawn & Combat
```
DM: [SPAWN_ENEMY: Grunts | grunt | 3 | Near-Enemy | aggressive_melee]
Expected: 3-unit group spawns, engages PCs, uses melee tactics
```

### Scenario 2: Group Attrition
```
Setup: 3-unit grunt group (25 health)
Combat: PCs deal 10 damage → 2 units remain
        PCs deal 10 damage → 1 unit remains
        PCs deal 5 damage → Group defeated
Expected: Unit count updates in prompts, damage scaling adjusts
```

### Scenario 3: Shared Intel
```
Round 1: Elite Sniper declares "SHARE_INTEL: Echo has grenade"
Round 2: Grunt Squad sees intel in prompt, spreads out
Expected: Grunts receive intel, adjust tactics
```

### Scenario 4: Retreat
```
Setup: Sniper at 15% health (retreat threshold 50%)
Round X: Sniper declares "MAJOR_ACTION: Retreat"
Expected: Sniper despawns, DM narrates escape
```

### Scenario 5: Void Possession
```
Setup: Void Cultist at Void 8 uses Void Surge
Effect: Void → 9 (can still act), uses Void Surge again
Effect: Void → 10 (possessed!)
Expected: Cultist transforms to berserk tactics, DM narrates corruption
```

### Scenario 6: Friendly Fire Grenade
```
Setup:
  Near-Enemy: PC infiltrator, 2-unit enemy group
  Far-Enemy: Enemy sniper
Sniper declares: Throw grenade at Near-Enemy
Expected: PC + enemy group both make saves, sniper risks fragging allies
```

---

## 12. Open Questions & Future Enhancements

### Resolved Questions:
- ✅ Q1: Roll initiative each round
- ✅ Q2: Share intel between enemy agents
- ✅ Q3: No special boss mechanics
- ✅ Q4: Void 10 = possession (same as PCs)
- ✅ Q5: Auto-execute reactions
- ✅ Q6: System suggests loot, DM overrides

### Future Enhancements (Post-v1.0):
1. **Enemy reinforcements:** Dynamic spawning mid-combat
2. **Morale system:** Groups break if leader defeated
3. **Battlefield objectives:** Capture points, defend locations
4. **Environmental hazards:** Void rifts, hull breaches
5. **Boss mechanics:** Optional complex behavior for unique enemies
6. **Enemy leveling:** Enemies that learn from combat
7. **Faction tactics:** Different enemy factions with signature tactics
8. **Ritual enemies:** Enemies using ritual system
9. **Vehicle enemies:** Tactical module vehicle rules integration
10. **AI vs AI:** Enemy agents vs NPC allies

---

## 13. Performance Considerations

### LLM Token Optimization:
- **Prompt size:** ~800-1200 tokens per enemy agent per round
- **Group mechanics:** Reduces O(n) enemies to O(1) group agent
- **Intel pooling:** Shared state instead of repeated context
- **Action caching:** Cache tactical analysis between similar states

### Scaling Limits:
- **Recommended:** 1-4 enemy agents per combat
- **Maximum:** 6-8 enemy agents (with groups)
- **PC limit:** System designed for 2-6 PCs

### Optimization Strategies:
1. Use groups for similar enemies (4 grunts = 1 group)
2. Cache enemy prompts when state hasn't changed
3. Parallel LLM calls for multiple enemy declarations
4. Simplify prompts for low-intelligence enemies
5. Auto-execute routine actions without prompting

---

## 14. DM Usage Guide (Summary)

### Spawning Enemies:
```
In your narration, include:
[SPAWN_ENEMY: name | template | count | position | tactics]

Example:
"Guards burst through the door!"
[SPAWN_ENEMY: Security Team | grunt | 4 | Near-Enemy | aggressive_melee]
```

### Templates Available:
- `grunt`: Basic enemies (low stats, aggressive)
- `elite`: Veteran enemies (good stats, tactical)
- `sniper`: Long-range specialists (high perception)
- `boss`: Major threats (high stats, adaptive)
- `void_cultist`: Ritual users (high void score)

### Tactics Options:
- `aggressive_melee`: Close and engage
- `defensive_ranged`: Maintain distance
- `tactical_ranged`: Balanced positioning
- `extreme_range`: Sniper tactics
- `ambush`: Infiltrate enemy side
- `support`: Covering fire and positioning
- `adaptive`: Dynamic response

### Monitoring Combat:
- Check enemy health/wounds in status display
- Note shared intel between enemies
- Watch for retreat declarations
- Review enemy reasoning in logs

### Despawning:
- Automatic when health ≤ 0
- Automatic when enemy retreats
- Manual: `[DESPAWN_ENEMY: agent_id | reason]`

### Loot:
- System suggests loot after defeat
- You can override or expand suggestions
- Narrate finding items, describe condition

---

## 15. Success Criteria

This system will be considered successful when:

1. ✅ DM can spawn enemies with simple markers
2. ✅ Enemy agents make autonomous tactical decisions
3. ✅ Groups work efficiently (no performance issues)
4. ✅ Enemies coordinate via shared intel
5. ✅ Combat feels challenging and dynamic
6. ✅ Enemies retreat appropriately (not all fight to death)
7. ✅ Void mechanics work for enemies
8. ✅ System integrates seamlessly with existing combat flow
9. ✅ PCs feel like they're fighting intelligent opponents
10. ✅ DM has minimal micromanagement burden

---

## Appendix A: Example Combat Transcript

```
=== ROUND 1: DECLARE PHASE ===

DM: "Three enforcers emerge from cover, weapons raised!"
[SPAWN_ENEMY: Syndicate Enforcers | grunt | 3 | Near-Enemy | aggressive_melee]

System: Syndicate Enforcers spawned (3 units, 25 health, Initiative 22)

Initiative Order:
1. Echo (28) - PC
2. Syndicate Enforcers (22) - Enemy
3. Sable (18) - PC
4. Nyx (12) - PC

--- Declare Phase (Ascending) ---

Nyx (12): "Moving to Near-PC, shooting Enforcers with pistol"
  Defence Token: Enforcers

Sable (18): "Charging the Enforcers, void blade ready!"
  Defence Token: Enforcers
  Major: Charge Enforcers

Syndicate Enforcers (22): [Receives tactical prompt]
  DEFENCE_TOKEN: PC-Sable
  MAJOR_ACTION: Attack
  TARGET: PC-Sable
  WEAPON: Rifle
  MINOR_ACTION: None
  TACTICAL_REASONING: Sable charging us is primary threat, coordinating fire with +4 group bonus
  SHARE_INTEL: Sable is charging, high damage threat

Echo (28): "Covering Sable's charge, rifle aimed at Enforcers"
  Defence Token: Enforcers
  Major: Attack Enforcers

=== ROUND 1: SLOW PHASE ===

--- Resolve (Descending) ---

Echo (28):
  Attacks Syndicate Enforcers
  Roll: Perception(4) × Guns(4) + d20(14) = 30
  Range: Far-Enemy to Near-Enemy = Near (-2)
  Defence: Enforcers watching Sable, Echo gets +2 Flanking
  Total: 30 - 2 + 2 = 30 vs Defence 18
  HIT! Damage: 4 (weapon) + d20(11) = 15
  Enforcers: 25 → 10 health

Syndicate Enforcers (22):
  Attack Sable (coordinated fire)
  Roll: Perception(2) × Guns(3) + d20(16) = 22
  Group Bonus: +4 damage
  Defence Token on Sable: -2 to hit
  Total: 22 - 2 = 20 vs Sable Defence 24
  MISS! (Sable dodges the coordinated volley)

Sable (18):
  Charges Syndicate Enforcers
  Shifts: Far-PC → Near-PC → Engaged → Near-Enemy
  Melee Attack:
  Roll: Agility(5) × Brawl(4) + d20(18) = 38
  Charge bonus: +2 damage
  Total: 38 vs Defence 16
  HIT! Damage: 5 (Str) + 4 (weapon) + d20(15) + 2 (charge) = 26
  Enforcers: 10 → 0 health

  DEFEATED!

=== ROUND 1: CLEANUP ===

Syndicate Enforcers: Defeated (0 health)
Despawn: defeated
DM: "The enforcers collapse under Sable's assault. Their rifles clatter to the floor."

Loot Suggestion: 3× pistols (fair), 3× batons (damaged), light armor (damaged), 45 credits

---

Combat Result: PC Victory
Duration: 1 round
Casualties: 3 enemy units defeated, 0 PC injuries
```

---

## Appendix B: Prompt Token Estimate

**Typical Enemy Tactical Prompt:**
- Header & Status: ~150 tokens
- Battlefield Situation: ~300 tokens
- Tactical Options: ~250 tokens
- Analysis & Recommendations: ~200 tokens
- Output Format: ~100 tokens

**Total:** ~1000 tokens per enemy agent per round

**With 3 enemy agents:** ~3000 tokens per round for enemy prompts

**Optimization:** Groups reduce this significantly (4 grunts as 1 group = 1000 tokens instead of 4000)

---

## Appendix C: Configuration Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "tactical_module_enabled": {
      "type": "boolean",
      "description": "Enable Tactical Module v1.2.3 combat rules"
    },
    "enemy_agents_enabled": {
      "type": "boolean",
      "description": "Enable autonomous enemy agent system"
    },
    "enemy_agent_config": {
      "type": "object",
      "properties": {
        "allow_groups": {
          "type": "boolean",
          "description": "Allow multiple enemies as single group agent"
        },
        "max_enemies_per_combat": {
          "type": "integer",
          "description": "Maximum total enemy units in combat"
        },
        "shared_intel_enabled": {
          "type": "boolean",
          "description": "Allow enemies to share tactical intel"
        },
        "auto_execute_reactions": {
          "type": "boolean",
          "description": "Auto-execute simple enemy reactions"
        },
        "loot_suggestions_enabled": {
          "type": "boolean",
          "description": "Generate loot suggestions on defeat"
        },
        "void_tracking_enabled": {
          "type": "boolean",
          "description": "Track void scores for enemies"
        }
      }
    }
  }
}
```

---

**End of Design Document**

**Next Steps:**
1. Review and approve design
2. Create implementation TODO list
3. Begin Phase 1: Core Infrastructure
4. Iterate based on testing feedback

**Document Version:** 1.0
**Last Updated:** 2025-10-22
**Status:** Awaiting approval to proceed with implementation
