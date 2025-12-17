# Conversion Phase Implementation Guide

## Status: PARTIAL IMPLEMENTATION

**Completed (2025-01-12):**
1. ✅ Enemy targeting communication enhanced (session.py:949-958, player.py:475-495, 1818-1865)
2. ✅ Unit tests for targeting communication (tests/unit/test_targeting_communication.py)
3. ✅ Unit tests for conversion validation (tests/unit/test_conversion_validation.py)
4. ✅ ConversionDecisions schema (schemas/story_events.py:740-837)
5. ✅ dm_conversion_check.yaml prompt (prompts/claude/en/dm/dm_conversion_check.yaml)

**Remaining Work:**

## Phase 1: Implement Conversion Check Method in DM

### File: `scripts/aeonisk/multiagent/dm.py`

**Add method:** `async def check_conversions(self, round_number: int, resolution_summary: str) -> ConversionDecisions`

**Implementation pattern:**
```python
async def check_conversions(self, round_number: int, resolution_summary: str) -> ConversionDecisions:
    """
    Separate conversion check phase - determine which enemies/NPCs should convert.

    Called AFTER all action resolutions, BEFORE synthesis.

    Args:
        round_number: Current round number
        resolution_summary: Summary of all action resolutions this round

    Returns:
        ConversionDecisions with enemy_conversions, escalations, npc_spawns
    """
    # 1. Build available enemies list
    available_enemies = []
    if self.shared_state and hasattr(self.shared_state, 'enemy_combat'):
        enemy_combat = self.shared_state.enemy_combat
        if enemy_combat and hasattr(enemy_combat, 'enemy_agents'):
            for enemy in enemy_combat.enemy_agents:
                if not enemy.is_defeated:
                    health_pct = int((enemy.health / enemy.max_health) * 100) if enemy.max_health > 0 else 0

                    # Flag low HP enemies as conversion candidates
                    is_candidate = health_pct < 30
                    marker = "🎯 CANDIDATE" if is_candidate else ""

                    available_enemies.append(
                        f"{enemy.agent_id} ({enemy.name}, {health_pct}% HP) {marker}".strip()
                    )

    # 2. Build available NPCs list
    available_npcs = []
    if self.shared_state and hasattr(self.shared_state, 'npc_agents'):
        for npc in self.shared_state.npc_agents:
            health_pct = int((npc.health / npc.max_health) * 100) if hasattr(npc, 'max_health') and npc.max_health > 0 else 100

            # Flag NPCs who took damage (escalation candidates)
            took_damage = health_pct < 100
            marker = "⚠️ TOOK DAMAGE" if took_damage else ""

            available_npcs.append(
                f"{npc.agent_id} ({npc.name}, {npc.disposition}, {health_pct}% HP) {marker}".strip()
            )

    # 3. Load conversion check prompt from YAML
    import yaml
    prompt_path = "scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_conversion_check.yaml"
    with open(prompt_path, 'r') as f:
        prompt_data = yaml.safe_load(f)

    # 4. Format prompt with context
    prompt = prompt_data['conversion_check_prompt'].format(
        available_enemies="\n".join(available_enemies) if available_enemies else "No active enemies",
        available_npcs="\n".join(available_npcs) if available_npcs else "No active NPCs",
        resolution_summary=resolution_summary
    )

    # 5. Call LLM with structured output (Pydantic AI)
    if not self.llm_provider:
        raise RuntimeError("DM llm_provider not initialized - cannot run conversion check")

    from .schemas.story_events import ConversionDecisions

    result = await self.llm_provider.run(
        prompt,
        response_model=ConversionDecisions
    )

    decisions = result.output  # Pydantic AI returns AgentRunResult with .output

    # 6. Log conversion check call for replay
    if self.llm_logger:
        self.llm_logger.log_llm_call(
            agent_id=self.agent_id,
            agent_type='dm',
            round=round_number,
            phase='conversion_check',
            prompt=prompt,
            response=decisions.model_dump_json(),
            model=self.llm_config.get('model', 'claude-sonnet-4-5'),
            source='dm_conversion_check'
        )

    return decisions
```

## Phase 2: Add Conversion Validation in Session

### File: `scripts/aeonisk/multiagent/session.py`

**Modify:** Existing conversion processing methods to add validation

**Location 1:** Enemy conversion processing (~line 3063-3145)

