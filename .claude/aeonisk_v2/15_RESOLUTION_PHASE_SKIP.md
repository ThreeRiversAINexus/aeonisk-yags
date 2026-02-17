# P1: Resolution Phase Skip (Action Preemption)

**Priority:** P1 (combat coherence + ML data quality)
**Branch:** `intention-lethality-mismatch`
**Evidence:** Baseline datamining of 25 sessions x 5 models; code audit of adjudication loop asymmetry
**Related specs:** 14_CONDITIONS (condition ticking must work for condition-based skip triggers)

---

## Problem Statement

During the adjudication (resolution) phase, actions resolve in descending initiative
order -- fastest first. When an earlier resolution changes the tactical or narrative
reality, later actions that depend on that reality should be skippable. Currently the
system has three gaps that allow incoherent outcomes and produce misleading ML
training data.

### Gap 1: Player Actions Bypass All State Validation

Enemy actions pass through `ActionValidator` checks (defeated, surrendered,
incapacitated) in `enemy_combat.py:975-998` before resolution. Player actions in
`session.py:2063-2244` skip directly to DM adjudication with no equivalent check.
If Enemy A stuns Player C in an earlier resolution, Player C's action still gets
sent to the DM for a full LLM call. The DM *may* narratively acknowledge the stun,
but there is no mechanical guarantee -- the engine happily applies whatever effects
the DM generates, including damage from an unconscious character.

**Impact:** Mechanically dead or incapacitated PCs can deal damage, advance clocks,
and trigger soulcredit assessments. The JSONL log records these impossible actions as
valid, corrupting ML training data.

### Gap 2: No Narrative Invalidation Pathway

Even when both players and enemies pass mechanical state checks, actions can become
meaningless due to narrative changes earlier in the round:

1. **Objective completed:** Player A steals the data chip. Enemy B's declared action
   was to steal the same data chip. Enemy B's action should be skippable -- the
   objective no longer exists.

2. **Target narratively downed:** Player A shoots Enemy B with a critical hit. The
   DM narrates Enemy B collapsing but the engine hasn't processed the damage into
   `resolution_state.defeated` yet (it happens after the narration). Enemy B's
   later action resolves normally.

3. **Tactical situation changed:** Player A collapses a corridor with explosives.
   Enemy C's declared "advance through corridor" action is now impossible.

The DM sees earlier narrations via `previous_context` (last 3 resolutions injected
into the DM prompt at `dm.py:5228-5249`), but has **no structured output field** to
declare "this action is preempted." The DM can only narrate around it, and the
engine still applies all mechanical effects.

**Impact:** DM-generated effects from preempted actions (damage, conditions, void
changes) are applied to game state, creating impossible outcomes. JSONL logs record
full mechanical effects for actions that narratively didn't happen.

### Gap 3: Skipped Actions Are Invisible

When `session.py:2039-2061` skips a dead/extracted player, it logs a minimal
`log_enemy_action` event (reusing the enemy logging method) with `action_type:
"skipped"`. This produces malformed training data: a player action logged as an
enemy action, with no narration visible to other agents. The skip doesn't enter
`all_resolutions`, so later agents' `previous_context` has no record that the
action was skipped.

**Impact:** Later-resolving agents have no awareness that an earlier agent was
incapacitated and skipped. The DM may narrate as if the skipped agent is still
active, creating contradictions in the narrative record.

### Motivating Examples

**Example 1 -- Hard skip (mechanical):**
Player A (init 22) shoots Enemy B (init 14) and deals lethal damage. Enemy B is
marked defeated via `_mark_defeated_from_resolution()`. Enemy B's later action
should be auto-skipped without an LLM call, with a templated narration entered
into `all_resolutions`.

**Example 2 -- Narrative skip (DM judgment):**
Player A (init 20) steals the encrypted data chip from the terminal. Enemy B
(init 12) declared "steal data chip from terminal." The DM should be able to set
`action_skipped=True` with `skip_reason="objective already completed by faster
agent"` and narrate Enemy B arriving at an empty terminal.

**Example 3 -- Cross-type skip (enemy stuns player):**
Enemy X (init 24) stuns Player C (init 16) with a shock baton (stuns >= 6 =
incapacitated). Player C's action should be auto-skipped before any LLM call.
Currently, Player C's action has no validation and gets sent to the DM regardless.

