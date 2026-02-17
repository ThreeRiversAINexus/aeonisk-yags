# 04: Defense Token Implementation for All Agent Types

**Priority:** P2
**Status:** Spec Draft
**Dependencies:** None
**Estimated Scope:** Medium (schema changes, modifier logic, prompt updates)

---

## Problem Statement

Defense tokens are a tactical mechanic where an agent "watches" one other combatant,
granting a -2 attack penalty to the watched enemy when they attack the watcher, and a
+2 flanking bonus to all enemies NOT being watched. This creates meaningful tactical
choices: spread your attention and reduce flanking, or concentrate on one threat.

Currently, only enemy agents can declare defense tokens. The mechanic is partially
implemented:

1. **Enemies can declare them** via EnemyDecision schema and the enemy prompt
   encourages (but does not require) allocation.
2. **Enemy attack resolution checks them** on the target, applying +/-2 modifiers.
3. **Players CANNOT declare them** -- no field exists in any player action schema.
4. **NPCs CANNOT declare them** -- no field exists in NPCAction schema.
5. **PC attack resolution does NOT check them** -- when a player attacks an enemy,
   no defense token modifier is applied even if the enemy declared one.

This asymmetry means:
- Enemies get flanking bonuses against players who physically cannot watch them.
- Players have no defensive positioning mechanic during declaration phase.
- NPCs (especially armed neutrals or allies) cannot contribute defensively.
- The mechanic produces skewed ML training data (enemies always flank, PCs never defend).

**Design Decision (confirmed):** Every player, enemy, and NPC may assign one defense
token per declaration to one other agent. Available once per action declaration. This
is a universal mechanic, not faction- or role-specific.

---

## Current Implementation

### Enemy Declaration Schema

**File:** `scripts/aeonisk/multiagent/schemas/enemy_decision.py` lines 59-63

```python
# Defensive positioning
defence_token: Optional[str] = Field(
    default=None,
    description="Target ID (tgt_xxxx) to protect/cover, or None"
)
```

Enemies declare their defense token as part of `EnemyDecision`. The field accepts a
target ID (tgt_xxxx format) or None. The `to_legacy_dict()` method (line 153) includes
`defence_token` in the output dict.

### Enemy Agent Dataclass

**File:** `scripts/aeonisk/multiagent/enemy_agent.py` line 314

```python
defence_token: Optional[str] = None  # Which PC agent_id are they watching?
```

The enemy agent stores the currently assigned defense token as persistent state. This
is set during declaration processing in `enemy_combat.py` lines 616 and 813:

```python
enemy.defence_token = parsed.defence_token
```

### Enemy Attack Resolution -- Defense Token Check

**File:** `scripts/aeonisk/multiagent/enemy_combat.py` lines 1038-1045

```python
# Check if target has defence token on this enemy
target_defence_token = getattr(target, 'defence_token', None)
if target_defence_token == enemy.agent_id:
    attack_total -= 2  # Target watching this enemy
    defence_note = "(target watching -2)"
else:
    attack_total += 2  # Flanking bonus
    defence_note = "(flanking +2)"
```

This code checks whether the **target** of an enemy's attack has their defense token
assigned to the attacking enemy. If yes, the attacker gets -2. If no, +2 flanking.

An identical check exists at lines 1369-1375 for suppressive fire resolution.

**Critical observation:** This code uses `getattr(target, 'defence_token', None)`.
Since player agents (`AIPlayerAgent`) and `CharacterState` (lines 76-163 of player.py)
have no `defence_token` attribute, `getattr` always returns `None`, and enemies always
get the +2 flanking bonus against players. The mechanic is structurally broken for PCs.

### Enemy Prompt -- Defense Token Encouragement

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 616-624

```python
section += f"""

### Defence Token Allocation:
CRITICAL: You must allocate your Defence Token to ONE PC you're watching.
- PC with your token: -2 to hit you
- PCs without your token: +2 Flanking bonus vs you

Currently allocated to: {enemy.defence_token or "NONE (all PCs get Flanking +2!)"}"""
```

The prompt tells enemies they "must" allocate a defense token, but `defence_token` is
`Optional[str]` with `default=None` in the schema, so omission does not cause a
validation error. The prompt also references PC defence tokens when listing targets
(lines 453-458, 750-751):