**Add validation before deescalation:**
```python
# Current code (around line 3128):
if conversion.resolution in [EnemyResolution.CONVINCED, EnemyResolution.NEUTRALIZED, EnemyResolution.SUBDUED]:
    # Find enemy in enemy_agents
    enemy = next((e for e in self.enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)

    # ✅ ADD VALIDATION HERE:
    if not enemy:
        logger.warning(f"Enemy {conversion.enemy_id} not found for conversion, skipping")
        print(f"\n⚠️  WARNING: Enemy {conversion.enemy_id} not found for conversion")
        continue  # Skip this conversion, process others

    # Existing deescalation code...
    npc = deescalate_enemy_to_npc(enemy, ...)
```

**Location 2:** Enemy removal processing

**Add similar validation for FLED/STORY_ADVANCED:**
```python
elif conversion.resolution in [EnemyResolution.FLED, EnemyResolution.STORY_ADVANCED]:
    # Find enemy to remove
    enemy = next((e for e in self.enemy_combat.enemy_agents if e.agent_id == conversion.enemy_id), None)

    # ✅ ADD VALIDATION HERE:
    if not enemy:
        logger.warning(f"Enemy {conversion.enemy_id} not found for removal, skipping")
        print(f"\n⚠️  WARNING: Enemy {conversion.enemy_id} not found for removal")
        continue  # Skip this removal, process others

    # Existing removal code...
    self.enemy_combat.enemy_agents.remove(enemy)
```

**Location 3:** NPC escalation processing (~line 3191-3210)

**Add validation for NPC existence:**
```python
for escalation in synthesis.escalations:
    # ✅ ADD VALIDATION HERE:
    npc = next((n for n in self.shared_state.npc_agents if n.agent_id == escalation.npc_id), None)

    if not npc:
        logger.warning(f"NPC {escalation.npc_id} not found for escalation, skipping")
        print(f"\n⚠️  WARNING: NPC {escalation.npc_id} not found for escalation")
        continue  # Skip this escalation, process others

    # Existing escalation code...
    await self.dm._process_escalation(escalation, round_number=self.current_round)
```

## Phase 3: Integrate Conversion Phase into Round Flow

### File: `scripts/aeonisk/multiagent/session.py`

**Current round flow (approximate):**
```
1. Declaration Phase → Players/Enemies/NPCs declare actions
2. Resolution Phase → DM resolves each action individually
3. Synthesis Phase → DM generates RoundSynthesis
4. Process Synthesis → Handle conversions/spawns/clocks
```

**New round flow:**
```
1. Declaration Phase → Players/Enemies/NPCs declare actions
2. Resolution Phase → DM resolves each action individually
3. **CONVERSION CHECK PHASE** → DM determines conversions (NEW)
4. Synthesis Phase → DM generates narrative (conversions already determined)
5. Process Synthesis → Handle conversions/spawns/clocks
```

**Implementation location:** Find the round loop method (likely in `MultiAgentSession` class)

**Add after resolution phase:**
```python
# After all resolutions complete
print(f"\n{'='*80}\n🔄 CONVERSION CHECK PHASE (Round {self.current_round})\n{'='*80}")

# Build resolution summary for DM
resolution_summary = self._build_resolution_summary()

# Call DM conversion check
conversion_decisions = await self.dm.check_conversions(
    round_number=self.current_round,
    resolution_summary=resolution_summary
)

print(f"✅ Conversion decisions: {len(conversion_decisions.enemy_conversions)} enemy conversions, "
      f"{len(conversion_decisions.escalations)} NPC escalations, "
      f"{len(conversion_decisions.npc_spawns)} NPC spawns")

# Store conversions for synthesis phase
self._pending_conversion_decisions = conversion_decisions
```

**Helper method to build resolution summary:**
```python
def _build_resolution_summary(self) -> str:
    """Build summary of resolutions for conversion check phase."""
    summary_lines = []

    # Iterate through stored resolutions this round
    for resolution in self._resolutions_this_round:
        agent_name = resolution.get('agent_name', 'Unknown')
        action = resolution.get('action', 'Unknown action')
        success = resolution.get('success', False)

        # Add damage dealt if any
        damage_text = ""
        if resolution.get('damage_dealt'):
            damage_text = f" (dealt {resolution['damage_dealt']} damage)"

        summary_lines.append(f"- {agent_name}: {action} ({'SUCCESS' if success else 'FAIL'}){damage_text}")

    return "\n".join(summary_lines) if summary_lines else "No resolutions this round"
```

**Modify synthesis to use pre-determined conversions:**
```python
# In synthesis phase, pass conversions to DM
synthesis = await self.dm.synthesize_round(
    round_number=self.current_round,
    predetermined_conversions=self._pending_conversion_decisions  # NEW parameter
)
```

