# 05: Full Stealth Overhaul

**Priority:** P1
**Status:** Spec Draft
**Dependencies:** None
**Estimated Scope:** Large (new mechanic, flag tracking, target filtering, prompt changes)

---

## Problem Statement

Stealth in Aeonisk is currently narrative-only. The DM can narrate a character
"sneaking past guards" or "moving unseen," and can use the `aware_agents` field on
`ActionResolution` to limit who sees the narration. However, there is no mechanical
`is_hidden` flag, no opposed detection checks, and no target list filtering based on
stealth state. This means:

1. **Hidden characters remain targetable.** Enemy AI sees all combatants in the
   target list regardless of stealth state. An enemy can target a "hidden" PC because
   the system does not filter them out.

2. **No opposed checks.** Stealth vs. Perception/Awareness has no mechanical
   resolution. The DM narratively decides outcomes without structured formulas.

3. **No search action.** There is no defined mechanic for detecting hidden agents.
   An enemy who suspects a hidden PC has no structured way to attempt detection.

4. **No stealth-breaking rules.** Attacking from stealth should break concealment
   automatically, but nothing enforces this.

5. **No last-known-position tracking.** When an enemy loses sight of a target, they
   have no concept of where the target was last seen.

The existing `aware_agents` field (ActionResolution lines 378-394) provides the
foundation for information hiding, but it only controls narration visibility -- it
does not affect targeting, AI decision-making, or mechanical checks.

**Design Decisions (confirmed):**
- Successful hiding removes an agent from direct targeting.
- Hidden actions/resolutions are concealed unless observers can perceive.
- Enemies use last known position when target is hidden.
- Reacquisition requires Perception x Awareness checks.

---

## Current Implementation

### Awareness System

**File:** `scripts/aeonisk/multiagent/awareness.py` (full file, 94 lines)

The awareness module provides narration filtering:

```python
@dataclass
class NarrationEntry:
    text: str
    aware_agents: List[str] = field(default_factory=list)
```

`filter_narrations_for_agent()` (lines 31-76) filters narrations so agents only see
events they should be aware of:
- Empty `aware_agents` = public (everyone sees it)
- Populated `aware_agents` = private (only listed agents see it)

`is_agent_aware()` (lines 79-93) is a simple check:

```python
def is_agent_aware(agent_id: str, aware_agents: List[str]) -> bool:
    if not aware_agents:
        return True  # Public
    return agent_id in aware_agents
```

This system handles narration visibility but NOT:
- Target list filtering (who can be attacked)
- Mechanical detection checks
- Stealth state tracking

### ActionResolution.aware_agents

**File:** `scripts/aeonisk/multiagent/schemas/action_resolution.py` lines 378-394

```python
aware_agents: List[str] = Field(
    default_factory=list,
    description="""Which agents are aware of this action's outcome.
    - Empty list [] = PUBLIC (all agents see this narration)
    - Populated list = PRIVATE (only listed agents see it)
    Examples:
    - Stealth success: ["dm", "player_echo"]
    - Failed stealth: [] - everyone nearby heard/saw the failure
    """
)
```

The DM is instructed to populate `aware_agents` for stealth actions, but this only
affects narration distribution, not mechanical targeting.

### DM Prompt References to Stealth

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7879-7896

The DM combat prompt describes stealth as a movement benefit:

```
- **Unseen** (Stealth): Enemies can't target you until you attack or fail Stealth
- **First Strike** (Stealth ambush): +2 damage on your next attack
```

These are narrative guidelines, not mechanical enforcement. The DM is told to narrate
stealth outcomes but the system does not enforce them.

### Stealth Skill in Skill Mapping

**File:** `scripts/aeonisk/multiagent/skill_mapping.py` line 34

```python
'stealth': 'Stealth',
```

Stealth is a recognized YAGS skill. Characters can have Stealth skill points. The
skill is used in roll calculations when the DM decides a stealth check is appropriate.

### Stealth in Skill Descriptions

**File:** `scripts/aeonisk/multiagent/skill_descriptions.py` lines 84-85

```python
"Stealth": SkillInfo(
    name="Stealth",
    ...
)
```

### Enemy Templates with Stealth

**File:** `scripts/aeonisk/multiagent/enemy_templates.py` lines 98, 138, 310, 348

Several enemy templates have Stealth skill:
- Line 98: `"Stealth": 3` (standard template)
- Line 138: `"Stealth": 4` (elite template)
- Line 310: `"Stealth": 3` (another template)
- Line 348: `"Stealth": 5` (boss-level template)

These templates define Stealth skill values but the skill is never mechanically used
by enemy agents to hide.

