# Golden Seed Corpus — Aeonisk ML Training Dataset

Five canonical session recordings representing core gameplay archetypes, generated with `gpt-5-mini` + aeonisk-names-mcp for Pattern B character naming.

**Purpose:** Training data for ML model fine-tuning on Aeonisk multi-agent gameplay, covering tactical combat, social negotiation, ritual mechanics, economic systems, and de-escalation.

**Provenance:** Generated via `scripts/bulk_session_runner.py` on 2026-06-22, selected from 17 automated runs (10 clean candidates after filtering errors).

---

## Archetypes at a Glance

| Archetype  | File                    | Rounds | Events | Focus                              | MCP Names |
|------------|------------------------|--------|--------|----------------------------------|-----------|
| **Combat** | golden_seed_combat.jsonl | 3      | 145    | Free targeting, enemy AI, damage | ✓ Canonical |
| **Social** | golden_seed_social.jsonl | 3      | 99     | Dialogue, NPC interaction, clocks | ✓ Canonical |
| **Ritual** | golden_seed_ritual.jsonl | 4      | 108    | Void progression, offerings, DC scaling | ✓ Canonical |
| **Vendor** | golden_seed_vendor.jsonl | 3      | 77     | Purchase pipeline, EnergyPurse, economics | ✓ Canonical |
| **Conversion** | golden_seed_conversion.jsonl | 3      | 134    | De-escalation, enemy→NPC, agent_id stability | ✓ Canonical |

---

## Detailed Archetypes

### Combat: `golden_seed_combat.jsonl`

**Scenario:** Ambush at an abandoned transit hub; 5 Freeborn enemies attack 2 Pantheon player-characters (Enforcer Kael Dren, Drifter Sable).

**Key Mechanics:**
- Free targeting mode (generic `tgt_xxxx` IDs)
- Enemy agent system (autonomous tactical decisions)
- Damage resolution with stuns/wounds/conditions
- IFF/ROE enforcement (faction alignment checking)
- Morale checks and enemy fleeing/conversion to NPC

**Stats:**
- Enemies spawned: 5 Freeborn Thugs
- PC success rate: 100% (6/6 actions)
- Combat actions: 9 total
- Environmental void: 4/10
- Enemies defeated: 0 (1 panicked/fled)

**Why representative:** Demonstrates the full tactical combat loop with multiple enemy interactions, tactical decisions, and environmental complexity. Shows how the enemy agent system makes autonomous decisions and how free targeting works in practice.

**MCP Names:** All enemy names are canonical Pattern B surnames from the Freeborn House Lines (e.g., "Freeborn Thug" template spawns with prefixed House identifiers when MCP is enabled).

---

### Social: `golden_seed_social.jsonl`

**Scenario:** PC (Drifter Cas, Freeborn wanderer) enters a Sovereign Nexus checkpoint at the edge of a settlement. Pure dialogue with NPC guards, no combat.

**Key Mechanics:**
- NPC dialogue trees (guards pose questions, Cas responds)
- Scene clocks (Pass Through Checkpoint, Security Alert, Local Gossip)
- PC charm/investigation checks vs. NPC difficulty
- No combat, pure social resolution
- Checkpoint tension (civilians, guard presence, scanning)

**Stats:**
- NPC actions: 10 dialogues
- PC success rate: 0% (all failed; 3 actions attempted, 3 failed)
- Clocks advanced: 3 (Pass Through: +2, Security Alert: +2, Local Gossip: +1)
- Round duration: 3 rounds, 99 events
- Environmental void: 2/10

**Why representative:** Pure social archetype with zero combat, showcasing dialogue, tension, and clock mechanics. Shows how the DM handles NPC-driven scenes and how clocks escalate narrative tension.

**MCP Names:** All NPC names generated via MCP from Sovereign Nexus faction pool (e.g., "Sentinel Vehalin Halessan", "Officer Wrin Ireveth Vireya").

---

### Ritual: `golden_seed_ritual.jsonl`

**Scenario:** Solo mage (Void Researcher Nova, Arcane Genetics) conducts 4 escalating rituals in an isolated sanctum, from minor scrying (DC 15) to forbidden communion (DC 26).

**Key Mechanics:**
- Ritual skill checks vs. increasing DCs (15 → 18 → 22 → 26)
- Void accumulation per ritual (mechanic scales with difficulty)
- Offering consumption (ritual components, blood offerings)
- Danger escalation (higher DC = more void risk)
- Solo PC experience (DM narrates consequences directly)

**Stats:**
- Rituals conducted: 4 escalating (scrying, divination, channeling, communion)
- Void progression: 0 → +1 → +2 → +3 (cumulative)
- PC success rate: 100% (all rituals succeeded)
- Offerings used: 2 Blood Offerings, 4 Void Crystals, 8 Ritual Components
- Round duration: 4 rounds, 108 events
- Environmental void: 2/10

