# Dataset Release: Aeonisk-52

**Working Title:** "Aeonisk-52: A Multi-Agent TTRPG Dataset with Graduated Outcomes for AI Research"

**Status:** Data exists, needs curation + documentation
**Priority:** HIGH (foundational for other papers)
**Estimated Timeline:** 2-3 weeks to public release

---

## Dataset Overview

**Aeonisk-52** is a multi-agent gameplay dataset featuring:
- **500+ sessions** of autonomous LLM agents playing tabletop RPG scenarios
- **10+ event types** (action declarations, resolutions, round syntheses, etc.)
- **Graduated outcomes** (6-tier outcome system for every action)
- **Counterfactual data** (outcome_tiers showing all possible outcomes per action)
- **Multi-provider** (Claude, GPT-4 agent interactions)
- **Structured JSONL** (Pydantic-validated schemas)
- **Deterministic replay** (random seeds, LLM call caching)

**Total size:** ~500 sessions × 500KB avg = 250MB compressed

**Use cases:**
- AI calibration research (player estimates vs DM decisions)
- Multi-agent coordination studies
- Ethical reasoning benchmarks
- Fine-tuning training data
- Game balancing analysis
- Narrative generation pipelines

## Dataset Structure

```
aeonisk-52/
├── README.md                    # Datasheet (Gebru et al. format)
├── LICENSE.txt                  # MIT (code) + CC-BY-4.0 (data)
├── sessions/
│   ├── session_001.jsonl        # Full session logs
│   ├── session_002.jsonl
│   ├── ...
│   └── session_500.jsonl
├── metadata/
│   ├── session_index.csv        # Session metadata (date, agents, rounds, outcome)
│   ├── character_index.csv      # Character stats across sessions
│   ├── scenario_index.csv       # Scenario types and themes
│   └── llm_usage.csv            # Token counts, costs, models
├── schemas/
│   ├── event_schemas.json       # JSON Schema definitions
│   └── validation.py            # Schema validation script
├── fixtures/
│   ├── example_combat.jsonl     # 3-round combat scenario (minimal example)
│   ├── example_social.jsonl     # 2-round negotiation
│   ├── example_ritual.jsonl     # 1-round ritual
│   └── example_mixed.jsonl      # 5-round mixed scenario
├── tools/
│   ├── analyze_session.py       # Session analysis CLI
│   ├── extract_fixture.py       # Extract round ranges
│   ├── replay_fixture.py        # Deterministic replay
│   ├── validate_logging.py      # Schema validation
│   └── reconstruct_narrative.py # JSONL → text narrative
└── research/
    ├── calibration_analysis.py  # Extract player estimates vs DM DCs
    ├── coordination_metrics.py  # Measure multi-agent coordination
    ├── ethical_metrics.py       # Void usage, de-escalation rates
    └── narrative_quality.py     # Coherence scoring
```

## Datasheet (Gebru et al. Format)

### Motivation

**Why was the dataset created?**
- Enable research in multi-agent LLM coordination, calibration, and ethical reasoning
- Provide training data for fine-tuning TTRPG-domain models
- Support game balancing and narrative generation research

**Who created the dataset?**
- Solo researcher (SRE background, 5 years multi-agent systems experience)
- Hobby project (2024-2025)

**Who funded the dataset?**
- Self-funded (LLM API costs ~$500)

### Composition

**What do the instances represent?**
- Each session is a complete multi-agent TTRPG gameplay scenario
- Events represent agent actions, resolutions, and world state changes

**How many instances are there?**
- 500 sessions
- ~30,000 action declarations
- ~30,000 action resolutions
- ~5,000 round syntheses

**What data does each instance consist of?**
```jsonl
{"event_type": "action_resolution", "round": 2, "agent": "Veyra Lune", "action": "Prepare ritual altar", "roll": {"dc": 18, "total": 16, "margin": -2, "success": false, "tier": "failure"}, "narration": "The crystals resist...", "effects": {"void_changes": [{"agent": "Veyra Lune", "change": 1}]}, "outcome_tiers": {...}}
```