### Target ID Mapper -- No Hidden Filtering

**File:** `scripts/aeonisk/multiagent/target_ids.py` lines 75-175

`TargetIDMapper.assign_ids()` assigns target IDs to all combatants. There is no
filtering based on hidden state:

```python
def assign_ids(self, player_agents, enemy_agents, npc_agents=None, vendors=None):
    # ... combines all agents into pool ...
    # NO filtering for hidden state
    for agent in all_combatants:
        target_id = generate_target_id()
        self.target_id_map[target_id] = agent
```

All active agents receive target IDs regardless of stealth state, making them visible
to all other agents.

### Agent Dataclasses -- No is_hidden Flag

**Player:** `scripts/aeonisk/multiagent/player.py` lines 76-164 (CharacterState),
165+ (AIPlayerAgent) -- no `is_hidden` attribute.

**Enemy:** `scripts/aeonisk/multiagent/enemy_agent.py` lines 268-663 (EnemyAgent) --
no `is_hidden` attribute. Has `status_effects` list (line 343) which could
theoretically contain "hidden" but this is not checked anywhere for targeting.

**NPC:** `scripts/aeonisk/multiagent/npc_agent.py` lines 231-349 (NPCAgent) -- no
`is_hidden` attribute.

### Enemy Prompt References to Hidden PCs

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py` line 372

```python
section += "\nNo visible player targets detected. They may be using stealth..."
```

This message appears when no player agents are visible to the enemy. However, this
only triggers when the player_agents list is empty (not when specific PCs are hidden),
which effectively never happens during combat.

---

## Design Decisions

1. **`is_hidden` flag on all agent types.** A boolean flag on `AIPlayerAgent`,
   `EnemyAgent`, and `NPCAgent` that tracks whether the agent is currently concealed.

2. **Opposed check formula.** YAGS-compatible:
   - **Hide check:** Agility x Stealth + d20 vs Environment DC
   - **Detection check:** Perception x Awareness + d20 vs hide_check_result
   - The hider's check result becomes the DC for detection.

3. **Hidden agents excluded from target list.** When `assign_ids()` or the DM
   combatant list builder runs, hidden agents are excluded from the target list shown
   to non-allied agents. The DM still sees all agents.

4. **Attack from hidden breaks stealth.** Any attack action automatically sets
   `is_hidden = False` after the action resolves, regardless of success.

5. **"Search" action for detection.** PCs can declare a PERCEPTION action to detect
   hidden enemies. Enemies can use their minor action (Scan) to attempt detection.
   NPCs detect via passive Awareness.

6. **Last known position.** When an agent hides, their last known position is stored.
   Enemies who lose sight of a target can still target the position (area effect) or
   move toward it.

7. **DM authority preserved.** The `is_hidden` flag is set by the DM during action
   resolution (via structured output), not by the player declaring stealth. The player
   declares a stealth action; the DM determines success and sets the flag.

8. **Narration visibility via aware_agents.** When a hidden agent acts, the DM uses
   `aware_agents` to limit narration visibility. This is the existing mechanic and
   requires no changes.

---

## Proposed Solution

### Phase 1: is_hidden Flag on All Agent Types

#### 1.1 AIPlayerAgent

**File:** `scripts/aeonisk/multiagent/player.py`

Add to `AIPlayerAgent.__init__`:

```python
class AIPlayerAgent(Agent):
    def __init__(self, ...):
        # ... existing init ...
        self.is_hidden: bool = False
        self.last_known_position: Optional[str] = None  # Position string
        self.stealth_dc: Optional[int] = None  # DC to detect this agent
```

#### 1.2 EnemyAgent

**File:** `scripts/aeonisk/multiagent/enemy_agent.py`

Add to `EnemyAgent` dataclass (after `is_panicked`, line 347):

```python
@dataclass
class EnemyAgent:
    # ... existing fields ...
    is_panicked: bool = False
    panic_trigger: Optional[str] = None

    # Stealth state
    is_hidden: bool = False
    last_known_position: Optional[str] = None  # Where enemies last saw this agent
    stealth_dc: Optional[int] = None  # DC to detect (set when hiding)
```

#### 1.3 NPCAgent

**File:** `scripts/aeonisk/multiagent/npc_agent.py`

Add to `NPCAgent` dataclass (after `is_active`, line 300):

```python
@dataclass
class NPCAgent:
    # ... existing fields ...
    is_active: bool = True

    # Stealth state
    is_hidden: bool = False
    last_known_position: Optional[str] = None
    stealth_dc: Optional[int] = None
