# NPC and De-escalation System Design

**Status**: In Progress (Branch: `npcs-and-deescalation`)
**Created**: 2025-11-02
**Last Updated**: 2025-11-04
**Version**: 2.0 (Major revision based on implementation research)

## Implementation Progress

**Completed Phases:**
- ✅ **Phase 1**: Core data structures (NPCAgent, NPCLLMClient, NPCAction) - All 13 tests passing
- ✅ **Phase 2**: Conversion mechanics (deescalate/escalate/subdue) - All 13 tests passing, stable IDs verified
- ✅ **Phase 4**: Healing system (apply_healing in mechanics.py) - Integrated with Phase 1

**In Progress:**
- 🔄 **Phase 3**: State tracking (SharedState and TargetIDMapper extensions)

**Remaining:**
- ⏳ Phase 5: Structured output schemas (NPCSpawn, Deescalation, Escalation)
- ⏳ Phase 6: DM integration (process story advancements)
- ⏳ Phase 7: NPC action system (full LLM client implementation)
- ⏳ Phase 8: Integration tests (full scenarios)
- ⏳ Phase 9: Session configs and documentation

**Commits:**
- `dcccfee`: Phase 1 - NPC core data structures and healing system
- `b1ea47c`: Phase 2 - Agent conversion mechanics with stable IDs

## Executive Summary

This document outlines an architectural enhancement to enable:
1. **De-escalation mechanics** - Diplomacy/intimidation can convert enemies to NPCs
2. **Escalation mechanics** - Attacking NPCs converts them to enemies
3. **Non-lethal combat** - Stun/subdue/disable to take prisoners
4. **Healing system** - Medical actions to stabilize wounded (currently missing)
5. **NPC agency** - NPCs have simple LLM clients for natural behavior

### Design Principles
- ✅ **Structured output only** - Use Pydantic schemas, NO marker parsing
- ✅ **Stable agent IDs** - Never change IDs across conversions (critical for JSONL continuity)
- ✅ **Full state preservation** - Health/wounds/conditions/skills identical across conversions
- ✅ **NPC agency** - NPCs have simple LLM clients for flee/hide/plead/dialogue actions
- ✅ **Personality-based targeting** - Enemies can target NPCs based on personality type
- ✅ **Extend existing systems** - Build on morale/surrender/prisoner mechanics already present
- ✅ **Foundation for IFF/ROE** - Sets groundwork for future multi-faction testing (narrative mode)

## Problem Context

### Current Issues (Session `6cecd16d`, Round 3)

**Symptom**: Player attempted de-escalation (Charisma × Guile, succeeded), but:
- Created condition "Tentative Truce" with `penalty=0` (narrative-only)
- No mechanical effect (combat continued unchanged)
- DM narration acknowledged success, but game state didn't reflect it