**Update DM synthesis method signature:**
```python
async def synthesize_round(
    self,
    round_number: int,
    predetermined_conversions: Optional[ConversionDecisions] = None
) -> RoundSynthesis:
    """
    Generate round synthesis with narrative.

    If predetermined_conversions provided, integrate those conversions into narrative
    rather than determining conversions during synthesis.
    """
    # Build synthesis prompt with note that conversions already determined
    if predetermined_conversions:
        conversion_note = f"""
## Conversions Already Determined

The following conversions have already been decided and will be processed:

**Enemy Conversions:** {len(predetermined_conversions.enemy_conversions)}
**NPC Escalations:** {len(predetermined_conversions.escalations)}
**NPC Spawns:** {len(predetermined_conversions.npc_spawns)}

Your task is to synthesize a cohesive narrative that INTEGRATES these conversions.
Do NOT redetermine conversions - use the ones provided in your RoundSynthesis output.
"""
        # Add to prompt...
```

## Phase 4: Update dm_commands.yaml

### File: `scripts/aeonisk/multiagent/prompts/claude/en/dm/dm_commands.yaml`

**Remove lines 53-192** (conversion guidance - now in dm_conversion_check.yaml)

**Replace with brief note:**
```yaml
**Enemy/NPC Conversions:**

Conversions (enemy→NPC, NPC→enemy, NPC spawns) are determined in a SEPARATE conversion check phase.
Your synthesis task is to integrate these predetermined conversions into a cohesive narrative.

The conversions you receive in your synthesis call have already been validated and decided.
Simply include them in your RoundSynthesis output fields:
- `enemy_conversions`: List provided to you
- `escalations`: List provided to you
- `npc_spawns`: List provided to you
```

## Phase 5: Integration Tests

### File: `tests/integration/test_conversion_phase.py`

**Test scenarios:**
1. **Test conversion check phase runs after resolutions**
   - Setup: Session with 2 players, 2 enemies (1 low HP, 1 high HP)
   - Action: Resolve attacks, then run conversion check
   - Assert: DM suggests low HP enemy surrenders

2. **Test conversion validation catches missing enemies**
   - Setup: DM returns conversion for non-existent enemy_id
   - Assert: Warning logged, conversion skipped, other conversions processed

3. **Test full round flow with conversions**
   - Setup: Full round with enemy surrender
   - Assert: Conversion check → Synthesis → Enemy converted to NPC

4. **Test NPC escalation validation**
   - Setup: DM returns escalation for non-existent npc_id
   - Assert: Warning logged, escalation skipped

## Phase 6: Testing Plan

### Unit Tests
```bash
# Test targeting communication
python -m pytest tests/unit/test_targeting_communication.py -v

# Test conversion validation
python -m pytest tests/unit/test_conversion_validation.py -v
```

### Integration Tests (after implementation)
```bash
# Test conversion phase integration
python -m pytest tests/integration/test_conversion_phase.py -v
```

### Manual Session Test
```bash
# Run combat session to verify targeting + conversions
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_combat.json
```

**Expected behavior:**
1. Enemy declarations show: "Thug attacks targeting tgt_player_ash with knife"
2. After resolutions, conversion check phase runs
3. Low HP enemies surrender (if applicable)
4. Synthesis narrative integrates conversions
5. No "Enemy not found" warnings (validation working)

## Known Challenges

1. **DM LLM client architecture:** Need to verify Pydantic AI integration pattern matches existing usage
2. **Round flow complexity:** Session round loop may have async dependencies
3. **Resolution storage:** Need to track resolutions for summary building
4. **Prompt token budget:** Conversion check + synthesis = 2 LLM calls per round (increased cost)

## Rollback Plan

If conversion phase separation causes issues:

1. Revert session.py changes (remove conversion check phase from round flow)
2. Keep targeting communication enhancements (valuable regardless)
3. Keep validation additions (prevent "not found" errors)
4. Conversion prompts can remain in dm_commands.yaml (integrated approach)

## Next Steps for Human Developer

1. Implement `check_conversions()` method in dm.py (follow pattern above)
2. Add conversion validation to session.py (3 locations marked)
3. Integrate conversion phase into round flow (session.py)
4. Update dm_commands.yaml (remove detailed conversion guidance)
5. Write integration tests (test_conversion_phase.py)
6. Run manual session test to verify behavior
7. Tune conversion check prompt based on DM quality

## References

- **Targeting enhancement:** session.py:949-958, player.py:475-495, 1818-1865
- **ConversionDecisions schema:** schemas/story_events.py:740-837
- **Conversion check prompt:** prompts/claude/en/dm/dm_conversion_check.yaml
- **Test specs:** tests/unit/test_targeting_communication.py, test_conversion_validation.py