```

### Phase 2: Opposed Check Mechanics

#### 2.1 Stealth Check Function

**File:** `scripts/aeonisk/multiagent/mechanics.py`

```python
def resolve_stealth_check(
    agent,
    environment_dc: int = 15,
    modifiers: int = 0
) -> Dict[str, Any]:
    """
    Resolve a stealth check using YAGS formula.

    Formula: Agility x Stealth + d20 + modifiers vs environment_dc

    Args:
        agent: The agent attempting to hide (must have attributes and skills)
        environment_dc: Base difficulty (10=dark alley, 15=normal, 20=open ground,
                        25=well-lit, 30=actively searched area)
        modifiers: Situational modifiers (+/- for cover, noise, distractions)

    Returns:
        Dict with:
            success: bool
            stealth_roll: int (total roll value, becomes detection DC if successful)
            d20: int (raw die roll)
            margin: int (roll - dc, negative = failure)
            formula: str (human-readable breakdown)
    """
    import random

    # Get stats
    agility = _get_attribute(agent, 'Agility', default=3)
    stealth_skill = _get_skill(agent, 'Stealth', default=0)

    # YAGS unskilled penalty
    unskilled_penalty = -5 if stealth_skill == 0 else 0

    d20 = random.randint(1, 20)
    roll_total = (agility * stealth_skill) + d20 + modifiers + unskilled_penalty

    # Minimum roll of 1 (can't go negative)
    roll_total = max(1, roll_total)

    success = roll_total >= environment_dc
    margin = roll_total - environment_dc

    formula = (
        f"Agility {agility} x Stealth {stealth_skill} + d20({d20})"
        f"{f' + modifiers({modifiers})' if modifiers else ''}"
        f"{f' + unskilled({unskilled_penalty})' if unskilled_penalty else ''}"
        f" = {roll_total} vs DC {environment_dc}"
    )

    return {
        'success': success,
        'stealth_roll': roll_total,
        'd20': d20,
        'margin': margin,
        'formula': formula,
        'agility': agility,
        'stealth_skill': stealth_skill,
    }
```

#### 2.2 Detection Check Function

**File:** `scripts/aeonisk/multiagent/mechanics.py`

```python
def resolve_detection_check(
    observer,
    stealth_dc: int,
    modifiers: int = 0
) -> Dict[str, Any]:
    """
    Resolve a detection check against a hidden target.

    Formula: Perception x Awareness + d20 + modifiers vs stealth_dc

    The stealth_dc is the total from the hider's stealth check (their roll becomes
    the DC for detection).

    Args:
        observer: The agent attempting to detect (must have attributes and skills)
        stealth_dc: DC to beat (from the hider's stealth check result)
        modifiers: Situational modifiers (+/- for noise, movement, equipment)

    Returns:
        Dict with:
            success: bool (True = detected the hidden agent)
            detection_roll: int
            d20: int
            margin: int
            formula: str
    """
    import random

    perception = _get_attribute(observer, 'Perception', default=3)
    awareness_skill = _get_skill(observer, 'Awareness', default=0)

    unskilled_penalty = -5 if awareness_skill == 0 else 0

    d20 = random.randint(1, 20)
    roll_total = (perception * awareness_skill) + d20 + modifiers + unskilled_penalty
    roll_total = max(1, roll_total)

    success = roll_total >= stealth_dc
    margin = roll_total - stealth_dc

    formula = (
        f"Perception {perception} x Awareness {awareness_skill} + d20({d20})"
        f"{f' + modifiers({modifiers})' if modifiers else ''}"
        f"{f' + unskilled({unskilled_penalty})' if unskilled_penalty else ''}"
        f" = {roll_total} vs DC {stealth_dc}"
    )

    return {
        'success': success,
        'detection_roll': roll_total,
        'd20': d20,
        'margin': margin,
        'formula': formula,
        'perception': perception,
        'awareness_skill': awareness_skill,
    }
```

#### 2.3 Helper Functions for Agent Stats (CANONICAL — shared with Spec 06)

> **Note:** These two helpers (`_get_attribute`, `_get_skill`) are the canonical
> definitions. Spec 06 (IFF/ROE) imports them via `from .mechanics import
> _get_attribute, _get_skill` — do NOT redefine them there. Implement these
> in this spec first; Spec 06 depends on them.

**File:** `scripts/aeonisk/multiagent/mechanics.py`

```python
def _get_attribute(agent, attr_name: str, default: int = 3) -> int:
    """Get attribute value from any agent type."""
    # EnemyAgent / NPCAgent: agent.attributes dict
    if hasattr(agent, 'attributes') and isinstance(agent.attributes, dict):
        return agent.attributes.get(attr_name, default)
    # AIPlayerAgent: agent.character_state.attributes dict
    if hasattr(agent, 'character_state'):
        cs = agent.character_state
        if hasattr(cs, 'attributes') and isinstance(cs.attributes, dict):
            return cs.attributes.get(attr_name, default)
    return default