**Root causes**:
1. No "convert enemy → NPC" pathway
2. No healing system (can't take prisoners without stabilization)
3. No non-lethal combat options (stun/subdue)
4. Binary PC vs Enemy model (no neutral/ally states)

### Existing Systems We Can Build On

From codebase exploration:

**Morale system** (`enemy_agent.py:401-449`):
- `check_morale()` already exists with personality-based outcomes
- Triggers: HP < 25%, critical stuns (5+), last survivor
- Personalities: `fight_to_death`, `surrender_if_cornered`, `flee_when_broken`

**Surrender mechanics** (`enemy_combat.py:1716-1740`):
- `enemy.is_prisoner = True` flag exists
- Can mark surrendered enemies
- No conversion to separate agent type

**Action types** (`schemas/shared_types.py:24-34`):
- `ActionType.SOCIAL` already exists
- `ActionType.SUPPORT` already exists (for healing)

**Existing despawn markers**:
- `FLED`: Scared off, retreated
- `CONVINCED`: Talked down, negotiated
- `SUBDUED`: Knocked unconscious

**Good news**: Core systems (mechanics, rolls, morale) are agent-agnostic. We're extending orchestration, not rewriting fundamentals.

## Design Goals

### Primary Goal: De-escalation UX
Make diplomacy/intimidation mechanically meaningful:
- Successful negotiation converts enemy → NPC
- NPCs can dialogue, receive healing, be escorted
- NPCs react naturally to environment (flee/hide/plead)
- Failure doesn't immediately break diplomacy (multi-round negotiation possible)

### Secondary Goals
1. **Escalation** - Attacking NPCs converts them to enemies
2. **Non-lethal combat** - Stun/subdue mechanics to take prisoners
3. **Healing** - Medical actions to stabilize wounded (currently missing)
4. **Foundation for IFF/ROE** - Prepare for multi-faction dynamic allegiance (future work, narrative mode)

## Proposed Architecture

### Two-Tier Agent Model

```
┌─────────────────────────────────────────┐
│  PLAYER AGENTS (unchanged)              │
│  - Full stats + LLM-controlled          │
│  - Combat-capable by default            │
│  - CharacterState nested object         │
└─────────────────────────────────────────┘
                 ↕ (targeting, dialogue, healing)
┌─────────────────────────────────────────┐
│  NPC AGENTS (NEW)                       │
│  - Full stats (health, soak, skills)    │
│  - Simple LLM client (flee/hide/plead)  │
│  - NO tactics, NO Position              │
│  - Can escalate → Enemy if attacked     │
│  - Can de-escalate ← Enemy via diplomacy│
│  - entity_type: neutral/ally/prisoner   │
│  - faction: (for future IFF/ROE)        │
│  - threat_level: (determines targeting) │
└─────────────────────────────────────────┘
                 ↕ (conversion)
┌─────────────────────────────────────────┐
│  ENEMY AGENTS (minimal changes)         │
│  - Full stats + tactics                 │
│  - Hostile by default                   │
│  - Can de-escalate → NPC via diplomacy  │
│  - Can be subdued → NPC via stun        │
│  - personality: (determines NPC targeting)│
└─────────────────────────────────────────┘
```

**Key insight**: NPCs are NOT a degraded enemy type. They're a separate agent class with different capabilities and behavior patterns.

### Critical Design Decision: Stable Agent IDs

**Problem**: If IDs change during conversion (`enemy_pirate_1` → `npc_pirate_1`), we break:
- Target tracking across rounds
- Condition references
- JSONL event continuity (can't follow same agent)
- Replay logic

**Solution**: Agent IDs are **STABLE** across conversions.

```python
# Example: Wounded pirate surrenders, then is attacked
1. Enemy pirate (agent_id="enemy_freeborn_pirate_1", health=30, wounds=0)
2. Takes damage → (health=12, wounds=2, stuns=1)
3. Surrenders → NPC (agent_id="enemy_freeborn_pirate_1" ✅, health=12, wounds=2, stuns=1)
4. Player attacks NPC → Enemy (agent_id="enemy_freeborn_pirate_1" ✅, health=12, wounds=2, stuns=1)
```

**Same agent_id, same state, different behavior mode.**

## Key Design Decisions

### 1. NPCAgent Structure

```python
class NPCAgent:
    """
    Non-player character with stats and simple LLM client.

    NPCs can:
    - Declare simple actions (flee/hide/plead/dialogue/assist/pass)
    - Be targeted for healing, buffs, conditions
    - Participate in skill checks (persuade them to help)
    - Take damage (triggers escalation → enemy)
    - Dialogue with players via their own LLM

    NPCs cannot:
    - Use combat tactics (no tactical AI)
    - Have Position on tactical grid (exist "off-grid")
    - Declare attack actions (only if escalated to enemy)
    """
    # Identity (STABLE across conversions)
    agent_id: str                      # NEVER changes during conversions
    name: str
    faction: str                       # "Freeborn", "ACG", "Civilian", etc.
    entity_type: Literal["neutral", "ally", "prisoner"]

    # Combat stats (preserved across conversions)
    health: int
    max_health: int
    soak: int                          # Damage reduction
    void_score: int
    skills: Dict[str, int]             # Full skill set
    conditions: List[Condition]        # All buffs/debuffs
    stuns: int
    wounds: int

    # NPC-specific behavior
    llm_client: NPCLLMClient           # Simple action declarations
    disposition: Literal["friendly", "neutral", "wary", "prisoner"]
    threat_level: Literal["non_combatant", "potential_threat", "armed_neutral"]
    description: str                   # Appearance/background

    # Conversion tracking (for reverse operations)
    converted_from_enemy: bool = False
    original_enemy_template: Optional[str] = None
    conversion_history: List[ConversionRecord] = []  # Track all conversions
```

**Stats capability rationale**: NPCs need full stats so they can:
- Be healed by players (stabilize prisoners)
- Receive buffs/conditions
- Take damage (triggers escalation)
- Participate in cooperative skill checks
- Convert back to enemy with identical state

**threat_level determines enemy targeting**:
- `non_combatant`: Most enemies ignore (unless personality="ruthless")
- `potential_threat`: Professional enemies might engage
- `armed_neutral`: Most enemies treat as threat

**faction field**: Future-proofs for IFF/ROE scenarios where hostility is faction-based, not role-based.

### 2. NPC LLM Client (Simple Agency)

**Problem**: Without agency, NPCs feel lifeless. Questions:
- Who decides NPC dialogue when players talk to them?
- What does NPC do when caught in firefight?
- Do NPCs just stand there and die if enemies target them?

**Solution**: NPCs have **simple LLM client** with limited action set.

```python
class NPCLLMClient:
    """Lightweight LLM client for NPC actions."""

    async def declare_action(
        self,
        npc: NPCAgent,
        context: NPCContext  # Simplified context
    ) -> NPCAction:
        """
        Get NPC action with simplified prompt.

        Context includes:
        - Immediate surroundings (not full battlefield)
        - Nearby agents (within 2 zones)
        - Recent events (last 1-2 rounds)
        - Pre-baked faction lore (no dynamic LOOKUP)
        """
```

**NPC Action Types** (limited set):
```python
class NPCAction(BaseModel):
    action_type: Literal["flee", "hide", "plead", "comply", "dialogue", "assist", "pass"]
    description: str  # Freeform action description
    target: Optional[str] = None  # For dialogue/assist
```

**Action descriptions**:
- `flee`: Run away from combat, seek safety
- `hide`: Take cover, become passive
- `plead`: Beg for mercy, surrender
- `comply`: Follow player orders
- `dialogue`: Talk, answer questions, negotiate
- `assist`: Help players (if friendly)
- `pass`: Explicitly do nothing (for ML training)

**Opportunistic acting**: NPCs don't act every round (expensive, unnecessary).

```python
def should_npc_act(npc: NPCAgent, context: Dict) -> bool:
    """
    Determine if NPC should act this round.

    Act if:
    - Targeted by action this round
    - Enemy within immediate range
    - Player addresses NPC directly
    - Combat started/ended
    - Situation changed dramatically

    Pass if:
    - Safe and ignored
    - Already hiding/complying
    - No meaningful options
    """
```

**Cost estimate**:
- NPC prompt: ~500 tokens (vs ~2000 for player)
- Acts every 2-3 rounds typically (not every round)
- 3 NPCs, 10-round session: ~15 LLM calls = ~7,500 tokens
- Cost: ~$0.02 per session (30% more calls, acceptable)

**No LOOKUP capability**: NPCs don't use ChromaDB knowledge retrieval (expensive, unnecessary). Instead, pre-bake faction-specific lore directly into NPC prompts:
```python
if npc.faction == "ACG":
    prompt_context = "You're ACG. Contracts are sacred, breach of bond is unforgivable."
```

### 3. Conversion System

**Enemy → NPC (De-escalation)**:
```python
def deescalate_enemy_to_npc(
    enemy: EnemyAgent,
    disposition: Literal["friendly", "neutral", "wary", "prisoner"]
) -> NPCAgent:
    """
    Convert enemy to NPC after successful diplomacy/intimidation.

    Preserves (IDENTICAL state):
    - agent_id (STABLE - never changes)
    - Stats (health, soak, skills, void_score)
    - Current damage (stuns, wounds)
    - Conditions (all buffs/debuffs)
    - Faction

    Removes:
    - Tactics (no longer combat AI)
    - Position (removed from tactical grid)
    - Enemy LLM client (if any)

    Adds:
    - NPC LLM client (simple action declarations)
    - entity_type (neutral/ally/prisoner)
    - threat_level (determines enemy targeting)
    - Disposition (behavior guide)
    - Conversion tracking
    """
    npc = NPCAgent(
        agent_id=enemy.agent_id,  # ✅ STABLE ID
        entity_type=f"npc_{disposition}",
        name=enemy.name,
        faction=enemy.faction,

        # Copy ALL state (not just some)
        health=enemy.health,
        max_health=enemy.max_health,
        soak=enemy.soak,
        void_score=enemy.void_score,
        skills=enemy.skills.copy(),  # Full skill set
        conditions=enemy.conditions.copy(),  # ALL conditions
        stuns=enemy.stuns,
        wounds=enemy.wounds,

        # NPC-specific
        disposition=disposition,
        threat_level=determine_threat_level(enemy),
        llm_client=NPCLLMClient(...),
        description=f"Former {enemy.template_name}, now {disposition}",

        # Conversion tracking (for reverse operation)
        converted_from_enemy=True,
        original_enemy_template=enemy.template_name,
        conversion_history=[ConversionRecord(...)]
    )
    return npc
```

**NPC → Enemy (Escalation)**:
```python
def escalate_npc_to_enemy(
    npc: NPCAgent,
    template_override: Optional[str] = None
) -> EnemyAgent:
    """
    Convert NPC to enemy after being attacked/threatened.

    Preserves (IDENTICAL state):
    - agent_id (STABLE)
    - Stats, damage, conditions

    Adds:
    - Tactics (use original template or "desperate_fighter" default)
    - Position (spawn at Near-Enemy or context-appropriate)
    - Combat AI (enemy action declarations)
    """
    # Reuse original template tactics if NPC was converted from enemy
    template = template_override or npc.original_enemy_template or "desperate_fighter"

    enemy = EnemyAgent(
        agent_id=npc.agent_id,  # ✅ STABLE ID
        name=npc.name,
        faction=npc.faction,

        # Copy ALL state
        health=npc.health,
        max_health=npc.max_health,
        soak=npc.soak,
        void_score=npc.void_score,
        skills=npc.skills.copy(),
        conditions=npc.conditions.copy(),
        stuns=npc.stuns,
        wounds=npc.wounds,

        # Enemy-specific
        template_name=template,
        tactics=load_tactics(template),
        personality=derive_personality(template)
    )
    return enemy
```

**Prisoner → NPC (Subdue)**:
```python
def subdue_enemy_to_prisoner(
    enemy: EnemyAgent
) -> NPCAgent:
    """
    Convert enemy to prisoner via non-lethal takedown (stun, subdue).

    Special entity_type: "prisoner" (distinct from neutral/ally).
    Prisoners are restrained, cannot act independently.

    Triggers when:
    - Enemy reduced to 0 HP via stun damage + capture_intent
    - Successful "subdue" action (new action type)
    - Successful "capture" after enemy flees/surrenders
    """
    return deescalate_enemy_to_npc(
        enemy,
        disposition="prisoner"
    )
```

### 4. Targeting System

**Who can target whom**:
```
Player   → PC, NPC, Enemy (universal targeting)
Enemy    → PC, NPC (based on personality)
NPC      → No one (non-combatant, can only flee/hide/dialogue)
```

**Enemy targeting logic** (personality-based):
```python
def get_valid_targets(enemy: EnemyAgent) -> List[str]:
    """Get valid targets based on personality."""
    targets = all_player_ids  # Always can target PCs

    if enemy.personality == "ruthless":
        # Target anyone (PCs + all NPCs)
        targets += all_npc_ids
    elif enemy.personality == "professional":
        # Target threats only (PCs + armed NPCs)
        targets += [
            npc.id for npc in npcs
            if npc.threat_level in ["potential_threat", "armed_neutral"]
        ]
    # else: Only PCs (default)

    return targets
```

**Personality types** (need to add to enemy templates):
- `professional`: Trained soldiers, ignore non-combatants
- `ruthless`: Pirates/raiders, target anyone
- `defensive`: Guards, only engage active threats (PCs only)

**Spawn config changes** (allow personality override):
```json
{
  "template": "freeborn_pirate",
  "count": 2,
  "personality": "ruthless",  // NEW: Optional override
  "initial_morale": 10         // NEW: Optional morale modifier
}
```

### 5. Morale System Extension

**Existing system** (`enemy_agent.py:401-449`):
- Automatic triggers: HP < 25%, critical stuns (5+), last survivor
- Personality-based outcomes: surrender, flee, or keep fighting
- Check: Willpower + d20 vs DC 15

**Extension**: Add player-triggered morale checks.

**New triggers**:
- `"player_intimidation"` - Charisma × Charm action
- `"player_negotiation"` - Empathy × Charm or Corporate Influence
- `"player_leverage"` - Intelligence × Debt Law (contract-based)

**Voluntary surrender** (DM decision):
- DM can mark enemy as surrendering via `Deescalation` in `StoryAdvancement`
- No morale check required if narrative warrants it
- Preserves "latitude for AI interpretation" philosophy

**DC guidance** (aligned with existing intimidation prompts):
- DC 15: Grunts, thugs, low morale
- DC 20: Trained soldiers, determined enemies
- DC 25: Elites, fanatics, ideological commitment

**Modifiers**:
- Wounded (HP < 50%): -5
- Critically wounded (HP < 25%): -10
- Allies defeated: -5 per ally
- Outnumbered 2:1 or more: -5
- Player has leverage (hostage, intel, contract): -10
- Ideological conflict: +5 to +15

### 6. Skill System (Corrected)

**WRONG (from original design doc)**:
- ❌ "Presence × Guile" - Presence doesn't exist
- ❌ "Presence check" - Not a real skill

**CORRECT (from Aeonisk YAGS implementation)**:

**Social skills**:
- **Empathy × Charm** - Core social interaction, persuasion
- **Charisma × Charm** - Intimidation (everyone has Charm 2!)
- **Empathy × Guile** - Deception, manipulation
- **Empathy × Corporate Influence** - Faction negotiation, extracting favors
- **Intelligence × Debt Law** - Contract/oath leverage, Soulcredit manipulation
- **Empathy × Counsel** - Alternative social skill (mentioned in prompts)

**Critical insight: Unskilled Empathy checks are terrible**:
- Empathy 3 (average) × 0 (unskilled) = 0
- Unskilled penalty: Result halved, fumble chance doubled
- Expected range: (d20 / 2) = 0.5-10 vs DC 15-20
- **Success rate: 5-15%** (mathematically unfavorable)

**This explains why players struggle with de-escalation!**

**Accessible alternative: Intimidation**:
- Everyone has Charm 2 (core talent)
- Charisma × Charm = base of 6-8 for average character
- Much higher success rate than unskilled Empathy

**Action type for social actions**: Use existing `ActionType.SOCIAL` with skill-based resolution.

### 7. Healing System

**Current gap**: No healing actions exist in the game.

**New action type**: Use existing `ActionType.SUPPORT` with skill checks.

**Healing mechanics** (new in `mechanics.py`):
```python
def apply_healing(
    target: Union[AIPlayerAgent, EnemyAgent, NPCAgent],
    amount: int,
    heal_type: Literal["stun", "wound", "hp"]
) -> Dict[str, Any]:
    """
    Heal target agent.

    heal_type:
    - "stun": Remove stun damage (fast recovery, field medicine)
    - "wound": Reduce wound penalties (surgery-equivalent, requires tools)
    - "hp": Restore health (medical treatment, bandaging)

    Returns:
    - amount_healed: Actual HP restored (capped at max_health)
    - stuns_removed: Number of stuns cleared
    - wounds_treated: Wounds reduced
    """
    if heal_type == "stun":
        stuns_before = target.stuns
        target.stuns = max(0, target.stuns - amount)
        return {"stuns_removed": stuns_before - target.stuns}

    elif heal_type == "wound":
        wounds_before = target.wounds
        target.wounds = max(0, target.wounds - amount)
        return {"wounds_treated": wounds_before - target.wounds}

    elif heal_type == "hp":
        hp_before = target.health
        target.health = min(target.max_health, target.health + amount)
        return {"amount_healed": target.health - hp_before}
```

**Skill check**: Intelligence × Medicine (or similar).

**Example healing actions**:
1. **"stabilize"** - Field medicine to prevent death (Medicine check, DC 15)
2. **"heal"** - Restore HP/remove stuns (Medicine check, DC 15-20, takes time/resources)
3. **"treat_wounds"** - Reduce wound penalties (Surgery-equivalent, requires tools, DC 20-25)

**Healing targets**: Any agent (PCs, NPCs, enemies if non-hostile).

**No resource cost initially**: Skill check determines success/amount. Can add medkit costs later if balance requires.

## Structured Output Schema Changes

### New Schemas

**1. NPCSpawn** (in `schemas/story_events.py`):
```python
class NPCSpawn(BaseModel):
    """
    Spawn an NPC into the scene.

    Use when:
    - Introducing non-combatant characters
    - Enemy surrenders/negotiates (DM marks conversion)
    - Scene requires dialogue NPCs
    """
    name: str = Field(..., min_length=3, max_length=50)
    faction: str = Field(..., description="NPC's faction/allegiance")
    entity_type: Literal["neutral", "ally", "prisoner"] = Field(
        ...,
        description="NPC's relation to players"
    )
    threat_level: Literal["non_combatant", "potential_threat", "armed_neutral"] = Field(
        "non_combatant",
        description="Determines enemy targeting behavior"
    )
    disposition: Literal["friendly", "neutral", "wary", "prisoner"] = Field(
        ...,
        description="NPC's attitude toward players"
    )
    description: str = Field(..., min_length=20, max_length=300)
    health: int = Field(..., ge=1, le=100)
    soak: int = Field(..., ge=0, le=20)
    skills: Dict[str, int] = Field(
        default_factory=dict,
        description="Key skills (for cooperative checks)"
    )

    # Optional: conversion tracking
    converted_from_enemy_id: Optional[str] = None
```

**2. Deescalation** (conversion event):
```python
class Deescalation(BaseModel):
    """
    Convert enemy to NPC via diplomacy/intimidation/voluntary surrender.

    Use when:
    - Successful negotiation/surrender
    - Enemy convinced to stand down
    - Intimidation causes flee/withdrawal
    - Morale breaks and enemy surrenders
    """
    enemy_id: str = Field(..., description="Enemy to convert (agent_id is preserved)")
    resulting_entity_type: Literal["neutral", "ally", "prisoner"] = Field(
        ...,
        description="NPC entity type after conversion"
    )
    resulting_disposition: Literal["friendly", "neutral", "wary", "prisoner"] = Field(
        ...,
        description="NPC disposition after conversion"
    )
    reason: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="Why enemy de-escalated"
    )
```

**3. Escalation**:
```python
class Escalation(BaseModel):
    """
    Convert NPC to enemy after provocation.

    Use when:
    - NPC is attacked
    - NPC is severely threatened
    - NPC's faction is attacked and they choose to defend

    DM decides when escalation happens (not automatic).
    """
    npc_id: str = Field(..., description="NPC to convert (agent_id is preserved)")
    reason: str = Field(..., min_length=20, max_length=300)
    template: str = Field(
        "desperate_fighter",
        description="Enemy template for tactics (default: desperate_fighter)"
    )
```

**4. AgentConversion** (JSONL logging event):
```python
class AgentConversion(BaseModel):
    """
    Log agent conversions for ML training and replay.

    Critical: agent_id is STABLE across conversions.
    """
    event_type: Literal["agent_conversion"] = "agent_conversion"
    round: int
    agent_id: str  # STABLE - same before and after
    from_type: Literal["enemy", "npc"]
    to_type: Literal["enemy", "npc"]
    trigger: str  # "morale_break", "player_intimidation", "player_attack", "voluntary"

    # State snapshot (for verification/replay)
    state_snapshot: Dict[str, Any] = Field(
        description="Health, stuns, wounds, conditions at conversion"
    )
```

### Modified Schemas

**ActionResolution** (add capture/heal fields):
```python
class ActionResolution(BaseModel):
    # ... existing fields

    # NEW: Capture intent for non-lethal takedowns
    capture_intent: Optional[bool] = Field(
        None,
        description="True if using non-lethal force to capture"
    )

    # NEW: Healing effects
    healing: Optional[List[HealingEffect]] = Field(
        None,
        description="Healing applied to targets"
    )
```

**StoryAdvancement** (add NPC spawning/conversion):
```python
class StoryAdvancement(BaseModel):
    # ... existing fields (narration, new_void_level, etc.)

    # NEW: NPC spawning
    npcs_spawned: Optional[List[NPCSpawn]] = None

    # NEW: Conversions
    deescalations: Optional[List[Deescalation]] = None
    escalations: Optional[List[Escalation]] = None
```

**HealingEffect** (new in `schemas/action_effects.py`):
```python
class HealingEffect(BaseModel):
    """Track healing applied to target."""
    target: str = Field(..., description="Target agent ID")
    heal_type: Literal["stun", "wound", "hp"]
    amount: int = Field(..., ge=0, description="Amount healed")
    source: Optional[str] = Field(None, description="Healing source (medkit, skill, offering)")
```

## JSONL Logging

### NPCs Use Same Event Types

**Key insight**: NPCs use existing `action_declaration` and `action_resolution` events.

**New fields distinguish behavior**:
- `agent_type: Literal["player", "enemy", "npc"]` - Who declared action
- `entity_type: Literal["neutral", "ally", "prisoner"]` - For NPCs specifically

**Example: NPC declares action**:
```json
{
  "event_type": "action_declaration",
  "round": 3,
  "agent_id": "enemy_freeborn_pirate_1",
  "agent_type": "npc",
  "entity_type": "npc_neutral",
  "action_type": "flee",
  "description": "I run for cover behind the cargo crates, hands raised"
}
```

**Example: DM resolves NPC action**:
```json
{
  "event_type": "action_resolution",
  "round": 3,
  "agent_id": "enemy_freeborn_pirate_1",
  "agent_type": "npc",
  "success": true,
  "narration": "The pirate scrambles behind cover, clearly terrified..."
}
```

**Benefits**:
- Same JSONL schema (no special case)
- Can track same agent across conversions via stable `agent_id`
- ML training sees NPC behavior patterns
- Replay logic works unchanged

### New Event: agent_conversion

**Purpose**: Track conversions for ML training and replay.

**Example**: Enemy surrenders:
```json
{
  "event_type": "agent_conversion",
  "round": 4,
  "agent_id": "enemy_freeborn_pirate_1",
  "from_type": "enemy",
  "to_type": "npc",
  "trigger": "player_intimidation",
  "state_snapshot": {
    "health": 12,
    "max_health": 30,
    "stuns": 1,
    "wounds": 2,
    "conditions": ["Shaken"]
  }
}
```

**Example**: NPC escalates after attack:
```json
{
  "event_type": "agent_conversion",
  "round": 7,
  "agent_id": "enemy_freeborn_pirate_1",
  "from_type": "npc",
  "to_type": "enemy",
  "trigger": "player_attack",
  "state_snapshot": {
    "health": 12,
    "max_health": 30,
    "stuns": 1,
    "wounds": 2,
    "conditions": ["Shaken"]
  }
}
```

**Critical**: Same `agent_id` in both events shows it's the same character.

## Implementation Plan

### Phase 1: Core Data Structures (TDD)

**Test file**: `tests/unit/test_npc_agent.py`

Write tests FIRST:
```python
def test_npc_agent_creation():
    """NPCs have stats but no tactics/Position."""
    npc = NPCAgent(
        agent_id="enemy_pirate_1",  # Note: can be enemy_xxx ID
        name="Freeborn Pirate",
        faction="Freeborn",
        entity_type="neutral",
        health=20,
        soak=2
    )
    assert npc.health == 20
    assert not hasattr(npc, 'tactics')
    assert not hasattr(npc, 'position')

def test_npc_can_take_damage():
    """NPCs can be damaged (triggers escalation potential)."""
    npc = NPCAgent(name="Bystander", health=20, soak=2, ...)
    apply_stun_damage(npc, 15)
    assert npc.stuns > 0

def test_npc_can_be_healed():
    """NPCs can receive healing."""
    npc = NPCAgent(name="Injured Civilian", health=10, max_health=20, ...)
    result = apply_healing(npc, amount=5, heal_type="hp")
    assert npc.health == 15
    assert result["amount_healed"] == 5
```

**Implementation**:
1. Create `scripts/aeonisk/multiagent/npc_agent.py`
2. Create `NPCAgent` class (structure shown above)
3. Create `NPCLLMClient` class (simple action declarations)
4. Create `NPCAction` schema

### Phase 2: Conversion Mechanics

**Test file**: `tests/unit/test_agent_conversion.py`

Write tests FIRST:
```python
def test_deescalate_enemy_to_npc_preserves_id():
    """Critical: agent_id never changes during conversion."""
    enemy = EnemyAgent(
        agent_id="enemy_raider_1",
        name="Raider",
        health=30,
        soak=5
    )
    npc = deescalate_enemy_to_npc(enemy, disposition="neutral")

    assert npc.agent_id == "enemy_raider_1"  # ✅ STABLE
    assert npc.name == "Raider"
    assert npc.health == 30
    assert npc.soak == 5
    assert npc.entity_type == "neutral"
    assert not hasattr(npc, 'tactics')
    assert npc.converted_from_enemy == True

def test_deescalate_preserves_all_state():
    """Wounds, stuns, conditions preserved exactly."""
    enemy = EnemyAgent(
        agent_id="enemy_guard_1",
        health=15,
        max_health=30,
        stuns=2,
        wounds=1,
        conditions=[Condition(name="Bleeding", penalty=-2)]
    )
    npc = deescalate_enemy_to_npc(enemy, disposition="prisoner")

    assert npc.health == 15
    assert npc.stuns == 2
    assert npc.wounds == 1
    assert len(npc.conditions) == 1
    assert npc.conditions[0].name == "Bleeding"

def test_escalate_npc_to_enemy_preserves_id():
    """Escalation also preserves agent_id."""
    npc = NPCAgent(
        agent_id="enemy_bystander_1",
        name="Bystander",
        health=20,
        original_enemy_template="desperate_fighter"
    )
    enemy = escalate_npc_to_enemy(npc)

    assert enemy.agent_id == "enemy_bystander_1"  # ✅ STABLE
    assert enemy.name == "Bystander"
    assert enemy.health == 20
    assert hasattr(enemy, 'tactics')
    assert enemy.template_name == "desperate_fighter"

def test_conversion_history_tracked():
    """Conversions are logged for replay."""
    enemy = EnemyAgent(agent_id="enemy_pirate_1", ...)
    npc = deescalate_enemy_to_npc(enemy, disposition="neutral")

    assert len(npc.conversion_history) == 1
    assert npc.conversion_history[0].from_type == "enemy"
    assert npc.conversion_history[0].to_type == "npc"
```

**Implementation**:
1. Create `scripts/aeonisk/multiagent/agent_conversion.py`
2. Implement `deescalate_enemy_to_npc()`
3. Implement `escalate_npc_to_enemy()`
4. Implement `subdue_enemy_to_prisoner()`
5. Add `ConversionRecord` schema

### Phase 3: State Tracking & Targeting

**Test file**: `tests/unit/test_shared_state_npcs.py`

Write tests FIRST:
```python
def test_shared_state_tracks_npcs():
    """SharedState maintains NPC pool."""
    state = SharedState()
    npc = NPCAgent(agent_id="enemy_guide_1", name="Guide", ...)
    state.add_npc(npc)
    assert len(state.npc_agents) == 1

def test_shared_state_tracks_entities():
    """SharedState can find agents across pools."""
    state = SharedState()
    player = create_test_player(agent_id="player_01")
    enemy = create_test_enemy(agent_id="enemy_raider_1")
    npc = NPCAgent(agent_id="enemy_guide_1", ...)

    state.add_player(player)
    state.add_enemy(enemy)
    state.add_npc(npc)

    # Can find by ID regardless of pool
    assert state.get_agent("player_01") == player
    assert state.get_agent("enemy_raider_1") == enemy
    assert state.get_agent("enemy_guide_1") == npc

def test_get_all_targetable():
    """SharedState returns all targetable agents."""
    state = SharedState()
    state.add_player(player)
    state.add_npc(npc)
    state.add_enemy(enemy)

    all_targets = state.get_all_targetable()
    assert len(all_targets) == 3
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/shared_state.py`
2. Add `npc_agents: List[NPCAgent] = []`
3. Add methods: `add_npc()`, `remove_npc()`, `get_npc()`, `get_npc_by_id()`
4. Add `get_agent(agent_id: str) -> Union[Player, Enemy, NPC]` (cross-pool lookup)
5. Modify `get_all_targetable()` to include NPCs

**Test file**: `tests/unit/test_target_ids_npcs.py`

Write tests FIRST:
```python
def test_npc_keeps_stable_id():
    """NPCs can use enemy_xxx IDs (stable across conversions)."""
    mapper = TargetIDMapper()
    npc = NPCAgent(agent_id="enemy_pirate_1", name="Surrendered Pirate", ...)

    # Mapper should recognize this as valid NPC
    assert mapper.is_valid_target("enemy_pirate_1")
    assert mapper.get_agent_type("enemy_pirate_1") == "npc"

def test_can_target_npc():
    """Players can target NPCs."""
    mapper = TargetIDMapper()
    assert mapper.can_target("player_01", "enemy_npc_1") == True

def test_enemy_can_target_npc_if_ruthless():
    """Ruthless enemies can target NPCs."""
    mapper = TargetIDMapper()
    enemy = EnemyAgent(agent_id="enemy_raider_1", personality="ruthless", ...)
    npc = NPCAgent(agent_id="enemy_guide_1", threat_level="non_combatant", ...)

    assert mapper.can_target_with_personality(
        enemy.agent_id,
        npc.agent_id,
        enemy.personality,
        npc.threat_level
    ) == True

def test_enemy_cannot_target_npc_if_professional():
    """Professional enemies ignore non-combatant NPCs."""
    enemy = EnemyAgent(agent_id="enemy_soldier_1", personality="professional", ...)
    npc = NPCAgent(agent_id="enemy_civilian_1", threat_level="non_combatant", ...)

    assert mapper.can_target_with_personality(
        enemy.agent_id,
        npc.agent_id,
        enemy.personality,
        npc.threat_level
    ) == False

def test_get_agent_type():
    """New method returns agent type from ID."""
    mapper = TargetIDMapper()
    assert mapper.get_agent_type("player_01") == "player"
    assert mapper.get_agent_type("enemy_raider_1") == "enemy"
    assert mapper.get_agent_type("enemy_guide_1") == "npc"  # If registered as NPC
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/target_ids.py`
2. Add NPC tracking to TargetIDMapper
3. Update `is_valid_target()` to include NPCs
4. Add `get_agent_type(target_id: str) -> Literal["player", "enemy", "npc"]`
5. Add `can_target_with_personality()` for enemy→NPC targeting
6. Support stable IDs (NPCs can have enemy_xxx IDs)

### Phase 4: Healing System

**Test file**: `tests/unit/test_healing.py`

Write tests FIRST:
```python
def test_heal_hp_on_player():
    """Healing restores HP to players."""
    player = create_test_player(health=10, max_health=30)
    result = apply_healing(player, amount=15, heal_type="hp")

    assert player.health == 25
    assert result["amount_healed"] == 15

def test_heal_hp_capped_at_max():
    """Healing cannot exceed max HP."""
    player = create_test_player(health=25, max_health=30)
    result = apply_healing(player, amount=20, heal_type="hp")

    assert player.health == 30
    assert result["amount_healed"] == 5

def test_remove_stun_damage():
    """Healing can remove stun damage."""
    enemy = create_test_enemy(stuns=3)
    result = apply_healing(enemy, amount=2, heal_type="stun")

    assert enemy.stuns == 1
    assert result["stuns_removed"] == 2

def test_treat_wounds():
    """Healing can reduce wound penalties."""
    player = create_test_player(wounds=2)
    result = apply_healing(player, amount=1, heal_type="wound")

    assert player.wounds == 1
    assert result["wounds_treated"] == 1

def test_heal_npc():
    """NPCs can be healed (key for prisoner stabilization)."""
    npc = NPCAgent(name="Injured Civilian", health=5, max_health=20, ...)
    result = apply_healing(npc, amount=10, heal_type="hp")

    assert npc.health == 15
```

**Implementation**:
1. Add to `scripts/aeonisk/multiagent/mechanics.py`
2. Implement `apply_healing()` function (signature above)
3. Support all agent types (Player, Enemy, NPC)

### Phase 5: Structured Output Schemas

**Test file**: `tests/unit/test_story_events_npcs.py`

Write tests FIRST:
```python
def test_npc_spawn_schema_validation():
    """NPCSpawn validates correctly."""
    spawn = NPCSpawn(
        name="Pirate Captain",
        faction="Freeborn",
        entity_type="neutral",
        threat_level="armed_neutral",
        disposition="wary",
        description="Scarred woman with void tattoos",
        health=25,
        soak=3,
        skills={"guile": 5}
    )
    assert spawn.name == "Pirate Captain"
    assert spawn.entity_type == "neutral"

def test_deescalation_schema_validation():
    """Deescalation validates correctly."""
    deesc = Deescalation(
        enemy_id="enemy_raider_1",
        resulting_entity_type="neutral",
        resulting_disposition="neutral",
        reason="Convinced to stand down"
    )
    assert deesc.resulting_entity_type == "neutral"

def test_escalation_schema_validation():
    """Escalation validates correctly."""
    esc = Escalation(
        npc_id="enemy_civilian_1",
        reason="Attacked by player",
        template="desperate_fighter"
    )
    assert esc.template == "desperate_fighter"

def test_agent_conversion_event_schema():
    """AgentConversion logs conversion with stable ID."""
    conversion = AgentConversion(
        round=4,
        agent_id="enemy_pirate_1",
        from_type="enemy",
        to_type="npc",
        trigger="player_intimidation",
        state_snapshot={"health": 12, "stuns": 1}
    )
    assert conversion.agent_id == "enemy_pirate_1"
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/schemas/story_events.py`
2. Add `NPCSpawn` schema
3. Add `Deescalation` schema
4. Add `Escalation` schema
5. Add `AgentConversion` schema (for JSONL logging)
6. Modify `StoryAdvancement` to include NPC fields
7. Modify `ActionResolution` to include `capture_intent` and `healing` fields
8. Add `HealingEffect` schema to `schemas/action_effects.py`

### Phase 6: DM Integration

**Test file**: `tests/unit/test_dm_npc_handling.py`

Write tests FIRST:
```python
def test_dm_spawns_npc_from_structured_output():
    """DM processes NPCSpawn from structured output."""
    story_adv = StoryAdvancement(
        narration="A guide approaches",
        npcs_spawned=[NPCSpawn(
            name="Guide",
            faction="Freeborn",
            entity_type="neutral",
            disposition="neutral",
            ...
        )]
    )

    dm._process_story_advancement(story_adv)

    assert len(shared_state.npc_agents) == 1
    assert shared_state.npc_agents[0].name == "Guide"

def test_dm_converts_enemy_to_npc_preserves_id():
    """DM processes Deescalation, preserves agent_id."""
    # Setup: enemy exists
    enemy = create_test_enemy(agent_id="enemy_raider_1", health=30)
    shared_state.add_enemy(enemy)

    story_adv = StoryAdvancement(
        narration="The raider lowers his weapon",
        deescalations=[Deescalation(
            enemy_id="enemy_raider_1",
            resulting_entity_type="neutral",
            resulting_disposition="neutral",
            reason="Convinced"
        )]
    )

    dm._process_story_advancement(story_adv)

    # Verify conversion
    assert len(shared_state.enemy_agents) == 0
    assert len(shared_state.npc_agents) == 1
    assert shared_state.npc_agents[0].agent_id == "enemy_raider_1"  # ✅ STABLE
    assert shared_state.npc_agents[0].health == 30  # Preserved

def test_dm_converts_npc_to_enemy_preserves_id():
    """DM processes Escalation, preserves agent_id."""
    npc = NPCAgent(agent_id="enemy_civilian_1", name="Bystander", health=20, ...)
    shared_state.add_npc(npc)

    story_adv = StoryAdvancement(
        narration="The civilian grabs a weapon in panic",
        escalations=[Escalation(
            npc_id="enemy_civilian_1",
            reason="Attacked",
            template="desperate_fighter"
        )]
    )

    dm._process_story_advancement(story_adv)

    assert len(shared_state.npc_agents) == 0
    assert len(shared_state.enemy_agents) == 1
    assert shared_state.enemy_agents[0].agent_id == "enemy_civilian_1"  # ✅ STABLE
    assert shared_state.enemy_agents[0].health == 20  # Preserved

def test_dm_logs_conversion_event():
    """DM logs agent_conversion to JSONL."""
    enemy = create_test_enemy(agent_id="enemy_raider_1", health=15, stuns=1)
    shared_state.add_enemy(enemy)

    story_adv = StoryAdvancement(
        deescalations=[Deescalation(
            enemy_id="enemy_raider_1",
            resulting_entity_type="prisoner",
            resulting_disposition="prisoner",
            reason="Surrendered"
        )]
    )

    dm._process_story_advancement(story_adv)

    # Check JSONL log
    last_event = mechanics.jsonl_logger.events[-1]
    assert last_event["event_type"] == "agent_conversion"
    assert last_event["agent_id"] == "enemy_raider_1"
    assert last_event["from_type"] == "enemy"
    assert last_event["to_type"] == "npc"
    assert last_event["state_snapshot"]["health"] == 15
```

**Implementation**:
1. Modify `scripts/aeonisk/multiagent/dm.py`
2. Update `_process_story_advancement()` to handle:
   - `npcs_spawned` (create NPCAgent, add to SharedState, assign LLM client)
   - `deescalations` (call `deescalate_enemy_to_npc()`, swap in SharedState, log conversion)
   - `escalations` (call `escalate_npc_to_enemy()`, swap in SharedState, log conversion)
3. Add helper methods:
   - `_spawn_npc(spawn: NPCSpawn) -> NPCAgent`
   - `_handle_deescalation(deesc: Deescalation)`
   - `_handle_escalation(esc: Escalation)`
   - `_log_conversion(from_agent, to_agent, trigger)`

### Phase 7: NPC Action System

**Test file**: `tests/unit/test_npc_actions.py`

Write tests FIRST:
```python
def test_npc_declares_action():
    """NPCs can declare simple actions."""
    npc = NPCAgent(agent_id="enemy_guide_1", name="Guide", ...)
    context = create_test_context(nearby_enemies=["enemy_raider_1"])

    action = await npc.llm_client.declare_action(npc, context)

    assert action.action_type in ["flee", "hide", "plead", "comply", "dialogue", "assist", "pass"]
    assert len(action.description) > 0

def test_should_npc_act_opportunistic():
    """NPCs skip turns when nothing interesting happening."""
    npc = NPCAgent(agent_id="enemy_civilian_1", entity_type="neutral", ...)

    # Safe context - should not act
    context = {"nearby_enemies": [], "targeted": False, "combat_active": False}
    assert should_npc_act(npc, context) == False

    # Threatened context - should act
    context = {"nearby_enemies": ["enemy_raider_1"], "targeted": False, "combat_active": True}
    assert should_npc_act(npc, context) == True

def test_npc_action_logged():
    """NPC actions logged with agent_type='npc'."""
    npc = NPCAgent(agent_id="enemy_guide_1", ...)
    action = NPCAction(action_type="flee", description="I run for cover")

    session._log_npc_action_declaration(npc, action)

    last_event = mechanics.jsonl_logger.events[-1]
    assert last_event["event_type"] == "action_declaration"
    assert last_event["agent_type"] == "npc"
    assert last_event["entity_type"] == npc.entity_type
    assert last_event["agent_id"] == "enemy_guide_1"
```

**Implementation**:
1. Implement `NPCLLMClient` in `scripts/aeonisk/multiagent/npc_llm_client.py`
2. Create NPC prompt template (simple, ~500 tokens)
3. Implement `should_npc_act()` logic
4. Integrate into session round flow (between player and enemy actions)
5. Add JSONL logging for NPC actions

### Phase 8: Integration Testing

**Test file**: `tests/integration/test_deescalation_flow.py`

Write integration test:
```python
def test_full_deescalation_scenario():
    """
    End-to-end test: Player negotiates with enemy, converts to NPC.

    Scenario:
    1. Session starts with hostile pirates
    2. Player declares intimidation action
    3. DM resolves with Deescalation in structured output
    4. Enemy converts to NPC (same agent_id)
    5. Player can heal the NPC
    """
    config = load_session_config("session_config_deescalation_test.json")
    session = create_test_session(config)

    # Initial state: 2 hostile pirates
    assert len(session.enemy_agents) == 2
    enemy_id = session.enemy_agents[0].agent_id

    # Player action: intimidate
    player_action = {
        "agent_id": "player_01",
        "action": "Intimidate pirates with show of force",
        "skill": "charm",
        "action_type": "social"
    }

    dm_response = session.process_player_action(player_action)

    # Verify conversion (one pirate surrenders)
    assert len(session.enemy_agents) == 1
    assert len(session.npc_agents) == 1
    assert session.npc_agents[0].agent_id == enemy_id  # ✅ STABLE ID
    assert session.npc_agents[0].entity_type == "prisoner"

    # Player heals the NPC
    heal_action = {
        "agent_id": "player_01",
        "action": "Apply medkit to injured pirate",
        "target": enemy_id,  # Same ID!
        "action_type": "support"
    }

    dm_response = session.process_player_action(heal_action)

    # Verify healing applied
    assert session.npc_agents[0].health > initial_health
```

**Test file**: `tests/integration/test_npc_behavior.py`

```python
def test_npc_flees_from_combat():
    """NPCs react naturally to danger."""
    session = create_test_session_with_npc("Civilian", entity_type="neutral")

    # Spawn enemy near NPC
    enemy = create_test_enemy(agent_id="enemy_raider_1")
    session.add_enemy(enemy)

    # Process round - NPC should act (flee or hide)
    npc_action = session.get_npc_action(session.npc_agents[0])

    assert npc_action.action_type in ["flee", "hide", "plead"]

def test_npc_dialogue_with_player():
    """NPCs can dialogue when addressed."""
    session = create_test_session_with_npc("Guide", entity_type="ally")

    player_action = {
        "agent_id": "player_01",
        "action": "Ask guide about vault location",
        "target": "enemy_guide_1",
        "action_type": "social"
    }

    dm_response = session.process_player_action(player_action)

    # DM narration should include NPC response
    assert "vault" in dm_response.narration.lower()
```

### Phase 9: Session Configs & Documentation

**Create test configs**:

1. `scripts/session_configs/session_config_deescalation_test.json`:
```json
{
  "session_name": "De-escalation Test",
  "max_turns": 3,
  "party_size": 2,
  "scenario": {
    "theme": "negotiation",
    "_scenario_hint": "Hostile Freeborn pirates, player must negotiate to avoid combat"
  },
  "initial_enemies": [
    {
      "template": "freeborn_pirate",
      "count": 2,
      "personality": "professional"
    }
  ]
}
```

2. `scripts/session_configs/session_config_capture_test.json`:
```json
{
  "session_name": "Prisoner Capture Test",
  "max_turns": 3,
  "scenario": {
    "theme": "stealth",
    "_scenario_hint": "Players infiltrate ACG facility, must capture guard for intel"
  },
  "initial_enemies": [
    {
      "template": "acg_security_guard",
      "count": 1,
      "personality": "defensive"
    }
  ]
}
```

3. `scripts/session_configs/session_config_npc_native_spawn_test.json`:
```json
{
  "session_name": "Native NPC Spawn Test",
  "max_turns": 2,
  "scenario": {
    "theme": "investigation",
    "_scenario_hint": "Players meet Freeborn guide who can help navigate void-corrupted station"
  },
  "starting_npcs": [
    {
      "name": "Freeborn Navigator",
      "faction": "Freeborn",
      "entity_type": "ally",
      "threat_level": "non_combatant",
      "disposition": "friendly",
      "description": "Experienced void navigator with neural optics",
      "health": 20,
      "soak": 2,
      "skills": {"perception": 5, "astral_arts": 3}
    }
  ]
}
```

**Update documentation**:

Add to `CLAUDE.md`:
```markdown
## NPC and De-escalation System

### Agent Types

**Players** - PC agents with full LLM control
**Enemies** - Hostile combatants with tactical AI
**NPCs** - Non-combatant agents with simple LLM (flee/hide/plead/dialogue)

### Conversion System

**De-escalation** (Enemy → NPC):
- Successful diplomacy/intimidation/negotiation
- Enemy surrenders or is convinced to stand down
- Preserves ALL state (health, wounds, conditions, skills)
- **Critical**: agent_id NEVER changes (stable across conversions)

**Escalation** (NPC → Enemy):
- NPC is attacked or severely threatened
- DM decides via Escalation in structured output
- Preserves ALL state, adds tactics
- **Critical**: agent_id preserved

**Capture** (Enemy → Prisoner NPC):
- Enemy reduced to 0 HP via stun damage + capture_intent
- Converts to prisoner (entity_type="prisoner")
- Can be stabilized, interrogated, recruited

### Stable Agent IDs

**Key principle**: agent_id NEVER changes during conversions.

Why:
- Target tracking across rounds
- Condition references remain valid
- JSONL continuity (can follow same agent)
- Replay logic works unchanged

Example:
```
Enemy pirate (agent_id="enemy_freeborn_pirate_1")
  → Surrenders → NPC (agent_id="enemy_freeborn_pirate_1" ✅)
  → Attacked → Enemy (agent_id="enemy_freeborn_pirate_1" ✅)
```

### Healing System

**Action type**: `ActionType.SUPPORT`
**Skill check**: Intelligence × Medicine (or similar)

**Heal types**:
- `stun`: Remove stun damage (fast recovery)
- `wound`: Reduce wound penalties (surgery-equivalent)
- `hp`: Restore health (medical treatment)

**Healing targets**: Any agent (PCs, NPCs, enemies if non-hostile)

### Skills for De-escalation

**Social skills** (corrected):
- Empathy × Charm - Persuasion, negotiation
- Charisma × Charm - Intimidation (accessible to all!)
- Empathy × Corporate Influence - Faction negotiation
- Intelligence × Debt Law - Contract leverage

**Warning**: Unskilled Empathy checks have 5-15% success rate. Use Charm-based skills instead.

### Targeting Hierarchy

**Players** can target: PCs, NPCs, Enemies (universal)
**Enemies** can target: PCs + NPCs (based on personality)
  - `ruthless`: Target anyone
  - `professional`: Only threats (PCs + armed NPCs)
  - `defensive`: Only PCs
**NPCs** cannot target (non-combatant, can only flee/hide/dialogue)

### JSONL Logging

**New event**: `agent_conversion`
- Tracks conversions with stable agent_id
- Includes state snapshot for replay

**NPC actions**: Use same `action_declaration`/`action_resolution` events
- `agent_type="npc"` distinguishes from players/enemies
- `entity_type` specifies neutral/ally/prisoner
```

## IFF/ROE Future Vision (Out of Scope)

**Long-term goal**: Multi-faction scenarios where hostility is dynamic, not binary.

**Example scenario**: Players (Freeborn) encounter:
- Freeborn NPCs (neutral/ally)
- ACG enemies (hostile)
- Civilian NPCs (neutral)
- Tempest NPCs (unknown/wary)

Players must distinguish threats from non-threats using ROE (Rules of Engagement).

### Why Narrative Mode?

Current tactical combat system is **deeply binary**:
- `Hemisphere.PC` vs `Hemisphere.ENEMY`
- Position system assumes two sides
- Enemy AI targets "opposite hemisphere"

**Refactoring for true multi-faction combat would require**:
- Replace binary hemispheres with faction-based positioning (~400 lines)
- Add hostility matrix (who can target whom) (~200 lines)
- Refactor enemy AI for multi-faction combat (~300 lines)
- **Total**: ~900 lines, high architectural risk

**Narrative mode alternative**:
- Disable tactical module entirely
- Free-form positioning via narration
- Social/stealth focused gameplay
- Combat is simplified (more like investigation/ritual resolution)
- **Estimated**: 300-500 lines, lower risk

**Current NPC design supports this**:
- NPCs exist "off-grid" (no Position)
- entity_type and faction fields ready for hostility logic
- Can convert enemy↔NPC dynamically
- Simple LLM client works in narrative mode

**Decision**: Defer IFF/ROE to future work. Implement narrative mode when needed.

## ChromaDB Knowledge System

**Current usage**:
- **Players**: Optional `LOOKUP: <query>` in action declarations (rarely used)
- **DM**: Automatic lore query during scenario generation (once per session)
- **Enemies**: No access

**NPC decision**: Don't give NPCs LOOKUP capability (expensive, unnecessary).

Instead, pre-bake faction-specific lore into NPC prompts:
```python
if npc.faction == "ACG":
    context = "You're ACG. Contracts are sacred, breach of bond is unforgivable."
```

**Logging enhancement needed**: Add DEBUG logs for DM scenario generation queries (currently silent).

## Success Criteria

✅ **De-escalation works**: Successful diplomacy converts enemy → NPC (stable ID, full state preservation)
✅ **Escalation works**: Attacking NPC converts → enemy (DM decides, stable ID)
✅ **Capture works**: Stun damage + capture_intent → prisoner NPC (stable ID)
✅ **Healing works**: Medical actions restore HP/remove stuns/treat wounds
✅ **NPC agency works**: NPCs have simple LLM, can flee/hide/plead/dialogue
✅ **Personality targeting works**: Ruthless enemies target NPCs, professionals don't
✅ **Stable IDs work**: agent_id never changes during conversions, JSONL continuity preserved
✅ **Round 3 scenario passes**: Freeborn pirate negotiation converts enemy to NPC
✅ **No markers used**: All spawning/conversion via Pydantic structured output
✅ **Opportunistic acting**: NPCs skip turns when safe, log pass actions for ML training

## Related Documents

- `.claude/ARCHITECTURE.md` - Multi-agent system architecture
- `.claude/NARRATIVE_ENTITIES_DESIGN.md` - Environmental objects design (separate feature)
- `CLAUDE.md` - Main development guide
- `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` - JSONL event schemas
- `scripts/session_config_README.md` - Session configuration guide

## Session Logs Referenced

- Session: `6cecd16d-e85a-483d-85bb-715d8def9d27`
- Log: `archive/logs/prompt_test_nonmagic.log`
- JSONL: `multiagent_output/session_6cecd16d-e85a-483d-85bb-715d8def9d27.jsonl`
- Issue: Round 3 de-escalation succeeded but had no mechanical effect

---

**Next Steps**: Review this design doc, then begin Phase 1 (TDD for NPCAgent and NPCLLMClient).