**Is there a label/target?**
- Not a supervised learning dataset
- Graduated outcomes (tier) can be used as labels
- Player difficulty estimates (calibration research)
- Coordination patterns (multi-agent research)

**Is any information missing?**
- Some early sessions lack `outcome_tiers` (schema evolved)
- LLM call prompts/responses NOT included (privacy/size)
- Image/audio artifacts NOT included (generated separately)

**Are relationships between instances made explicit?**
- Yes: `round` numbers link events chronologically
- Yes: `agent_id` links actions to characters
- Yes: `parent_event_id` links resolutions to declarations

### Collection

**How was the data collected?**
- Autonomous LLM agents (Claude, GPT-4) playing TTRPG scenarios
- Logged via custom JSONL pipeline during gameplay
- No human intervention during sessions

**Who was involved?**
- AI agents only (DM, players, enemies, NPCs)
- No human participants

**Over what timeframe?**
- 2024-2025 (18 months)

**Were ethical review processes conducted?**
- N/A (no human subjects)

### Preprocessing

**Was any preprocessing/cleaning done?**
- Schema validation (removed malformed events)
- Anonymization (character names are fictional)
- Deterministic replay validation (ensure LLM cache correctness)

**Was raw data saved?**
- Yes: JSONL logs are raw (no filtering)
- LLM prompts/responses NOT saved (too large)

### Uses

**What are the intended use cases?**
1. **AI calibration research** - Analyze player estimates vs DM decisions
2. **Multi-agent coordination** - Study emergent teamwork patterns
3. **Ethical reasoning** - Measure void usage, de-escalation, resource sharing
4. **Fine-tuning** - Train domain-specific LLMs
5. **Game balancing** - Optimize mechanics via self-play
6. **Narrative generation** - Train story generation models

**What should NOT be done with the data?**
- Do NOT use for real-world tactical/military applications (fictional setting)
- Do NOT assume AI behavior generalizes to humans
- Do NOT use for surveillance or manipulation research

**Are there tasks the dataset should NOT be used for?**
- Real-world decision-making (this is fiction)
- Medical/legal applications (out of domain)

### Distribution

**How is the dataset distributed?**
- HuggingFace Datasets: `3RAIN/aeonisk-52`
- GitHub: `ThreeRiversAINexus/aeonisk-yags` (MIT license)
- Zenodo: DOI for citation stability

**When will the dataset be released?**
- Target: Q2 2025 (after initial papers submitted)

**What licenses apply?**
- Code: MIT License (permissive)
- Data: CC-BY-4.0 (attribution required)
- World lore: CC-BY-4.0 (attribution required)

**Are there fees?**
- No (free, open access)

**Are there export controls or regulations?**
- No (fictional content, no dual-use concerns)

### Maintenance

**Who maintains the dataset?**
- Primary: Solo researcher
- Community contributions accepted (GitHub PRs)

**How can users get support?**
- GitHub issues: `ThreeRiversAINexus/aeonisk-yags/issues`
- Email: (provide contact)

**Will the dataset be updated?**
- Yes: New sessions added periodically
- Versioning: `aeonisk-52-v1.0`, `aeonisk-52-v1.1`, etc.

**Is there a process for retiring the dataset?**
- Dataset will remain available indefinitely (archival via Zenodo)

## Session Metadata

**session_index.csv columns:**
```
session_id, date, duration_rounds, scenario_type, scenario_theme, void_level,
num_players, num_enemies, dm_model, player_models, outcome,
total_actions, avg_void_final, soulcredit_spent, cost_usd
```

**Example:**
```csv
session_id,date,duration_rounds,scenario_type,scenario_theme,void_level,num_players,num_enemies,dm_model,player_models,outcome,total_actions,avg_void_final,soulcredit_spent,cost_usd
7f5b70bc,2024-11-15,8,ritual,void_purification,8,1,0,claude-sonnet-4-5,claude-sonnet-4-5,success,24,3.0,45,1.89
```

## Event Schema Documentation

### Core Event Types