```python
pc_defence_token = getattr(pc, 'defence_token', None)
is_watching = pc_defence_token == enemy.agent_id
watching_str = "WATCHING YOU (-2 to hit them)" if is_watching else \
               "NOT watching you (+2 Flanking if you attack)"
```

This already handles the case where PCs have defense tokens -- but PCs never do.

### Structured Output Format in Enemy Prompt

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/enemy.yaml` lines 177, 195-198

The structured output section documents `defence_token` as a field and marks it as
required in the validation checklist (line 262):

```
- Defence_token is PC agent_id (not None unless no PCs exist)
```

### Player Action Schemas -- No Defense Token Field

**File:** `scripts/aeonisk/multiagent/schemas/player_action.py`

Neither `PlayerActionBase` (lines 77-168), `CombatAction` (lines 336-379), nor the
legacy `PlayerAction` (lines 779-1028) contain a `defence_token` field. Confirmed via
grep: zero matches for `defence_token` or `defense_token` in `player_action.py`.

### NPC Action Schema -- No Defense Token Field

**File:** `scripts/aeonisk/multiagent/npc_agent.py` lines 350-461

`NPCAction` has `action_type`, `reason`, `target`, `dialogue_content`, and transfer
fields. No `defence_token` field exists.

### Player Agent -- No Defense Token Attribute

**File:** `scripts/aeonisk/multiagent/player.py` lines 76-164 (CharacterState),
lines 165+ (AIPlayerAgent)

Neither `CharacterState` nor `AIPlayerAgent` store a `defence_token` attribute. The
`getattr(target, 'defence_token', None)` in enemy_combat.py always returns None for
player targets.

### DM Combatant List -- No Defense Token Display

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7536-7578

The combatant list builder shows target IDs, names, pronouns, health, wounds, and
agent type (player/enemy/npc/vendor). It does not display defense token assignments.

### PC Attack Resolution -- No Defense Token Check

**File:** `scripts/aeonisk/multiagent/dm.py`

When DM resolves a PC attack via structured output (`ActionResolution`), the resolution
is narrative-driven. The DM does not mechanically check whether the PC's target has a
defense token on the PC. This contrasts with enemy attack resolution, which applies
+/-2 based on defense tokens at the code level.

---

## Design Decisions

1. **Universal mechanic:** All agent types (PC, enemy, NPC) get one defense token per
   round, declared during their action declaration phase.

2. **Token semantics:** "I am watching agent X" -- means:
   - If X attacks me, X gets -2 to their attack roll.
   - If any agent OTHER than X attacks me, they get +2 flanking bonus.
   - Only one token per declaration (cannot watch multiple agents).

3. **Declaration timing:** Defense tokens are declared alongside the action declaration
   (Phase 2 for PCs, EnemyDecision for enemies, NPCAction for NPCs). They persist
   until the next declaration phase.

4. **Target ID format:** Defense tokens use target IDs (`tgt_xxxx`) in free targeting
   mode, or agent IDs in standard mode. Consistent with existing enemy implementation.

5. **Optional field:** Defense token remains `Optional[str]` with `default=None`. Not
   every action warrants watching someone (e.g., exploration, social, technical). The
   prompt should encourage usage during combat but not force it for non-combat actions.

6. **Modifier symmetry:** The same +/-2 modifier applies regardless of attacker type:
   - Enemy attacks PC: check PC's defense token (already implemented, currently broken)
   - PC attacks enemy: check enemy's defense token (NOT implemented)
   - NPC attacks anyone: check target's defense token (NOT implemented)
   - Enemy attacks NPC: check NPC's defense token (NOT implemented)

7. **DM narration integration:** For PC attacks resolved by DM (structured output),
   the defense token modifier should be surfaced in the DM prompt's resolution context
   so the DM can factor it into success tier determination.

---

## Proposed Solution

### Phase 1: Schema Changes

#### 1.1 Add `defence_token` to PlayerActionBase

**File:** `scripts/aeonisk/multiagent/schemas/player_action.py`

Add the field to `PlayerActionBase` (after `reasoning`, line 148) so it is available
to all action types during combat rounds. Some players take non-combat actions
(investigate, support) but still need defensive positioning:

```python
class PlayerActionBase(BaseModel):
    # ... existing fields ...

    reasoning: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Internal reasoning for this action choice (for ML training)"
    )

    defence_token: Optional[str] = Field(
        default=None,
        description=(
            "COMBAT ONLY: Target ID (tgt_xxxx) of the combatant you are watching. "
            "That combatant gets -2 to attack you; all others get +2 flanking. "
            "Choose the biggest threat. Leave null for non-combat situations."
        )
    )