---

## Current Implementation

### Enemy Action Validation (The Model)

Enemy actions in `enemy_combat.py:975-998` use `ActionValidator` before resolution:

```python
# enemy_combat.py:975-998
can_proceed, failure_reason = ActionValidator.can_attack(
    enemy.agent_id,
    target_id,
    resolution_state
)

if not can_proceed:
    target_name = target.name if hasattr(target, 'name') else str(target_id)
    invalidation_msg = generate_invalidation_message(
        enemy.name, 'attack', failure_reason, target_name
    )
    return {
        'enemy_id': enemy.agent_id,
        'character_name': enemy.name,
        'action': 'attack',
        'result': 'invalidated',
        'failure_reason': failure_reason,
        'narration': invalidation_msg
    }
```

This pattern:
1. Checks `ResolutionState` for defeated/surrendered/incapacitated states
2. Generates a templated narration via `generate_invalidation_message()`
3. Returns an `invalidated` result dict that enters `all_resolutions`
4. **No LLM call made** -- purely mechanical

### Player Action Validation (The Gap)

Player actions in `session.py:2063-2244` have a single pre-check:

```python
# session.py:2039-2042
if not agent.is_in_combat:
    skip_reason = "extracted by medevac" if agent.is_extracted else "dead/unconscious"
    # ... logs via log_enemy_action (wrong method) and continues
```

This only catches `is_in_combat=False` (permanent death or extraction). It does NOT
check `resolution_state` for mid-round state changes:
- Not checked: `resolution_state.is_defeated(agent.agent_id)`
- Not checked: `resolution_state.is_incapacitated(agent.agent_id)`
- Not checked: `resolution_state.is_surrendered(agent.agent_id)`

After this single check, the code proceeds directly to building the DM adjudication
message at line 2088 and awaiting the LLM response.

### Resolution State Tracking

`ResolutionState` (tactical_resolution.py:40-191) tracks five categories of
mid-round state changes:
- `defeated: Set[str]` -- killed, unconscious, fled
- `surrendered: Set[str]` -- negotiated down, intimidated
- `incapacitated: Set[str]` -- stun KO, non-lethal unconsciousness
- `fled_npcs: Set[str]` -- NPCs that left the scene
- `claimed_tokens: Dict[str, str]` -- tactical tokens claimed

The state is updated after each PC resolution via two helper functions:
- `_parse_surrender_from_resolution()` -- detects surrendered enemies from narration
- `_mark_defeated_from_resolution()` -- checks enemy HP and marks 0-HP enemies

### Previous Context Injection

At `dm.py:5228-5249`, previous resolutions are formatted into the DM prompt:

```python
if previous_resolutions:
    previous_items = []
    for prev in previous_resolutions[-3:]:  # Last 3 to keep prompt manageable
        char_name = prev.get('character_name', 'Unknown')
        narration = prev.get('narration', '')
        if narration:
            previous_items.append(f"- {char_name}: {narration}")

    if previous_items:
        action['previous_context'] = f"""
**CRITICAL - EARLIER ACTIONS THIS ROUND:**
The following actions ALREADY resolved (faster initiative):
{chr(10).join(previous_items)}

**CONSISTENCY REQUIREMENTS:**
- Your narration MUST acknowledge these established facts
- DO NOT contradict details from earlier resolutions
"""
```

This provides the DM with narrative context but no structured mechanism to declare
that the current action is preempted. The DM can only work around it in narration
text -- the engine still applies all mechanical effects regardless.

### ActionValidator (tactical_resolution.py:197-300)

Three validation methods exist:
- `can_attack(attacker_id, target_id, resolution_state)` -- checks both attacker and target
- `can_claim_token(claimant_id, token_name, resolution_state)` -- checks claimant + token availability
- `can_move(mover_id, resolution_state)` -- checks mover only

All return `(bool, Optional[str])` tuples. Used by enemy combat but not by the
player adjudication loop.

### Invalidation Messages (tactical_resolution.py:307-364)