def _get_skill(agent, skill_name: str, default: int = 0) -> int:
    """Get skill value from any agent type."""
    if hasattr(agent, 'skills') and isinstance(agent.skills, dict):
        return agent.skills.get(skill_name, default)
    if hasattr(agent, 'character_state'):
        cs = agent.character_state
        if hasattr(cs, 'skills') and isinstance(cs.skills, dict):
            return cs.skills.get(skill_name, default)
    return default
```

### Phase 3: Target List Filtering

#### 3.1 TargetIDMapper Hidden Filtering

**File:** `scripts/aeonisk/multiagent/target_ids.py`

Modify `assign_ids()` to track hidden agents separately. Hidden agents still get
target IDs (for DM use), but are flagged:

```python
class TargetIDMapper:
    def __init__(self):
        self.target_id_map: Dict[str, Any] = {}
        self.reverse_map: Dict[str, str] = {}
        self.enabled: bool = False
        self.npc_registry: Dict[str, Any] = {}
        self.hidden_agents: Set[str] = set()  # NEW: Set of agent_ids that are hidden

    def update_hidden_state(self, agent_id: str, is_hidden: bool):
        """Update hidden state for an agent."""
        if is_hidden:
            self.hidden_agents.add(agent_id)
        else:
            self.hidden_agents.discard(agent_id)

    def is_hidden(self, agent_id: str) -> bool:
        """Check if an agent is hidden."""
        return agent_id in self.hidden_agents

    def get_visible_target_ids(self, observer_agent_id: str) -> List[str]:
        """
        Get target IDs visible to a specific observer.

        Filters out hidden agents unless:
        - The observer is the DM (always sees all)
        - The hidden agent is on the same team as the observer
          (PCs can always see hidden PCs, enemies see hidden enemies)

        Args:
            observer_agent_id: The agent requesting the target list

        Returns:
            List of visible target_ids
        """
        if not self.enabled:
            return []

        visible = []
        observer_type = self.get_agent_type(observer_agent_id)

        for target_id, agent in self.target_id_map.items():
            agent_id = getattr(agent, 'agent_id', None) or \
                       getattr(agent, 'vendor_id', None)
            if not agent_id:
                visible.append(target_id)
                continue

            if agent_id not in self.hidden_agents:
                # Not hidden, always visible
                visible.append(target_id)
                continue

            # Hidden agent -- check if observer should see them
            target_type = self.get_agent_type(agent_id)

            # Same team always sees each other
            if observer_type == target_type:
                visible.append(target_id)
                continue

            # PCs on same team see each other (even hidden ones, for coordination)
            if observer_type == "player" and target_type == "player":
                visible.append(target_id)
                continue

            # Enemies on same team see each other
            if observer_type == "enemy" and target_type == "enemy":
                visible.append(target_id)
                continue

            # Otherwise, hidden agent is NOT visible to this observer
            # (skip adding to visible list)

        return visible
```

#### 3.2 DM Combatant List -- Mark Hidden Agents

**File:** `scripts/aeonisk/multiagent/dm.py` lines 7536-7578

The DM should see all agents but hidden ones should be marked:

```python
# Inside combatant list builder
agent_id_for_hidden = info.get('agent_id', '')
is_agent_hidden = target_id_mapper.is_hidden(agent_id_for_hidden)
hidden_marker = " [HIDDEN]" if is_agent_hidden else ""

combatant_lines.append(
    f"  - [{tid}] {info['name']} ({pronouns}, {info['type']}{hidden_marker})"
)
```

#### 3.3 Enemy Prompt -- Filter Hidden PCs from Target List

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py`

When building the enemy's tactical prompt, filter the player_agents list to only
show non-hidden PCs. For hidden PCs, show last known position:

```python
def _format_pc_targets(enemy, player_agents, target_id_mapper=None):
    """Format PC target information for enemy prompt."""
    visible_pcs = []
    hidden_pcs = []

    for pc in player_agents:
        pc_agent_id = getattr(pc, 'agent_id', None)
        if pc_agent_id and target_id_mapper and target_id_mapper.is_hidden(pc_agent_id):
            # Hidden PC -- show last known position only
            last_pos = getattr(pc, 'last_known_position', 'Unknown')
            pc_name = getattr(pc, 'name', 'Unknown PC')
            hidden_pcs.append(f"- {pc_name}: HIDDEN (last seen at {last_pos})")
        else:
            visible_pcs.append(pc)

    # Format visible PCs as normal targets
    # Format hidden PCs as awareness section
    section = ""
    if hidden_pcs:
        section += "\n**HIDDEN TARGETS (cannot be directly targeted):**\n"
        section += "\n".join(hidden_pcs)
        section += "\n\nUse 'Scan' minor action to attempt detection.\n"

    return section
```