```

Since `CombatAction` inherits from `PlayerActionBase`, no separate addition needed
on `CombatAction`. All action types (ExploreAction, SocialAction, etc.) inherit it.

#### 1.2 Add `defence_token` to Legacy PlayerAction

**File:** `scripts/aeonisk/multiagent/schemas/player_action.py`

Add to the legacy `PlayerAction` class (after `situational_modifiers`, line 943):

```python
class PlayerAction(BaseModel):
    # ... existing fields ...

    situational_modifiers: Dict[str, int] = Field(...)

    defence_token: Optional[str] = Field(
        default=None,
        description=(
            "Target ID (tgt_xxxx) of the combatant you are watching/covering. "
            "That combatant gets -2 to attack you; others get +2 flanking."
        )
    )
```

Also update `to_legacy_dict()` (around line 1005) to include:

```python
def to_legacy_dict(self) -> Dict:
    return {
        # ... existing fields ...
        'situational_modifiers': self.situational_modifiers,
        'defence_token': self.defence_token,
    }
```

#### 1.3 Add `defence_token` to NPCAction

**File:** `scripts/aeonisk/multiagent/npc_agent.py`

Add after the transfer fields (line 421):

```python
class NPCAction(BaseModel):
    # ... existing fields ...

    transfer_items: Optional[Dict[str, int]] = Field(...)

    defence_token: Optional[str] = Field(
        None,
        description=(
            "Target ID (tgt_xxxx) you are watching/covering during combat. "
            "That combatant gets -2 to attack you; others get +2 flanking. "
            "Recommended for armed_neutral and potential_threat NPCs in combat."
        )
    )
```

#### 1.4 Store defence_token on AIPlayerAgent

**File:** `scripts/aeonisk/multiagent/player.py`

Add `defence_token` attribute to `AIPlayerAgent.__init__`:

```python
class AIPlayerAgent(Agent):
    def __init__(self, ...):
        # ... existing init ...
        self.defence_token: Optional[str] = None
```

#### 1.5 Store defence_token on NPCAgent

**File:** `scripts/aeonisk/multiagent/npc_agent.py`

Add to `NPCAgent` dataclass (after `is_active`, line 300):

```python
@dataclass
class NPCAgent:
    # ... existing fields ...
    is_active: bool = True
    defence_token: Optional[str] = None  # Which combatant this NPC is watching
```

### Phase 2: Modifier Logic for PC Attacks

#### 2.1 Create shared utility function

**File:** `scripts/aeonisk/multiagent/mechanics.py`

```python
def apply_defense_token_modifier(
    attacker_agent_id: str,
    target,
    target_id_mapper=None
) -> Tuple[int, str]:
    """
    Calculate defense token attack modifier.

    The target's defence_token determines the modifier:
    - If target is watching the attacker: attacker gets -2
    - If target is watching someone else or no one: attacker gets +2 (flanking)

    Args:
        attacker_agent_id: The agent_id of the attacker
        target: The target entity (must have .defence_token attribute or lack thereof)
        target_id_mapper: Optional TargetIDMapper for resolving tgt_xxxx to agent_id

    Returns:
        (modifier, description) -- e.g., (-2, "target watching -2") or (+2, "flanking +2")
    """
    target_defense = getattr(target, 'defence_token', None)

    if target_defense is None:
        return (2, "flanking +2, target not watching anyone")

    # Direct match on agent_id
    if target_defense == attacker_agent_id:
        return (-2, "target watching -2")

    # Check if target's defence_token is the attacker's tgt_xxxx alias
    if target_id_mapper:
        attacker_tgt_id = target_id_mapper.get_target_id(attacker_agent_id)
        if attacker_tgt_id and target_defense == attacker_tgt_id:
            return (-2, "target watching -2")

    return (2, "flanking +2")