`generate_invalidation_message()` produces templated narrations for each failure
reason. Covers: attacker/target defeated, attacker/target incapacitated,
attacker/claimant/mover surrendered, token taken. These narrations are emoji-tagged
and mechanical in tone (not DM-quality prose).

---

## Design Decisions

### D1: Hard Auto-Skip Extends ActionValidator to Players

Before sending a player action to the DM (before the LLM call at `session.py:2100`),
check `ResolutionState` for the player's agent_id:
- `is_defeated()` --> auto-skip
- `is_incapacitated()` --> auto-skip
- `is_surrendered()` --> auto-skip (for completeness, unlikely for PCs)

Auto-skip uses `generate_invalidation_message()` for the narration. No LLM call is
made. The skip produces a full result dict that enters `all_resolutions` with the
same structure as enemy invalidation results, plus `action_skipped: True`.

**Rationale:** Dead and unconscious agents cannot act. This is a mechanical fact,
not a narrative judgment. Sending the action to the DM wastes an LLM call and risks
the DM generating effects for an agent that can't produce them.

### D2: Narrative Skip Reuses the Existing ActionResolution LLM Call

For narrative preemption (objective completed, target downed narratively, tactical
situation changed), no extra LLM call is needed. The DM already resolves each
action with one LLM call and already sees `previous_context` with earlier narrations.

Two new fields on `ActionResolution`:
- `action_skipped: bool = False`
- `skip_reason: Optional[str] = None`

When the DM determines that an action is preempted, it outputs
`action_skipped=True`, provides `skip_reason`, and writes narration describing the
preemption (what the agent tried to do and why it failed). The engine reads
`action_skipped` and ignores all `effects` fields.

**Rationale:** This is a zero-cost solution -- same number of LLM calls, same
prompt structure. The DM already has the context to make this judgment. We just give
it a structured output field to express it.

### D3: DM-Authoritative for Narrative, Engine-Authoritative for Hard Skips

Two clear authority boundaries:

| Skip Type | Authority | Mechanism | LLM Call? |
|-----------|-----------|-----------|-----------|
| Hard skip (defeated/incapacitated) | Engine | `ActionValidator` check | No |
| Narrative skip (preempted/meaningless) | DM | `action_skipped` field in `ActionResolution` | Yes (existing call) |

The engine ALWAYS applies hard skips before the DM sees the action. The DM NEVER
needs to judge mechanical impossibility -- only narrative preemption.

**Rationale:** Hard skips are deterministic and mechanical. Narrative skips require
contextual judgment that only the LLM can provide. This clean split avoids
duplication and keeps each authority layer doing what it does best.

### D4: Skip Narration Is Full and Visible

Both hard and narrative skips produce narration that:
1. Enters `all_resolutions` (available to `previous_context` for later actions)
2. Prints to stdout (visible to human observers)
3. Logs to JSONL with `action_skipped=True` and `skip_reason`
4. Is indistinguishable from a normal resolution in `previous_context` (the DM
   sees it as a regular earlier resolution -- the fact that it was a skip is
   transparent from a narrative perspective)

**Rationale:** Silent skips create narrative gaps. If Player C was stunned and their
turn was skipped, later agents need to know Player C is down. The narration makes
this visible to all agents without requiring special handling.

### D5: Engine Ignores Effects When `action_skipped=True`

When processing a resolution with `action_skipped=True`, the engine skips all
effect application regardless of what the LLM populated in the `effects` field:
- No damage applied
- No conditions applied
- No void changes applied
- No soulcredit changes applied
- No clock updates applied
- No inventory/purchase/crafting effects processed