**1. scenario**
- Session setup (theme, location, void_level)
- Occurs once per session (event 1)

**2. action_declaration**
- Player/enemy announces intent
- Includes difficulty_estimate (for calibration research)
- Occurs before resolution

**3. action_resolution**
- DM resolves action with graduated outcome
- Includes: dc, roll, tier, narration, effects, outcome_tiers
- **Counterfactual data:** outcome_tiers shows all 6 possible outcomes

**4. round_synthesis**
- DM summarizes round, processes entity conversions
- Includes: summary, deescalations, escalations, npc_spawns

**5. round_summary**
- Mechanical state update (character HP, void, clocks)
- Occurs at end of each round

**6. character_state**
- Full character state snapshot
- Includes: health, void_score, wounds, skills

**7. combat_action**
- Deprecated (replaced by action_resolution)
- Legacy data only

**8. enemy_spawn / enemy_defeat**
- Entity lifecycle events
- Links to agent_id (stable across conversions)

**9. mission_debrief**
- Final session summary
- Includes: outcome, lessons_learned, soulcredit_earned

**10. llm_call**
- LLM API metadata (tokens, cost, model)
- NO prompts/responses (size/privacy)

## Research-Specific Extracts

### Calibration Dataset

**Extract player estimates vs DM DCs:**

```python
import json
import pandas as pd

calibration_data = []

for session_file in sessions:
    with open(session_file) as f:
        for line in f:
            event = json.loads(line)

            if event['event_type'] == 'action_resolution':
                action = event.get('action', {})
                roll = event.get('roll', {})

                if 'difficulty_estimate' in action and 'dc' in roll:
                    calibration_data.append({
                        'session': event['session'],
                        'round': event['round'],
                        'agent': event['agent'],
                        'action_type': action.get('action_type'),
                        'skill': action.get('skill'),
                        'skill_value': action.get('skill_value'),
                        'player_estimate': action['difficulty_estimate'],
                        'dm_dc': roll['dc'],
                        'error': roll['dc'] - action['difficulty_estimate'],
                        'success': roll['success']
                    })

df = pd.DataFrame(calibration_data)
df.to_csv('calibration_dataset.csv', index=False)
```

**Output:** ~10,000 rows of player estimates vs actual DCs

### Coordination Dataset

**Extract multi-agent coordination patterns:**

```python
coordination_data = []

for session_file in sessions:
    declarations = []

    with open(session_file) as f:
        for line in f:
            event = json.loads(line)

            if event['event_type'] == 'action_declaration':
                declarations.append(event)

            if event['event_type'] == 'round_synthesis':
                # Check if declarations mention each other
                for i, decl in enumerate(declarations):
                    for j, other in enumerate(declarations):
                        if i != j and mentions(decl['action'], other['agent']):
                            coordination_data.append({
                                'session': event['session'],
                                'round': event['round'],
                                'agent': decl['agent'],
                                'coordinated_with': other['agent'],
                                'pattern': classify_pattern(decl, other)
                            })

                declarations = []  # Reset for next round

df = pd.DataFrame(coordination_data)
df.to_csv('coordination_dataset.csv', index=False)
```

### Ethical Reasoning Dataset

**Extract void usage, de-escalation, resource sharing:**

```python
ethical_data = []

for session_file in sessions:
    with open(session_file) as f:
        for line in f:
            event = json.loads(line)

            # Void power usage
            if event['event_type'] == 'action_resolution':
                effects = event.get('effects', {})
                void_changes = effects.get('void_changes', [])

                if void_changes:
                    ethical_data.append({
                        'session': event['session'],
                        'round': event['round'],
                        'agent': event['agent'],
                        'ethical_dimension': 'void_usage',
                        'void_before': event.get('character_void'),
                        'void_change': void_changes[0]['change'],
                        'justification': event.get('action', {}).get('description')
                    })

            # De-escalation
            if event['event_type'] == 'round_synthesis':
                for deesc in event.get('deescalations', []):
                    ethical_data.append({
                        'session': event['session'],
                        'round': event['round'],
                        'agent': deesc['agent_id'],
                        'ethical_dimension': 'deescalation',
                        'mechanism': deesc['mechanism'],
                        'disposition': deesc['disposition']
                    })

df = pd.DataFrame(ethical_data)
df.to_csv('ethical_dataset.csv', index=False)
```