```

#### 2.2 Surface defense token in DM resolution prompt

**File:** `scripts/aeonisk/multiagent/dm.py`

When building the DM prompt for a PC's combat action (around line 7580, after the
weapon context block), inject defense token modifier info:

```python
# Build defense token context for combat actions
defense_token_context = ""
if action and action.get('action_type') in ('attack', 'combat', 'brawl'):
    target_id = action.get('target')
    if target_id and self.shared_state:
        target_id_mapper = self.shared_state.get_target_id_mapper()
        if target_id_mapper and target_id_mapper.enabled:
            target_entity = target_id_mapper.resolve_target(target_id)
            if target_entity:
                from .mechanics import apply_defense_token_modifier
                attacker_agent_id = action.get('agent_id', '')
                modifier, desc = apply_defense_token_modifier(
                    attacker_agent_id, target_entity, target_id_mapper
                )
                if modifier < 0:
                    defense_token_context = (
                        f"\n**DEFENSE TOKEN:** Target is WATCHING this attacker "
                        f"({desc}). Factor this -2 penalty into success tier.\n"
                    )
                else:
                    defense_token_context = (
                        f"\n**FLANKING BONUS:** Target is NOT watching this attacker "
                        f"({desc}). Factor this +2 bonus into success tier.\n"
                    )
```

#### 2.3 Refactor enemy_combat.py to use shared utility

**File:** `scripts/aeonisk/multiagent/enemy_combat.py` lines 1038-1045 and 1368-1375

Replace inline defense token check with the shared utility:

```python
# Before (lines 1038-1045):
target_defence_token = getattr(target, 'defence_token', None)
if target_defence_token == enemy.agent_id:
    attack_total -= 2
    defence_note = "(target watching -2)"
else:
    attack_total += 2
    defence_note = "(flanking +2)"

# After:
from .mechanics import apply_defense_token_modifier
token_modifier, defence_note = apply_defense_token_modifier(
    enemy.agent_id, target, self.shared_state.get_target_id_mapper()
    if self.shared_state else None
)
attack_total += token_modifier
```

### Phase 3: Declaration Processing

#### 3.1 Player Declaration Processing

**File:** `scripts/aeonisk/multiagent/dm.py` or `scripts/aeonisk/multiagent/session.py`

After a player's Phase 2 structured output is parsed, extract and store the defense
token on the agent:

```python
# After player action structured output is parsed
if hasattr(player_action, 'defence_token'):
    player_agent.defence_token = player_action.defence_token
    if player_action.defence_token:
        logger.info(
            f"{player_agent.character_state.name} watching "
            f"{player_action.defence_token}"
        )
else:
    player_agent.defence_token = None  # Clear from previous round
```

#### 3.2 NPC Declaration Processing

**File:** `scripts/aeonisk/multiagent/dm.py` (adjudicate_npc section)

After NPC action is declared:

```python
if hasattr(npc_action, 'defence_token'):
    npc.defence_token = npc_action.defence_token
    if npc_action.defence_token:
        logger.info(f"NPC {npc.name} watching {npc_action.defence_token}")
else:
    npc.defence_token = None
```

#### 3.3 Round Reset

At the beginning of each round's declaration phase, reset all defense tokens to None
before agents redeclare:

```python
# Reset defense tokens at round start
for player_agent in player_agents:
    player_agent.defence_token = None
for npc in npc_agents:
    npc.defence_token = None
# Enemy tokens already reset via EnemyDecision processing
```

### Phase 4: Prompt Updates

#### 4.1 Player Combat Prompt

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/player/player_action_combat.yaml`

Add a defense token section to the combat action guidance:

```yaml
defense_token_guidance: |-
  ## Defense Token (Tactical Positioning)

  During combat, assign your defense token to ONE combatant you are watching:

  **Mechanic:**
  - The combatant you watch gets -2 to their attack rolls against you
  - ALL other combatants get +2 flanking bonus when attacking you
  - You can only watch one combatant per round

  **When to use:**
  - Watch the biggest threat to you (highest damage, closest melee enemy)
  - If only one enemy threatens you, always watch them
  - If multiple enemies, watch the deadliest one and accept flanking from others

  **How to declare:**
  Set defence_token to the tgt_xxxx of the combatant you are watching.
  Leave null if not in combat or no specific threat.
```