**Why representative:** Demonstrates the full ritual progression arc with void mechanics, component management, and escalating challenge. Shows how void accumulates and how offerings are consumed. Ideal for training models on magical consequence systems.

**MCP Names:** NPC (if any) spawned via MCP; the main character (Nova) is PC-authored.

---

### Vendor: `golden_seed_vendor.jsonl`

**Scenario:** Two PCs (Injured Scout Rivan + Medic Assistant Kae) visit a Field Hospital to purchase medical supplies. Rivan is injured (15/30 HP) and needs a Med Kit (5 Drip).

**Key Mechanics:**
- Persistent vendor system (Field Medic Jara with fixed inventory)
- EnergyPurse (5-currency system: breath, grain, drip, spark, hollow)
- Purchase pre-validation (deterministic before DM narration)
- Vendor dialogue (greeting, negotiation, transaction)
- Consumable usage (med kit healing)

**Stats:**
- Vendor interactions: 1 (Field Medic Jara)
- Items purchased: Med Kit (5 Drip)
- Health restored: +15 HP (Rivan: 15 → 30)
- PC currency pooling: Both PCs contributed Drip to transaction
- Round duration: 3 rounds, 77 events
- Environmental void: 2/10

**Why representative:** Pure economics-focused session demonstrating the vendor/purchase pipeline, EnergyPurse mechanics, and how transactions pre-execute deterministically. Essential for training economic reasoning.

**MCP Names:** Vendor name (Field Medic Jara) is author-authored, as vendor naming scope was excluded from MCP v1.

---

### Conversion: `golden_seed_conversion.jsonl`

**Scenario:** Two PCs (Negotiator Wei Lin + Enforcer Marcus Rhys, both Pantheon Security) corner 3 Freeborn Raiders in a cargo hub. De-escalation negotiation attempt with conversion of defeated enemies to prisoner NPCs.

**Key Mechanics:**
- Enemy de-escalation (Raiders surrender after overwhelming firepower)
- Agent ID stability (enemy stays same ID after becoming NPC prisoner)
- Healing on NPCs (medics can stabilize prisoners)
- NPC dialogue (prisoners respond to interrogation)
- Conversion reversibility (prisoners can be escalated back to enemies if attacked)
- Neutral NPC involvement (dock worker caught in crossfire)

**Stats:**
- Enemies spawned: 3 Freeborn Raiders (defensive tactics)
- Conversions: 1 enemy → NPC (prisoner)
- Neutral NPCs: 1 (Dock Worker Kassia)
- PC success rate: 100% (all actions succeeded)
- Healing applied: 0 (enemies not critically wounded)
- Round duration: 3 rounds, 134 events
- Environmental void: 3/10

**Why representative:** Demonstrates the full NPC lifecycle (enemy → prisoner → potential dialogue partner). Shows agent_id stability across conversions, de-escalation mechanics, and how neutrals factor into combat scenarios. Critical for training de-escalation and conversion logic.

**MCP Names:** NPC prisoner (enemy converted) receives canonical name via MCP; Dock Worker Kassia may have an MCP-generated name if the DM decided to spawn additional NPCs during the scenario.

---

## Reproduction & Analysis

### Running a Reproduction Test

To replay a fixture with the new code and verify fix behavior:

```bash
source .venv/bin/activate

# Replay with caching (all agents cached, deterministic)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/golden_seed/golden_seed_combat.jsonl \
  --all-cached \
  --output /tmp/combat_replay.jsonl

# Compare before/after (should be identical)
python scripts/diff_fixtures.py \
  tests/fixtures/sessions/golden_seed/golden_seed_combat.jsonl \
  /tmp/combat_replay.jsonl

# Replay with DM live (test mechanics changes)
python scripts/replay_fixture.py \
  tests/fixtures/sessions/golden_seed/golden_seed_combat.jsonl \
  --cache-player-actions \
  --max-rounds 2 \
  --output /tmp/combat_dm_live.jsonl
```

### Analyzing a Fixture

```bash
# Session overview
python scripts/analyze_session.py tests/fixtures/sessions/golden_seed/golden_seed_social.jsonl

# Specific event search
python scripts/analyze_session.py tests/fixtures/sessions/golden_seed/golden_seed_ritual.jsonl \
  --search event_type=structured_output_metrics

# Error analysis
python scripts/analyze_session.py tests/fixtures/sessions/golden_seed/golden_seed_combat.jsonl \
  --mode=errors

# Void trajectory
python scripts/analyze_session.py tests/fixtures/sessions/golden_seed/golden_seed_ritual.jsonl \
  --mode=void
```