This is a safety net: even if the LLM populates effects on a skipped action (which
it shouldn't, but LLMs are imperfect), the engine does not apply them.

**Rationale:** The Pydantic validator will warn (not error) if effects are populated
on a skipped action. This catches LLM compliance issues in the logs without
crashing the session. But the engine's behavior is unconditional: `action_skipped=True`
means zero mechanical impact, period.

### D6: Enhanced `previous_context` Includes Mechanical State

Currently `previous_context` only includes narration text. For skip-aware
resolution, the DM benefits from seeing mechanical state alongside narration:

```
**EARLIER ACTIONS THIS ROUND:**
- Sera Karsel: [13/27 HP, Stunned -4] "Sera's shot catches the enforcer..."
- Grunt Alpha: [DEFEATED] "The enforcer crumples, weapon skidding across the deck."
- Kade Revel: [SKIPPED - incapacitated] "Kade lies motionless where the shock blast dropped him."
```

This enhancement is additive -- narration is unchanged, but HP/status/skip-state
prefixes give the DM structured awareness of the tactical situation without parsing
narration text.

**Rationale:** The DM currently infers tactical state from narration prose. Adding
mechanical state tags makes skip decisions more reliable. An agent tagged
`[DEFEATED]` is unambiguously down -- no need to parse "crumples" or "collapses."

---

## Proposed Solution

### Phase 1: Hard Auto-Skip (Extend ActionValidator to Players)

#### Insertion Point: `session.py:2063` (Before DM Adjudication)

After the existing `is_in_combat` check (line 2039-2061) and before processing
buffered actions (line 2065), add ActionValidator checks against `resolution_state`.

**Pseudocode:**

```python
# session.py - inside the initiative loop, agent_type == 'player' branch
# After line 2061 (existing is_in_combat check)

# Phase 1: Hard auto-skip for mid-round state changes
if resolution_state.is_defeated(agent.agent_id):
    skip_narration = generate_invalidation_message(
        agent.character_state.name, 'action', 'attacker_defeated'
    )
    _log_player_auto_skip(
        agent, 'defeated', skip_narration, all_resolutions, mechanics
    )
    continue

if resolution_state.is_incapacitated(agent.agent_id):
    skip_narration = generate_invalidation_message(
        agent.character_state.name, 'action', 'attacker_incapacitated'
    )
    _log_player_auto_skip(
        agent, 'incapacitated', skip_narration, all_resolutions, mechanics
    )
    continue
```

#### Helper Function: `_log_player_auto_skip()`

```python
def _log_player_auto_skip(
    agent, skip_type: str, narration: str,
    all_resolutions: list, mechanics
):
    """
    Log a hard auto-skipped player action.

    Produces a result dict matching enemy invalidation format that enters
    all_resolutions (for previous_context) and JSONL (for ML training).
    """
    result = {
        'player_id': agent.agent_id,
        'character_name': agent.character_state.name,
        'action_type': 'skipped',
        'action_skipped': True,
        'skip_reason': skip_type,
        'narration': narration,
        'result': 'invalidated',
        'effects': {}  # No mechanical effects for skipped actions
    }

    # Enter all_resolutions for previous_context visibility
    all_resolutions.append(result)

    # Print to stdout
    print(f"\n  {narration}")

    # Log to JSONL
    if mechanics and hasattr(mechanics, 'jsonl_logger') and mechanics.jsonl_logger:
        mechanics.jsonl_logger.log_action_resolution(
            round_num=mechanics.current_round,
            player_id=agent.agent_id,
            character_name=agent.character_state.name,
            action_type='skipped',
            narration=narration,
            effects={'action_skipped': True, 'skip_reason': skip_type},
            success_tier='not_applicable',
            margin=0,
            roll_details=None
        )
```

### Phase 2: DM Narrative Skip (ActionResolution Schema Extension)

#### Schema Changes: `schemas/action_resolution.py`

Add two fields to `ActionResolution` (after `aware_agents`, before validators):

```python
# Action preemption (Phase 2 skip system)
action_skipped: bool = Field(
    default=False,
    description="""True if this action was preempted by earlier events this round.

    Set this to True when a previous resolution rendered this action impossible
    or meaningless:
    - Agent was incapacitated by an earlier attack (hard skip handles most cases,
      but DM can also flag this for narrative-only incapacitation)
    - Objective was already completed by a faster agent
    - Target was narratively downed before this agent's turn
    - Tactical situation changed (route blocked, environment destroyed)

    When action_skipped=True:
    - The engine ignores ALL effects (damage, conditions, void, soulcredit, etc.)
    - The narration field MUST still be populated with a description of what the
      agent tried to do and why it was preempted
    - skip_reason MUST be populated with a brief explanation

    Example:
        ActionResolution(
            action_skipped=True,
            skip_reason="Target collapsed from earlier gunshot before this agent could act",
            narration="The enforcer raises his weapon, but Sera's shot already sent
                       the target sprawling. He lowers the barrel -- no point firing
                       at a body on the ground.",
            success_tier=SuccessTier.FAILURE,
            margin=0,
            effects=MechanicalEffects()  # Empty -- engine ignores anyway
        )
    """
)

skip_reason: Optional[str] = Field(
    default=None,
    min_length=10,
    max_length=300,
    description="""Why the action was preempted (required when action_skipped=True).

    Brief narrative explanation of what changed between declaration and resolution.
    Examples:
    - "Target collapsed from wounds before this agent could act"
    - "Data chip already extracted by faster operative"
    - "Corridor collapsed by earlier explosion, route impassable"
    """
)
```

#### Pydantic Validator

Add a model validator to `ActionResolution`:

```python
@model_validator(mode='after')
def validate_skip_fields(self):
    """Validate skip field consistency."""
    if self.action_skipped:
        if not self.skip_reason:
            import warnings
            warnings.warn(
                "action_skipped=True but skip_reason is empty. "
                "Provide a reason for ML training data quality."
            )
        # Warn (not error) if effects are populated on a skipped action
        if self.effects:
            has_effects = (
                self.effects.damage
                or self.effects.conditions
                or self.effects.void_changes
                or self.effects.healing
            )
            if has_effects:
                import warnings
                warnings.warn(
                    "action_skipped=True but effects contain non-empty fields. "
                    "Engine will ignore these effects."
                )
    elif self.skip_reason:
        import warnings
        warnings.warn(
            "skip_reason is set but action_skipped=False. "
            "Set action_skipped=True or remove skip_reason."
        )
    return self
```

#### Engine-Side Effect Suppression

In the resolution processing code in `dm.py` (where `ActionResolution` effects are
extracted and applied), add a guard at the top of effect processing:

```python
# In dm.py effect processing (after structured output extraction)
if action_resolution_data.get('action_skipped', False):
    logger.info(
        f"Action skipped for {character_name}: {action_resolution_data.get('skip_reason', 'unknown')}"
    )
    # Return resolution with narration but no mechanical effects applied
    # The narration still enters all_resolutions for previous_context
    return {
        'character_name': character_name,
        'narration': action_resolution_data.get('narration', ''),
        'action_skipped': True,
        'skip_reason': action_resolution_data.get('skip_reason'),
        'effects': {}  # Explicitly empty -- engine ignores LLM-populated effects
    }
```

In `session.py`, the existing effect processing block (lines 2163-2241 -- purchases,
crafting, attunement, item discovery, stabilization) should be wrapped:

```python
# session.py - after resolution_data is collected
if resolution_data:
    all_resolutions.append(resolution_data)

    # Skip all effect processing for preempted actions
    if resolution_data.get('action_skipped', False):
        skip_reason = resolution_data.get('skip_reason', 'preempted')
        logger.info(f"Skipping effect processing for {agent.character_state.name}: {skip_reason}")
        # Still update resolution_state for downstream awareness
        # (but no surrenders/defeats to parse from a skipped action)
    else:
        # Existing effect processing block (purchases, crafting, etc.)
        _parse_surrender_from_resolution(resolution_data, resolution_state, target_id_mapper)
        _mark_defeated_from_resolution(self.enemy_combat, resolution_state)
        # ... purchase, crafting, attunement, item_discovery, stabilization ...
```

#### Prompt Guidance Additions

Add to the DM resolution prompt modules (combat, social, investigation, etc.):

```yaml
# Addition to dm_resolution_*.yaml prompt modules

action_preemption: |
  **ACTION PREEMPTION:**
  If a previous resolution this round rendered this action impossible or
  meaningless, you MUST set action_skipped=True and provide skip_reason.

  Triggers for action_skipped=True:
  - Agent was incapacitated, stunned, or downed by an earlier action
  - The action's objective was already completed by a faster agent
  - The action's target was eliminated or removed by an earlier action
  - The tactical environment changed (blocked route, destroyed cover, etc.)

  When skipping an action:
  1. Set action_skipped=True
  2. Set skip_reason to a brief explanation (10-300 chars)
  3. Write narration describing what the agent TRIED to do and why it failed
  4. Set success_tier to FAILURE and margin to 0
  5. Leave effects empty (MechanicalEffects with no entries)

  IMPORTANT: Only skip when the action is truly impossible or meaningless.
  If the situation changed but the action could still partially succeed
  (e.g., target wounded but not down), resolve normally with adjusted difficulty.
```

#### Enhanced `previous_context` Format

Update `dm.py:5228-5249` to include mechanical state tags:

```python
if previous_resolutions:
    previous_items = []
    for prev in previous_resolutions[-3:]:
        char_name = prev.get('character_name', 'Unknown')
        narration = prev.get('narration', '')

        # Add mechanical state prefix for DM awareness
        state_prefix = ""
        if prev.get('action_skipped'):
            skip_type = prev.get('skip_reason', 'preempted')
            state_prefix = f"[SKIPPED - {skip_type}] "
        elif prev.get('result') == 'invalidated':
            state_prefix = "[INVALIDATED] "

        if narration:
            previous_items.append(f"- {char_name}: {state_prefix}{narration}")
```

---

## Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `schemas/action_resolution.py` | After line 395 | Add `action_skipped`, `skip_reason` fields to `ActionResolution` |
| `schemas/action_resolution.py` | After new fields | Add `validate_skip_fields` model validator |
| `session.py` | ~2063 (after `is_in_combat` check) | Add `ActionValidator` checks for player agents against `resolution_state` |
| `session.py` | ~2063 | Add `_log_player_auto_skip()` helper function |
| `session.py` | ~2153-2241 | Wrap effect processing block with `action_skipped` guard |
| `dm.py` | ~5228-5249 | Enhance `previous_context` format with mechanical state tags |
| `dm.py` | Effect processing section | Add `action_skipped` guard before applying effects |
| `tactical_resolution.py` | ~307-364 | Add player-oriented invalidation message templates (optional -- existing templates may suffice) |
| `prompts/claude/en/dm/dm_resolution_*.yaml` | End of each file | Add action preemption guidance block |

---

## Test Plan (TDD)

All tests go in `tests/unit/test_resolution_phase_skip.py`. Tests are written FIRST
before any implementation code.

### Test 1: `test_player_auto_skip_defeated`

**Setup:** Create a mock player agent with `agent_id="player_01"`. Create a
`ResolutionState` with `defeated={"player_01"}`. Simulate the adjudication loop
entry for this player.

**Assert:**
- DM adjudication message is NOT sent (no LLM call)
- `all_resolutions` contains one entry with `action_skipped=True`
- Entry contains `skip_reason="defeated"` and non-empty `narration`
- Player's action is consumed (not left pending)

### Test 2: `test_player_auto_skip_incapacitated`

**Setup:** Same as Test 1 but with `incapacitated={"player_01"}`.

**Assert:** Same assertions as Test 1, with `skip_reason="incapacitated"`.

### Test 3: `test_player_not_skipped_when_healthy`

**Setup:** Create a mock player with `agent_id="player_01"`. Create an empty
`ResolutionState`. Simulate the adjudication loop entry.

**Assert:**
- DM adjudication message IS sent (LLM call proceeds)
- `all_resolutions` does not contain a skip entry before the DM responds

### Test 4: `test_action_skipped_field_accepted_by_schema`

**Setup:** Create an `ActionResolution` with `action_skipped=True`,
`skip_reason="Target already eliminated"`, narration, `success_tier=FAILURE`,
`margin=0`, empty `MechanicalEffects`.

**Assert:** Pydantic validation passes. All fields are accessible.

### Test 5: `test_action_skipped_warns_on_populated_effects`

**Setup:** Create an `ActionResolution` with `action_skipped=True` AND
`effects.damage` populated with a `DamageEffect`.

**Assert:** Pydantic validation emits a warning (not error). The model is still
valid.

### Test 6: `test_skip_reason_required_warning`

**Setup:** Create an `ActionResolution` with `action_skipped=True` but
`skip_reason=None`.

**Assert:** Pydantic validation emits a warning about missing skip_reason.

### Test 7: `test_effects_ignored_when_skipped`

**Setup:** Create a resolution dict with `action_skipped=True` and effects
containing damage, conditions, and void changes.

**Assert:** The engine effect processing code:
- Does NOT apply damage to any character
- Does NOT add conditions to any character
- Does NOT modify void scores
- Does NOT modify soulcredit
- DOES include narration in the returned result

### Test 8: `test_skip_in_previous_context`

**Setup:** Create an `all_resolutions` list containing a skipped action entry.
Run the `previous_context` builder code.

**Assert:**
- The skipped action's narration appears in the formatted `previous_context` string
- The `[SKIPPED - ...]` prefix is present in the context

### Test 9: `test_skip_logged_to_jsonl`

**Setup:** Mock `jsonl_logger`. Run the player auto-skip path.

**Assert:**
- `log_action_resolution` is called exactly once
- Call args include `action_skipped=True` in effects
- Call args include `skip_reason` in effects
- Call args include narration text

### Test 10: `test_enemy_skip_still_works`

**Setup:** Verify that existing enemy `ActionValidator` invalidation still works
correctly after changes. Create an enemy with `agent_id` in
`resolution_state.defeated`. Run `enemy_combat.execute_enemy_action()`.

**Assert:**
- Result has `result="invalidated"` (existing behavior unchanged)
- No regressions in enemy skip path

### Test 11: `test_skip_reason_without_action_skipped_warns`

**Setup:** Create an `ActionResolution` with `action_skipped=False` but
`skip_reason="some reason"`.

**Assert:** Pydantic validation emits a warning about inconsistent fields.

### Test 12: `test_enhanced_previous_context_format`

**Setup:** Create `all_resolutions` with:
1. A normal resolution (character at 13/27 HP)
2. An invalidated enemy action (`result="invalidated"`)
3. A DM narrative skip (`action_skipped=True`)

Run the enhanced `previous_context` builder.

**Assert:**
- Entry 2 has `[INVALIDATED]` prefix
- Entry 3 has `[SKIPPED - ...]` prefix
- Entry 1 has no prefix (normal resolution)

---

## JSONL Logging

### Existing Event Type: `action_resolution`

The `action_resolution` event type already exists and handles both player and enemy
resolutions. For skipped actions, extend the existing event with additional fields
in the `effects` dict:

```json
{
    "event_type": "action_resolution",
    "round": 3,
    "data": {
        "player_id": "player_kade",
        "character_name": "Kade Revel",
        "action_type": "skipped",
        "narration": "Kade lies motionless where the shock blast dropped him, unable to act.",
        "success_tier": "not_applicable",
        "margin": 0,
        "effects": {
            "action_skipped": true,
            "skip_reason": "incapacitated",
            "skip_type": "hard"
        }
    }
}
```

For DM narrative skips:

```json
{
    "event_type": "action_resolution",
    "round": 3,
    "data": {
        "player_id": "player_sera",
        "character_name": "Sera Karsel",
        "action_type": "attack",
        "narration": "Sera raises her rifle but the enforcer is already down...",
        "success_tier": "failure",
        "margin": 0,
        "effects": {
            "action_skipped": true,
            "skip_reason": "Target collapsed from earlier gunshot",
            "skip_type": "narrative"
        }
    }
}
```

**No new event type needed.** The `action_skipped` field within `effects` is
sufficient for ML pipeline filtering. Downstream analysis can:
- Filter on `effects.action_skipped == true` to exclude skipped actions from
  damage/effect analysis
- Use `effects.skip_type` to distinguish hard vs narrative skips
- Use `effects.skip_reason` for skip reason categorization

---

## Dependencies

### Hard Dependency: 14_CONDITIONS (Condition Pipeline)

Condition-based auto-skip (e.g., stun accumulation >= 6 triggers incapacitation)
depends on conditions being correctly tracked and ticked. Currently:
- Condition duration is hardcoded to 3 and never ticked (Bug 3 in 14_CONDITIONS)
- The `affects` field is dead code (Bug 5 in 14_CONDITIONS)

Once 14_CONDITIONS is implemented, the hard auto-skip can also check active
conditions: "if agent has Stunned condition with penalty <= -6, mark incapacitated
in resolution_state." This is additive -- the current `is_incapacitated()` check
works with the existing stun tracking, and condition-based incapacitation adds a
second pathway.

**Ordering:** 14_CONDITIONS should be implemented before or concurrently with
Phase 1 of this spec. Phase 2 (DM narrative skip) has no dependency on conditions.

### Soft Dependency: 08_SUPPRESSION (Suppression Skip)

Once suppression is implemented (08_SUPPRESSION), suppressed agents may have their
actions partially preempted (can't advance, can only fire at reduced accuracy).
The DM narrative skip mechanism from Phase 2 naturally handles this: the DM sees
the Suppressed condition in `previous_context` and can set `action_skipped=True`
for movement actions while allowing reduced-accuracy fire to proceed normally.

### No Dependency: 01_NPC_COMBAT, 02_ENEMY_LIFECYCLE, 03_TARGET_VALIDATION

These Wave 1 specs address orthogonal issues (NPC damage, defeat semantics, target
binding). They do not affect the skip mechanism and can be implemented independently.

---

## Migration & Backward Compatibility

### Schema Backward Compatibility

Both new fields (`action_skipped`, `skip_reason`) have defaults (`False` and `None`
respectively). Existing `ActionResolution` instances from before this change will
deserialize correctly with `action_skipped=False`.

### JSONL Backward Compatibility

The `action_skipped` field appears inside the `effects` dict, which is already a
flexible container. Existing JSONL analysis scripts that don't check for
`action_skipped` will include skipped actions in their analysis -- but since
skipped actions have empty effects (no damage, no conditions), they won't corrupt
aggregate statistics.

### Session Config Backward Compatibility

No session config changes. The skip system is entirely engine-internal.

---

## Open Questions

### Q1: Should `previous_context` Cap Increase Beyond 3 Resolutions?

Currently, only the last 3 resolutions are included in `previous_context`
(dm.py:5230). When skips add entries to `all_resolutions` without consuming
"meaningful resolution slots," the DM may miss important earlier context.

**Consideration:** Skipped actions are typically short narrations. Increasing the
cap to 5 would cost ~200-400 extra tokens per DM prompt but ensure better
context coverage in rounds with multiple skips.

**Recommendation:** Keep at 3 initially. Monitor prompt token usage in treatment
runs and increase if skip narrations displace important earlier context.

### Q2: Should Auto-Skip Check Active Conditions?

Currently, hard auto-skip checks `resolution_state.is_incapacitated()` which is
set by the stun KO path in combat resolution. Should it also scan the agent's
active conditions for incapacitating effects (e.g., Stunned with penalty <= -6)?

**Consideration:** This depends on 14_CONDITIONS being implemented first. Without
correct condition tracking, scanning conditions would produce false positives.

**Recommendation:** Phase 1 uses only `ResolutionState` checks (already reliable).
Add condition-based skip as a follow-up after 14_CONDITIONS is stable.

### Q3: Should Hard Auto-Skip Narration Be DM-Generated?

Currently, auto-skip uses `generate_invalidation_message()` which produces
mechanical, emoji-tagged text. Should we instead make an LLM call to generate
atmospheric narration for the skip?

**Consideration:** DM-generated narration is higher quality but costs one LLM call
per skip. In a 4-player session with 2 players stunned, that's 2 extra LLM calls
per round -- non-trivial for bulk generation.

**Recommendation:** Use templated narration for hard auto-skips (Phase 1). The
narration quality is acceptable for training data since the mechanical state
(defeated/incapacitated) is clear from structured fields. DM narrative skips
(Phase 2) already get DM-quality narration for free.

### Q4: Should Enemies Also Go Through DM Narrative Skip?

Currently, enemies use only `ActionValidator` (hard mechanical checks). Should
enemies also benefit from DM narrative skip for cases like "objective already
completed"?

**Consideration:** Enemy actions resolve through the legacy combat pipeline in
`mechanics.py`, not through DM structured output. Adding narrative skip to enemies
would require a DM LLM call for each enemy action -- fundamentally changing the
enemy resolution architecture.

**Recommendation:** No. Keep enemies on `ActionValidator` only. The narrative skip
mechanism is for DM-adjudicated actions (PCs and NPCs). If an enemy's objective is
narratively invalidated, the `ActionValidator` already handles the mechanical cases
(target defeated, etc.), and the remaining edge cases (objective completed by
another agent) are rare enough to not warrant an architectural change.