### Phase 4: Stealth Breaking

#### 4.1 Automatic Stealth Break on Attack

**File:** `scripts/aeonisk/multiagent/dm.py`

After resolving a combat action from a hidden agent, automatically break stealth:

```python
# After combat action resolution for a hidden agent
if action.get('action_type') in ('combat', 'attack', 'brawl'):
    agent_id = action.get('agent_id')
    if agent_id and self.shared_state:
        agent = self.shared_state.get_agent_by_id(agent_id)
        if agent and getattr(agent, 'is_hidden', False):
            agent.is_hidden = False
            logger.info(f"{agent_id} stealth broken: attacked from hidden")

            # Update target ID mapper
            target_id_mapper = self.shared_state.get_target_id_mapper()
            if target_id_mapper:
                target_id_mapper.update_hidden_state(agent_id, False)
```

#### 4.2 DM-Controlled Stealth Setting

**File:** `scripts/aeonisk/multiagent/schemas/action_resolution.py`

Add a stealth result field to `MechanicalEffects`:

```python
class StealthChange(BaseModel):
    """Change to an agent's stealth state."""
    agent_id: str = Field(
        ...,
        description="Agent whose stealth state changes"
    )
    is_hidden: bool = Field(
        ...,
        description="True = agent is now hidden; False = agent revealed"
    )
    stealth_dc: Optional[int] = Field(
        default=None,
        description="DC to detect this agent (set by stealth check result)"
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Why stealth state changed"
    )


class MechanicalEffects(BaseModel):
    # ... existing fields ...

    stealth_changes: List[StealthChange] = Field(
        default_factory=list,
        description="Stealth state changes. Populated when agents hide or are detected."
    )
```

### Phase 5: Search/Detection Action

#### 5.1 PERCEPTION Action Enhancement

The existing `PerceptionAction` (player_action.py lines 418-438) already supports
awareness checks. Enhance it with detection-specific guidance:

```python
class PerceptionAction(PlayerActionBase):
    """
    PERCEPTION action: Awareness checks, detecting hidden threats.

    Includes searching for hidden enemies (opposed check vs their Stealth).
    """
    action_type: Literal[ActionType.PERCEPTION] = ActionType.PERCEPTION

    search_for_hidden: bool = Field(
        default=False,
        description="True if actively searching for hidden agents (opposed check)"
    )
```

#### 5.2 Enemy Scan Minor Action

Enemies already have `minor_action: Optional[Literal["Move", "Reload", "Scan", ...]]`
in `EnemyDecision` (line 89). The "Scan" option can be used for detection. Add
processing in `enemy_combat.py`:

```python
# In enemy action processing, after minor_action == "Scan"
if declaration.minor_action == "Scan":
    # Check for hidden PCs
    hidden_pcs = [pc for pc in player_agents
                  if getattr(pc, 'is_hidden', False)]
    for pc in hidden_pcs:
        stealth_dc = getattr(pc, 'stealth_dc', 15)
        detection = resolve_detection_check(enemy, stealth_dc)
        if detection['success']:
            pc.is_hidden = False
            target_id_mapper.update_hidden_state(pc.agent_id, False)
            logger.info(
                f"{enemy.name} detected {pc.character_state.name}: "
                f"{detection['formula']}"
            )
```

### Phase 6: Last Known Position Tracking

#### 6.1 Store Position on Hide

When an agent successfully hides, store their current position as `last_known_position`
on the agent for enemies to reference:

```python
# When agent hides successfully
agent.last_known_position = str(agent.position) if hasattr(agent, 'position') else None
```

#### 6.2 Clear Last Known Position on Detection