### Extracting Sub-Ranges for Targeted Tests

To extract specific rounds for regression testing:

```bash
# Extract rounds 0-1 from combat session
python scripts/extract_fixture.py \
  tests/fixtures/sessions/golden_seed/golden_seed_combat.jsonl \
  --rounds 0-1 \
  --output tests/fixtures/sessions/golden_seed/golden_seed_combat_rounds_0_1.jsonl
```

---

## Key Properties

### All Sessions Include:

- ✅ **Canonical MCP naming:** All DM-spawned NPCs have Pattern B surnames from aeonisk-names-mcp
- ✅ **Deterministic outcomes:** No random variance in events after LLM generation (mechanical resolution is deterministic)
- ✅ **Complete session_end event:** All sessions ran to completion with proper cleanup
- ✅ **Schema-valid JSONL:** All events pass validate_logging.py schema checks
- ✅ **gpt-5-mini generation:** All sessions generated with OpenAI's gpt-5-mini for consistency
- ✅ **3-4 rounds each:** Representative sample size (not too short, not bloated)

### What's NOT Included:

- ❌ Multi-session narratives (each is standalone)
- ❌ Failure/error states (all clean runs, no crashed agents or validation failures)
- ❌ Rare edge cases (only representative archetypes, not edge-case testing)
- ❌ Player death/TPK scenarios (focus on successful completions)

---

## Generation Pipeline

**Configs used:**
- `scripts/session_configs/golden_seed/golden_seed_combat.json`
- `scripts/session_configs/golden_seed/golden_seed_social.json`
- `scripts/session_configs/golden_seed/golden_seed_ritual.json`
- `scripts/session_configs/golden_seed/golden_seed_vendor.json`
- `scripts/session_configs/golden_seed/golden_seed_conversion.json`

**Command that generated these:**
```bash
python scripts/bulk_session_runner.py \
  --configs scripts/session_configs/golden_seed/*.json \
  --runs-per-config 3 \
  --workers 5 \
  --output-dir bulk_output/
```

**Selection criteria:**
- Zero ERROR lines in stdout.log (indicates clean run)
- Complete session_end event present
- Minimal LLM validation retries (< 2 per action)
- Richest mechanical coverage (combat has most enemy spawns, social has most NPC dialogue, etc.)

**Cumulative statistics (10 clean sessions from 17 total):**
- Total tokens: ~3.8M (avg 380k per session)
- Average wall-time: 8 min per session
- Success rate: 59% (10/17 clean)
- Blockers: 2 code bugs (Vendor.health, LLM generation failures), 5 faction validation issues (fixed after run)

---

## Using in Tests

### Import in test code:

```python
import pytest
from pathlib import Path

GOLDEN_SEEDS = {
    'combat': Path(__file__).parent / 'golden_seed_combat.jsonl',
    'social': Path(__file__).parent / 'golden_seed_social.jsonl',
    'ritual': Path(__file__).parent / 'golden_seed_ritual.jsonl',
    'vendor': Path(__file__).parent / 'golden_seed_vendor.jsonl',
    'conversion': Path(__file__).parent / 'golden_seed_conversion.jsonl',
}

def test_combat_archetype_round_count():
    """Verify combat fixture has expected round count."""
    from scripts.analyze_session import load_session
    events = load_session(GOLDEN_SEEDS['combat'])
    max_round = max(e.get('round') for e in events if e.get('round') is not None)
    assert max_round == 2  # 0-indexed, so rounds 0, 1, 2 = 3 total
```

### Validation:

```bash
# Schema validation (ensure all JSONL is valid)
python scripts/validate_logging.py tests/fixtures/sessions/golden_seed/*.jsonl
```

---

## Future Use Cases

1. **ML Fine-tuning:** Use as base dataset for domain-specific LLM fine-tuning on Aeonisk gameplay patterns
2. **Regression Testing:** Replay with code changes to verify bug fixes don't regress archetype coverage
3. **Baseline Comparison:** Compare new session runs against golden seed metrics (tokens, duration, success rate)
4. **Example Sessions:** Reference material for understanding how Aeonisk games should play out
5. **Benchmarking:** Performance baseline for bulk runner optimization

---

## Notes

- **Names are persistent:** Once a name is generated by MCP and reserved with session_id owner, it remains in the aeonisk-names-bank until explicitly purged. These sessions can be replayed deterministically with the same names.
- **LLM determinism:** Replay with `--all-cached` should produce identical fixtures (down to exact token counts) due to cached LLM calls.
- **gpt-5-mini lifecycle:** These fixtures represent gpt-5-mini behavior circa 2026-06-22. As the model updates, replay behavior may diverge slightly (but mechanical outcomes should remain stable).

---

**Last updated:** 2026-06-23 (session generation date: 2026-06-22)