#### 4.2 Player Targeting Guidance Update

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/player.yaml` lines 744-752

Extend the `targeting_guidance` section:

```yaml
targeting_guidance: |-
  # Free Targeting Mode

  All combatants have generic IDs: `tgt_xxxx`

  No faction restrictions enforced by system. DM interprets intent via context.
  You can target anyone (including allies if justified by roleplay).

  ## Defense Token
  In combat, set `defence_token` to the tgt_xxxx of the combatant you are watching.
  That combatant gets -2 to hit you; all others get +2 flanking bonus against you.
```

#### 4.3 Enemy Prompt Enhancement

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` lines 616-624

Enhance to explain the symmetric mechanic and PC watching:

```python
section += f"""

### Defence Token Allocation:
CRITICAL: Allocate your Defence Token to ONE combatant you're watching.
- **You watch them:** They get -2 to hit you (you're vigilant)
- **You don't watch them:** They get +2 Flanking bonus vs you
- **They watch you:** YOU get -2 to hit THEM (shown in target list)

Currently allocated to: {enemy.defence_token or "NONE (all enemies get Flanking +2!)"}

TACTICAL RECOMMENDATION:
- Watch the combatant most likely to attack you this round
- If a PC is watching you (shown as "WATCHING YOU" in target list),
  attacking them costs -2; consider a different target
- PCs NOT watching you are vulnerable to flanking (+2 to hit)"""
```

#### 4.4 NPC Prompt Enhancement

**File:** `scripts/aeonisk/multiagent/npc_agent.py` (NPCLLMClient._get_system_prompt)

Add defense token guidance (around line 608, after action options):

```python
"""
**Defense Token (Combat Only):**
- Set defence_token to the tgt_xxxx of the combatant you are watching
- They get -2 to attack you; others get +2 flanking
- Recommended for armed_neutral and potential_threat NPCs
- Non-combatant NPCs: leave defence_token null
"""
```

### Phase 5: DM Combatant List Enhancement

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7536-7578

Add defense token status to combatant list entries:

```python
# Inside combatant list builder, for player entries (around line 7553)
watching = getattr(player_agent, 'defence_token', None)
watch_text = f", watching {watching}" if watching else ""
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {health_text}{wounds_text}{watch_text})"
)

# For enemy entries (around line 7567)
enemy_agent = target_id_mapper.resolve_target(tid)
watching = getattr(enemy_agent, 'defence_token', None)
watch_text = f", watching {watching}" if watching else ""
combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {info['type']}{watch_text})"
)
```

---

## Spelling Note: `defence_token` vs `defense_token`

The existing codebase uses British spelling `defence_token` in:
- `enemy_agent.py` line 314
- `enemy_decision.py` line 60
- `enemy_combat.py` lines 49, 111, 136, 533, 616, 695, 813, 1039, 1369
- `enemy_prompts.py` lines 453, 624, 750

**Decision:** Use `defence_token` everywhere (match existing convention). The
`enemy_prompts.py` already uses `getattr(pc, 'defence_token', None)`, so the
attribute name on player agents must be `defence_token` for the existing code to work
without modification. If we want American spelling, rename everything in a separate
cleanup commit.

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `schemas/player_action.py` | Add `defence_token` to `PlayerActionBase` | After line 148 |
| `schemas/player_action.py` | Add `defence_token` to legacy `PlayerAction` | After line 943 |
| `schemas/player_action.py` | Add `defence_token` to `PlayerAction.to_legacy_dict()` | Lines 1005-1027 |
| `npc_agent.py` | Add `defence_token` to `NPCAction` schema | After line 421 |
| `npc_agent.py` | Add `defence_token` to `NPCAgent` dataclass | After line 300 |
| `npc_agent.py` | Add defense token to NPC system prompt | Lines 571-643 |
| `player.py` | Add `defence_token` attribute to `AIPlayerAgent` | In `__init__` |
| `dm.py` | Store player defense token after declaration | Declaration processing |
| `dm.py` | Store NPC defense token after declaration | NPC adjudication |
| `dm.py` | Add defense token modifier to DM resolution prompt | Lines 7580+ |
| `dm.py` | Add defense token to combatant list display | Lines 7536-7578 |
| `mechanics.py` | Add `apply_defense_token_modifier()` utility | New function |
| `enemy_combat.py` | Refactor to use shared utility | Lines 1038-1045, 1368-1375 |
| `enemy_prompts.py` | Enhance defense token section | Lines 616-624 |
| `prompts/.../player.yaml` | Add defense token to targeting_guidance | Lines 744-752 |
| `prompts/.../player_action_combat.yaml` | Add defense token guidance section | New section |
| `prompts/.../enemy.yaml` | Update structured output examples | Lines 160-268 |