## Quality Assurance

### Validation Checks

**1. Schema Compliance**
```bash
python tools/validate_logging.py sessions/*.jsonl
# Expected: 100% pass rate
```

**2. Completeness**
```python
for session in sessions:
    assert has_event_type(session, 'scenario')
    assert has_event_type(session, 'round_summary')
    assert has_event_type(session, 'mission_debrief')
```

**3. Temporal Consistency**
```python
for session in sessions:
    events = load_events(session)
    rounds = [e['round'] for e in events if 'round' in e]
    assert rounds == sorted(rounds)  # Chronological order
```

**4. Character Consistency**
```python
for session in sessions:
    characters = extract_characters(session)
    for char in characters:
        assert char.agent_id is unique
        assert char.name is consistent across events
```

### Known Issues

**Issue 1:** Early sessions (001-050) lack `outcome_tiers`
- **Impact:** Can't use for counterfactual analysis
- **Workaround:** Filter by date >= 2024-10-01

**Issue 2:** Some enemy LLM calls missing
- **Impact:** Can't replay certain combat rounds
- **Workaround:** Use `--cache-player-actions` only

**Issue 3:** Narration length varies wildly (50-500 words)
- **Impact:** Not ideal for fixed-length models
- **Workaround:** Truncate or summarize

## Citation

**BibTeX:**
```bibtex
@dataset{aeonisk52_2025,
  title={Aeonisk-52: A Multi-Agent TTRPG Dataset with Graduated Outcomes},
  author={[Your Name]},
  year={2025},
  publisher={HuggingFace},
  howpublished={\url{https://huggingface.co/datasets/3RAIN/aeonisk-52}},
  doi={10.5281/zenodo.XXXXXXX}
}
```

**ACM Reference Format:**
```
[Your Name]. 2025. Aeonisk-52: A Multi-Agent TTRPG Dataset with Graduated Outcomes.
HuggingFace Datasets. https://doi.org/10.5281/zenodo.XXXXXXX
```

## Release Checklist

**Pre-release (2 weeks):**
- [ ] Curate 52 best sessions (hence "Aeonisk-52")
- [ ] Validate all schemas (100% pass)
- [ ] Generate metadata CSVs
- [ ] Write comprehensive README
- [ ] Create example notebooks (Jupyter)
- [ ] Test tools on fresh Python environment

**Release (1 day):**
- [ ] Upload to HuggingFace Datasets
- [ ] Tag GitHub release (v1.0)
- [ ] Upload to Zenodo (get DOI)
- [ ] Post announcement (r/MachineLearning, Twitter, LessWrong)

**Post-release (ongoing):**
- [ ] Monitor GitHub issues
- [ ] Update documentation based on feedback
- [ ] Add new sessions periodically (v1.1, v1.2, etc.)

## Target Announcement Venues

**1. HuggingFace Datasets**
- Main distribution platform
- Searchable, citable, versioned

**2. r/MachineLearning**
- Reddit ML community
- "[D] New Dataset: Aeonisk-52 - Multi-Agent TTRPG with Graduated Outcomes"

**3. Twitter/X**
- AI research community
- Thread explaining unique features

**4. LessWrong**
- AI safety community (ethical reasoning angle)
- Post: "Multi-Agent Calibration Dataset"

**5. Papers With Code**
- Link dataset to benchmark papers
- Track leaderboards

**6. ArXiv**
- Dataset paper (2-4 pages)
- Cite in all subsequent papers

---

**Key Takeaway:** Dataset release establishes Aeonisk as a research platform. First-mover advantage in multi-agent TTRPG domain.

**Practical impact:** Enables researchers worldwide to use your data (citations, collaborations).

**Research impact:** Canonical dataset for multi-agent coordination + graduated outcomes research.