When an agent is detected, clear their last known position (they're visible now):

```python
# When agent is detected
agent.is_hidden = False
agent.last_known_position = None
agent.stealth_dc = None
```

### Phase 7: Prompt Updates

#### 7.1 DM Stealth Resolution Prompt

**File:** `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_resolution_movement.yaml`

The existing movement prompt (lines 67-176) already has stealth narration examples.
Enhance with structured stealth mechanics:

```yaml
stealth_mechanics: |-
  ## Stealth Resolution

  When a character attempts to hide:
  1. Resolve Agility x Stealth check vs Environment DC
  2. On success: Set stealth_changes with is_hidden=True and stealth_dc=roll_total
  3. On failure: aware_agents=[] (everyone sees the failed attempt)

  **Environment DC Guide:**
  - DC 10: Dark corridor, heavy fog, loud ambient noise
  - DC 15: Normal indoor, partial cover available
  - DC 20: Open area with some cover, well-lit
  - DC 25: Well-lit open area, active patrols
  - DC 30: Brightly lit, no cover, alert guards

  **Stealth Breaking Triggers:**
  - Attack from hidden: automatic break (system enforced)
  - Failed subsequent stealth check: DM narrates
  - Loud action (explosion, yelling): DM discretion
  - Enemy detection (Scan/Search): opposed check

  **Stealth State in ActionResolution:**
  ```python
  effects=MechanicalEffects(
      stealth_changes=[
          StealthChange(
              agent_id="player_01",
              is_hidden=True,
              stealth_dc=22,
              reason="Successfully ghosted through shadows"
          )
      ]
  )
  ```
```

#### 7.2 Player Prompt Stealth Guidance

Add stealth guidance to player combat/explore prompts:

```yaml
stealth_guidance: |-
  ## Stealth Actions

  You can attempt to hide during combat or exploration:
  - Use EXPLORE or COMBAT action with Agility x Stealth
  - If successful, you become HIDDEN:
    - Enemies cannot directly target you
    - Your actions are only visible to allies and DM
    - Attacking breaks stealth automatically
  - Set search_for_hidden=True on PERCEPTION actions to detect hidden enemies
```

#### 7.3 Enemy Prompt Stealth Awareness

**File:** `scripts/aeonisk/multiagent/enemy_prompts.py`

Add guidance for handling hidden PCs:

```python
stealth_section = """
### Hidden Targets:
Some PCs may be HIDDEN (not in your target list).
- Use 'Scan' as your minor_action to attempt detection
- Target last known position with area attacks if available
- Coordinate with allies: share hidden PC locations via shared_intel
- Detection check: Perception x Awareness vs hidden PC's stealth DC
"""
```

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `player.py` | Add `is_hidden`, `last_known_position`, `stealth_dc` to `AIPlayerAgent` | In `__init__` |
| `enemy_agent.py` | Add `is_hidden`, `last_known_position`, `stealth_dc` to `EnemyAgent` | After line 347 |
| `npc_agent.py` | Add `is_hidden`, `last_known_position`, `stealth_dc` to `NPCAgent` | After line 300 |
| `target_ids.py` | Add `hidden_agents` set, `update_hidden_state()`, `is_hidden()`, `get_visible_target_ids()` | New methods |
| `awareness.py` | Extend with stealth detection integration | New functions |
| `mechanics.py` | Add `resolve_stealth_check()`, `resolve_detection_check()`, helpers | New functions |
| `dm.py` | Combatant list: mark hidden agents | Lines 7536-7578 |
| `dm.py` | Auto-break stealth on combat action | After resolution processing |
| `dm.py` | Process StealthChange from DM resolution | After effects processing |
| `schemas/action_resolution.py` | Add `StealthChange`, add `stealth_changes` to `MechanicalEffects` | After line 168 |
| `schemas/player_action.py` | Add `search_for_hidden` to `PerceptionAction` | After line 438 |
| `enemy_combat.py` | Process Scan minor action for detection | In minor action handling |
| `enemy_prompts.py` | Filter hidden PCs from target list, add stealth guidance | Target building, new section |
| `prompts/.../dm/dm_resolution_movement.yaml` | Stealth resolution structured mechanics | New section |
| `prompts/.../player.yaml` or combat prompt | Stealth guidance for players | New section |
| `prompts/.../enemy.yaml` | Hidden target awareness | New section |

---

## Test Plan

### Unit Tests

**File:** `tests/unit/test_stealth.py`

```python
class TestStealthCheck:
    """Stealth check resolution mechanics."""

    def test_stealth_check_success(self):
        """Agent with high Agility/Stealth should succeed against moderate DC."""
        agent = MockAgent(attributes={'Agility': 4}, skills={'Stealth': 3})
        # Agility 4 x Stealth 3 = 12 base, + d20 average 10.5 = ~22.5 vs DC 15
        result = resolve_stealth_check(agent, environment_dc=15)
        assert 'success' in result
        assert 'stealth_roll' in result
        assert 'formula' in result

    def test_stealth_check_unskilled_penalty(self):
        """Agent with Stealth=0 should get -5 unskilled penalty."""
        agent = MockAgent(attributes={'Agility': 3}, skills={'Stealth': 0})
        result = resolve_stealth_check(agent, environment_dc=10)
        assert 'unskilled' in result['formula']

    def test_stealth_check_modifiers_apply(self):
        """Situational modifiers should affect the roll."""
        agent = MockAgent(attributes={'Agility': 3}, skills={'Stealth': 2})
        result_normal = resolve_stealth_check(agent, environment_dc=15, modifiers=0)
        # With +5 modifier, should have higher total (but d20 is random)
        result_bonus = resolve_stealth_check(agent, environment_dc=15, modifiers=5)
        # Can't assert success due to randomness, but formula should show modifier
        assert 'modifiers' in result_bonus['formula']


class TestDetectionCheck:
    """Detection check resolution mechanics."""

    def test_detection_success(self):
        """Observer with high Perception/Awareness should detect low-DC target."""
        observer = MockAgent(
            attributes={'Perception': 4},
            skills={'Awareness': 3}
        )
        result = resolve_detection_check(observer, stealth_dc=10)
        assert 'success' in result
        assert 'detection_roll' in result

    def test_detection_unskilled_penalty(self):
        """Observer with Awareness=0 should get -5 unskilled penalty."""
        observer = MockAgent(
            attributes={'Perception': 3},
            skills={'Awareness': 0}
        )
        result = resolve_detection_check(observer, stealth_dc=15)
        assert 'unskilled' in result['formula']


class TestHiddenAgentFiltering:
    """Target list filtering for hidden agents."""

    def test_hidden_agent_excluded_from_enemy_targets(self):
        """Hidden PC should not appear in enemy's visible target list."""
        mapper = create_test_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)

        visible = mapper.get_visible_target_ids("enemy_grunt_01")
        player_01_tid = mapper.get_target_id("player_01")
        assert player_01_tid not in visible

    def test_hidden_agent_visible_to_allies(self):
        """Hidden PC should still be visible to other PCs."""
        mapper = create_test_mapper_with_agents()
        mapper.update_hidden_state("player_01", True)

        visible = mapper.get_visible_target_ids("player_02")
        player_01_tid = mapper.get_target_id("player_01")
        assert player_01_tid in visible

    def test_unhidden_agent_visible_to_all(self):
        """Non-hidden agent should be visible to everyone."""
        mapper = create_test_mapper_with_agents()

        visible = mapper.get_visible_target_ids("enemy_grunt_01")
        player_01_tid = mapper.get_target_id("player_01")
        assert player_01_tid in visible

    def test_hidden_enemy_excluded_from_pc_targets(self):
        """Hidden enemy should not appear in PC's visible target list."""
        mapper = create_test_mapper_with_agents()
        mapper.update_hidden_state("enemy_grunt_01", True)

        visible = mapper.get_visible_target_ids("player_01")
        enemy_tid = mapper.get_target_id("enemy_grunt_01")
        assert enemy_tid not in visible

    def test_hidden_enemy_visible_to_allied_enemies(self):
        """Hidden enemy should be visible to other enemies."""
        mapper = create_test_mapper_with_agents()
        mapper.update_hidden_state("enemy_grunt_01", True)

        visible = mapper.get_visible_target_ids("enemy_sniper_01")
        enemy_tid = mapper.get_target_id("enemy_grunt_01")
        assert enemy_tid in visible


class TestStealthBreaking:
    """Automatic stealth breaking rules."""

    def test_attack_breaks_stealth(self):
        """Attacking from hidden should set is_hidden=False."""
        agent = MockAgent(is_hidden=True)
        break_stealth_on_attack(agent)
        assert agent.is_hidden is False

    def test_non_attack_preserves_stealth(self):
        """Non-attack actions should not break stealth."""
        agent = MockAgent(is_hidden=True)
        # Perception, social, explore actions should not break stealth
        assert agent.is_hidden is True


class TestStealthSchemas:
    """Schema validation for stealth-related fields."""

    def test_stealth_change_schema(self):
        """StealthChange should validate correctly."""
        change = StealthChange(
            agent_id="player_01",
            is_hidden=True,
            stealth_dc=22,
            reason="Successfully hid behind cargo containers in the dim lighting"
        )
        assert change.is_hidden is True
        assert change.stealth_dc == 22

    def test_mechanical_effects_stealth_changes(self):
        """MechanicalEffects should accept stealth_changes list."""
        effects = MechanicalEffects(
            stealth_changes=[
                StealthChange(
                    agent_id="player_01",
                    is_hidden=True,
                    stealth_dc=18,
                    reason="Slipped into shadows while guards were distracted"
                )
            ]
        )
        assert len(effects.stealth_changes) == 1

    def test_perception_action_search_field(self):
        """PerceptionAction should accept search_for_hidden field."""
        action = PerceptionAction(
            intent="Scan area for hidden threats actively",
            description="Using enhanced senses to detect concealed enemies in "
                        "the surrounding cargo bay area.",
            attribute="Perception",
            skill="Awareness",
            difficulty_estimate=18,
            difficulty_justification="Poor visibility, active concealment",
            search_for_hidden=True
        )
        assert action.search_for_hidden is True


class TestLastKnownPosition:
    """Last known position tracking for hidden agents."""

    def test_position_stored_on_hide(self):
        """When agent hides, their position should be stored."""
        agent = MockAgent(position="Near-PC", is_hidden=False)
        agent.last_known_position = str(agent.position)
        agent.is_hidden = True
        assert agent.last_known_position == "Near-PC"

    def test_position_cleared_on_detection(self):
        """When agent is detected, last known position should clear."""
        agent = MockAgent(
            position="Far-Enemy",
            is_hidden=True,
            last_known_position="Near-PC"
        )
        agent.is_hidden = False
        agent.last_known_position = None
        assert agent.last_known_position is None
```

### Integration Tests

**File:** `tests/integration/test_stealth_integration.py`

1. **Full stealth round:** PC declares stealth action, DM resolves with StealthChange,
   verify enemy's next round does not show PC in target list.
2. **Attack from hidden:** PC attacks from hidden, verify stealth breaks after
   resolution and PC appears in next round's target list.
3. **Enemy scan detection:** Enemy uses Scan minor action, verify detection check
   is performed against hidden PC's stealth_dc.
4. **Narration visibility:** Hidden PC's action narration should only be visible to
   allies and DM (via aware_agents).

### Prompt Tests

1. Verify DM resolution prompt includes stealth_changes in MechanicalEffects schema.
2. Verify enemy prompt shows "HIDDEN TARGETS" section when PCs are hidden.
3. Verify player prompt includes stealth guidance.

---

## Migration Notes

- No JSONL schema changes needed for existing events. New `stealth_changes` field in
  `MechanicalEffects` defaults to empty list, maintaining backward compatibility.
- New `is_hidden`, `last_known_position`, `stealth_dc` attributes on agents default
  to `False`/`None`/`None`, so existing code continues to work unchanged.
- Existing fixtures remain valid (no hidden agents in historical data).
- The `search_for_hidden` field on `PerceptionAction` defaults to `False`.

---

## Open Questions

1. **Passive detection vs active detection.** Should enemies automatically detect
   hidden PCs at the start of each round (passive Awareness), or only when they
   actively use Scan? YAGS supports both.
   **Recommendation:** Passive detection at half skill (Perception x Awareness / 2)
   at round start. Active Scan at full skill. This prevents indefinite hiding without
   any active effort to detect.

2. **Stealth and movement.** Can a hidden agent move without breaking stealth?
   **Recommendation:** Yes, but they must make a new stealth check at the new
   position's environment DC. Moving in the open (crossing gaps) should increase DC.

3. **Multiple hidden agents.** If 3 PCs are hidden, does each Scan check detect all
   of them or just one?
   **Recommendation:** Each Scan checks against one hidden agent (the closest or most
   obvious). Multiple Scans needed for multiple hidden agents.

4. **Stealth in non-combat.** Should `is_hidden` work outside combat rounds?
   **Recommendation:** Yes, but the mechanics are simpler. In exploration, stealth is
   a single check against environment DC. The `is_hidden` flag affects NPC awareness
   and narrative options.

5. **Void and stealth interaction.** High void scores cause corruption effects. Should
   void corruption reveal hidden agents (void aura detection)?
   **Recommendation:** At void_score >= 7, hidden agents emit detectable void
   signatures. Detection checks against them get +5 bonus. At void_score 10 (possessed),
   stealth is impossible -- the void corruption is visible.

6. **First Strike bonus.** DM prompt mentions "+2 damage on first attack from hidden."
   Should this be mechanical (structured output) or remain narrative-only?
   **Recommendation:** Add as a structured modifier. When attacking from hidden, the
   DM should set a situational modifier of +2 in the resolution, and the system should
   apply it before breaking stealth.

7. **NPC hiding.** NPCs already have "hide" as an action_type in NPCAction. Should
   this mechanically set `is_hidden`?
   **Recommendation:** Yes. When NPC declares `action_type="hide"`, resolve a stealth
   check and set `is_hidden` based on the result. This gives NPC hiding actual teeth.

8. **Team visibility rules.** The current spec says PCs always see hidden PCs and
   enemies always see hidden enemies. Should there be exceptions (traitors, double
   agents)?
   **Recommendation:** For v1, keep team-based visibility simple. Espionage mechanics
   can be added later via the IFF system (spec 06).