---

## Test Plan

### Unit Tests

**File:** `tests/unit/test_defense_tokens.py`

```python
class TestDefenseTokenSchemas:
    """Schema validation for defense token field."""

    def test_combat_action_accepts_defense_token(self):
        """CombatAction should accept defence_token field."""
        action = CombatAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            target="tgt_7a3f",
            defence_token="tgt_b2e1"
        )
        assert action.defence_token == "tgt_b2e1"

    def test_combat_action_defense_token_optional(self):
        """CombatAction defence_token should default to None."""
        action = CombatAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            target="tgt_7a3f"
        )
        assert action.defence_token is None

    def test_npc_action_accepts_defense_token(self):
        """NPCAction should accept defence_token field."""
        action = NPCAction(
            action_type="hide",
            reason="Taking cover behind the crates during the ongoing combat.",
            defence_token="tgt_a4f2"
        )
        assert action.defence_token == "tgt_a4f2"

    def test_npc_action_defense_token_optional(self):
        """NPCAction defence_token should default to None."""
        action = NPCAction(
            action_type="flee",
            reason="Running away from the combat zone as quickly as possible."
        )
        assert action.defence_token is None

    def test_legacy_player_action_accepts_defense_token(self):
        """Legacy PlayerAction should accept defence_token for backward compat."""
        action = PlayerAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_7a3f",
            defence_token="tgt_b2e1"
        )
        assert action.defence_token == "tgt_b2e1"

    def test_to_legacy_dict_includes_defense_token(self):
        """to_legacy_dict should include defence_token."""
        action = PlayerAction(
            intent="Fire plasma rifle at enemy commander",
            description="Taking careful aim at enemy leader's center mass, "
                        "squeezing trigger on exhale for maximum accuracy.",
            attribute="Perception",
            skill="Guns",
            difficulty_estimate=18,
            difficulty_justification="Moving target with partial cover",
            action_type=ActionType.COMBAT,
            target="tgt_7a3f",
            defence_token="tgt_b2e1"
        )
        legacy = action.to_legacy_dict()
        assert legacy['defence_token'] == "tgt_b2e1"


class TestDefenseTokenModifiers:
    """Attack modifier calculations based on defense tokens."""

    def test_target_watching_attacker_gives_minus_2(self):
        """When target's defence_token matches attacker, attacker gets -2."""
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token="enemy_grunt_01")
        )
        assert modifier == -2
        assert "watching" in desc

    def test_target_not_watching_gives_plus_2(self):
        """When target's defence_token is someone else, attacker gets +2."""
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token="enemy_sniper_02")
        )
        assert modifier == 2
        assert "flanking" in desc

    def test_target_no_defense_token_gives_plus_2(self):
        """When target has no defence_token, attacker gets +2 flanking."""
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token=None)
        )
        assert modifier == 2
        assert "flanking" in desc

    def test_target_watching_via_target_id(self):
        """Defence token can be a tgt_xxxx ID, matched via mapper."""
        mapper = MockTargetIDMapper({"enemy_grunt_01": "tgt_7a3f"})
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="enemy_grunt_01",
            target=MockAgent(defence_token="tgt_7a3f"),
            target_id_mapper=mapper
        )
        assert modifier == -2

    def test_pc_attacking_enemy_watched_gets_minus_2(self):
        """When PC attacks enemy, enemy's defence_token should be checked."""
        enemy = MockAgent(defence_token="tgt_1234")
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="player_01",
            target=enemy,
            target_id_mapper=MockTargetIDMapper({"player_01": "tgt_1234"})
        )
        assert modifier == -2  # Enemy is watching this PC

    def test_pc_attacking_unwatched_enemy_gets_flanking(self):
        """PC attacking enemy who watches someone else gets +2."""
        enemy = MockAgent(defence_token="tgt_9999")
        modifier, desc = apply_defense_token_modifier(
            attacker_agent_id="player_01",
            target=enemy,
            target_id_mapper=MockTargetIDMapper({"player_01": "tgt_1234"})
        )
        assert modifier == 2


class TestDefenseTokenStorage:
    """Verify defense tokens are stored on agent instances."""

    def test_player_agent_stores_defense_token(self):
        """AIPlayerAgent should store defence_token attribute."""
        agent = create_test_player_agent()
        assert hasattr(agent, 'defence_token')
        assert agent.defence_token is None
        agent.defence_token = "tgt_7a3f"
        assert agent.defence_token == "tgt_7a3f"

    def test_npc_agent_stores_defense_token(self):
        """NPCAgent should store defence_token attribute."""
        npc = create_test_npc_agent()
        assert hasattr(npc, 'defence_token')
        assert npc.defence_token is None
        npc.defence_token = "tgt_b2e1"
        assert npc.defence_token == "tgt_b2e1"

    def test_enemy_agent_already_stores_defense_token(self):
        """EnemyAgent already has defence_token (regression check)."""
        enemy = create_test_enemy_agent()
        assert hasattr(enemy, 'defence_token')
```

### Integration Tests

**File:** `tests/integration/test_defense_tokens_integration.py`

1. **Full round with PC defense tokens:** Mock a combat round where PCs declare
   defense tokens, verify enemy attack resolution applies modifiers correctly.
2. **DM prompt includes defense token context:** Verify the DM resolution prompt
   mentions defense token modifiers for combat actions.
3. **Combatant list shows defense tokens:** Verify combatant list entries include
   watching status when defense tokens are assigned.

### Prompt Tests

1. Verify `player_action_combat.yaml` loads and contains defense token section.
2. Verify enemy prompt includes defense token allocation section.
3. Verify NPC system prompt mentions defense tokens for combat-capable NPCs.

---

## Migration Notes

- No database migration needed (in-memory state only).
- No JSONL schema changes needed (defense tokens are declaration-phase, not logged
  as separate events -- they are implicit in the action declaration).
- Existing fixtures remain valid (new field is Optional with default=None).
- Existing enemy_combat.py defense token checks will work unchanged once PC agents
  have the `defence_token` attribute.

---

## Open Questions

1. **Should defense tokens reset each round?** Current enemy implementation resets
   when a new declaration overwrites the old value. Should PCs explicitly clear their
   token, or does it persist until changed?
   **Recommendation:** Reset to None at the start of each declaration phase, require
   re-declaration. This forces active tactical thinking each round.

2. **Should non-combat actions support defense tokens?** If a PC declares INVESTIGATE
   during combat, can they still watch an enemy?
   **Recommendation:** Yes. The field on `PlayerActionBase` allows any action type to
   declare a defense token. The prompt should encourage it for any action taken during
   a combat round.

3. **NPC defense tokens -- worth the token cost?** NPCs already have minimal prompts
   (~500 tokens). Adding defense token guidance adds ~100 tokens.
   **Recommendation:** Yes, but only mention it in the system prompt for NPCs with
   `threat_level` of `potential_threat` or `armed_neutral`. Non-combatant NPCs skip it.

4. **Should the DM see all defense token assignments?** Currently the combatant list
   shows health and wounds. Adding defense tokens reveals tactical intent.
   **Recommendation:** Yes, the DM needs this information to narrate positioning
   accurately and factor modifiers into resolution.

5. **Interaction with bonds:** Bond system gives +1 Soak when defending a bonded
   partner. Does this stack with defense token modifier?
   **Recommendation:** Yes, they are orthogonal mechanics. Bond Soak is damage
   reduction; defense token is attack roll modifier. Both can apply simultaneously.

6. **ML training data implications:** Defense tokens add a new field to player action
   structured output. Existing training data will not have this field.
   **Recommendation:** Acceptable. The field is Optional[None], so existing data
   naturally represents "no defense token declared." New sessions will produce richer
   tactical training data.
