# Quick Start: Multi-Agent System

This guide shows how to run multi-agent RPG sessions and work with the mechanics system.

## Prerequisites

**CRITICAL:** Always activate the virtual environment first:

```bash
cd scripts/aeonisk
source .venv/bin/activate
```

ChromaDB and sentence-transformers are required and installed in the venv.

## Running a Session

```bash
# From scripts/aeonisk directory (with venv activated)
python3 ../run_multiagent_session.py ../session_config_combat.json
```

The mechanics are automatically initialized via `shared_state`.

## For DM Development

### 1. Create Scenario-Specific Clocks

When generating a scenario, create 2-4 clocks that track key dramatic questions:

```python
# In dm.py, _generate_ai_scenario() method

mechanics = self.shared_state.get_mechanics_engine()

# Example: Bond Crisis scenario
mechanics.create_scene_clock(
    name="Sanctuary Corruption",
    maximum=6,
    description="Void contamination spreading through sacred space"
)

mechanics.create_scene_clock(
    name="Saboteur Exposure",
    maximum=6,
    description="Progress toward identifying the inside collaborator"
)

mechanics.create_scene_clock(
    name="Communal Stability",
    maximum=6,
    description="Social cohesion of the commune"
)
```

**Clock Types to Consider:**
- **Threat Clocks**: Danger intensifying (corruption, countdown, collapse)
- **Progress Clocks**: Investigation or goal advancement
- **Resource Clocks**: Time, trust, or stability depleting

### 2. Resolve Actions with Dice

When handling player actions:

```python
# In dm.py, _handle_action_declared() method

mechanics = self.shared_state.get_mechanics_engine()

# Get action details from player message
action = message.payload

# Resolve mechanically
resolution = mechanics.resolve_action(
    intent=action['intent'],
    attribute=action['attribute'],
    skill=action.get('skill'),
    attribute_value=action['attribute_value'],
    skill_value=action.get('skill_value', 0),
    difficulty=action['difficulty']
)

# Format for narration
narration = mechanics.format_resolution_for_narration(resolution)
print(narration)

# Update clocks based on outcome
if resolution.outcome_tier in [OutcomeTier.FAILURE, OutcomeTier.CRITICAL_FAILURE]:
    if 'ritual' in resolution.intent.lower():
        mechanics.advance_clock("Sanctuary Corruption", 1, f"Failed {resolution.intent}")

if resolution.success and resolution.margin >= 10:
    if 'investigate' in resolution.intent.lower():
        mechanics.advance_clock("Saboteur Exposure", 2, "Excellent investigation")

# Check for filled clocks (triggers)
for clock_name, clock in mechanics.scene_clocks.items():
    if clock.filled:
        # Trigger scenario beat based on which clock filled
        if clock_name == "Saboteur Exposure":
            print("TRIGGER: The collaborator is exposed and makes a desperate move!")
        elif clock_name == "Sanctuary Corruption":
            print("TRIGGER: A void entity manifests in the corrupted field!")
```

### 3. Enforce Ritual Requirements

For ritual actions:

```python
resolution, ritual_effects = mechanics.resolve_ritual(
    intent=action['intent'],
    willpower=action['willpower'],
    astral_arts=action['astral_arts'],
    difficulty=action['difficulty'],
    has_primary_tool=action.get('has_primary_tool', False),
    has_offering=action.get('has_offering', False),
    sanctified_altar=action.get('at_altar', False),
    agent_id=action['agent_id']
)

# ritual_effects includes:
# - void_change: How much void to add/remove
# - consequences: List of strings describing what happened
# - soulcredit_change: Economic effects

print(f"Void change: +{ritual_effects['void_change']}")
print(f"Consequences: {', '.join(ritual_effects['consequences'])}")
```

### 4. Use Knowledge Retrieval

Look up rules during play:

```python
kr = self.shared_state.get_knowledge_retrieval()

# Get specific rules
ritual_rules = kr.get_ritual_rules()
void_rules = kr.get_void_rules()
difficulty_guide = kr.get_difficulty_guidelines()

# General query
results = kr.query("How do bonds work mechanically?", n_results=2)
for result in results:
    print(result['content'])
```

## For Player Development

### 1. Use Enhanced Prompts

```python
from aeonisk.multiagent.enhanced_prompts import get_player_system_prompt

# Get recent intents for de-duplication
validator = self.shared_state.get_action_validator()
recent = validator.deduplicator.get_recent_intents(self.agent_id)

# Build system prompt
system_prompt = get_player_system_prompt(
    character_name=self.character_state.name,
    character_stats={
        'attributes': self.character_state.attributes,
        'skills': self.character_state.skills,
        'soulcredit': self.character_state.soulcredit
    },
    personality=self.personality,
    goals=self.character_state.goals,
    recent_intents=recent,
    void_score=self.character_state.void_score
)
```

### 2. Validate Actions

Before sending action to DM:

```python
from aeonisk.multiagent.action_schema import ActionDeclaration

# Create structured action
action = ActionDeclaration(
    intent="Question Acolyte Senna about her ritual observations",
    description="I approach Senna discreetly and ask what she noticed during the failed bonding ritual",
    attribute="Empathy",
    skill="Social",
    difficulty_estimate=20,
    difficulty_justification="Moderate: she's traumatized but willing to talk",
    character_name=self.character_state.name,
    agent_id=self.agent_id,
    action_type="social"
)

# Validate (checks structure and de-duplication)
validator = self.shared_state.get_action_validator()
is_valid, issues = validator.validate_action(action)

if not is_valid:
    # issues will contain:
    # - Structural problems
    # - Duplicate detection with suggestions
    print(f"Action rejected: {issues}")
    # Re-prompt with suggestions
else:
    # Send to DM
    self.send_message_sync(MessageType.ACTION_DECLARED, None, action.to_dict())
```

### 3. Track Void State

```python
mechanics = self.shared_state.get_mechanics_engine()
void_state = mechanics.get_void_state(self.agent_id)

# Update character state
self.character_state.void_score = void_state.score

# Check corruption level
print(f"Corruption: {void_state.corruption_level}")  # "Pure", "Touched", "Shadowed", etc.

# View history
for change in void_state.history[-3:]:
    print(f"{change['reason']}: {change['old_score']} -> {change['new_score']}")
```

## Common Patterns

### Pattern: Investigation Action

**Player declares:**
```python
action = ActionDeclaration(
    intent="Scan the disrupted resonance field for technical signatures",
    description="Zara calibrates her void-tech scanner to filter out Commune frequencies and identify the disruptor signature",
    attribute="Perception",
    skill="Tech/Craft",
    difficulty_estimate=25,
    difficulty_justification="Challenging due to masked frequencies",
    character_name="Zara Nightwhisper",
    agent_id=self.agent_id,
    action_type="investigate"
)
```

**DM resolves:**
```python
resolution = mechanics.resolve_action(
    intent="Scan the disrupted resonance field",
    attribute="Perception",
    skill="Tech/Craft",
    attribute_value=4,  # Zara's Perception
    skill_value=4,      # Zara's Tech/Craft
    difficulty=25
)

# Roll: 4 × 4 + d20 = 16 + 14 = 30 vs DC 25
# Margin: +5
# Outcome: MODERATE success

if resolution.success:
    mechanics.advance_clock("Saboteur Exposure", 1, "Technical evidence found")

# Log the resolution
if mechanics.jsonl_logger:
    mechanics.jsonl_logger.log_action_resolution(
        resolution, character_name, round_num, narration
    )
```

### Pattern: Ritual Action

**Player declares:**
```
INTENT: Harmonize the group's spiritual bonds
ATTRIBUTE: Willpower
SKILL: Astral Arts
DIFFICULTY: 20 - Moderate, field is damaged but ambient void is low
ACTION_TYPE: ritual
RITUAL: yes
PRIMARY_TOOL: yes - Echo-Calibrator
OFFERING: no
DESCRIPTION: Echo forms a circle with commune members and channels harmonizing resonance through her Echo-Calibrator.
```

**DM resolves:**
```python
resolution, effects = mechanics.resolve_ritual(
    intent="Harmonize group bonds",
    willpower=9,         # Echo's Willpower
    astral_arts=6,       # Echo's Astral Arts
    difficulty=20,
    has_primary_tool=True,
    has_offering=False,  # Will add +1 Void
    agent_id="player_02"
)

# effects = {
#   'void_change': 1,  # No offering
#   'consequences': ['No offering: +1 Void']
# }

void_state = mechanics.get_void_state("player_02")
print(f"Echo's Void: {void_state.score}/10")  # Now 1/10

if resolution.success:
    mechanics.scene_clocks["Communal Stability"].regress(1)  # Improves
```

### Pattern: Scene Clock Filled Trigger

```python
# After each action resolution, check clocks
for clock_name, clock in mechanics.scene_clocks.items():
    if clock.filled and not clock.triggered:  # Track triggered separately
        clock.triggered = True  # Custom flag

        if clock_name == "Saboteur Exposure":
            # Reveal collaborator
            print("BEAT: You've identified Acolyte Senna's mentor as the collaborator!")
            print("New NPC: Mentor Kaelen (attempting to flee to meditation chambers)")

            # Create new clock for pursuit
            mechanics.create_scene_clock("Pursuit: Mentor Kaelen", 4,
                                        "Catch Kaelen before he destroys evidence")

        elif clock_name == "Sanctuary Corruption":
            # Void manifestation
            print("BEAT: The corrupted field coalesces into a minor void entity!")
            print("Combat encounter begins.")
            # Switch to tactical tempo
```

## Difficulty Guidelines Quick Reference

| Difficulty | Target | When to Use |
|------------|--------|-------------|
| Easy | 10 | Trained character in favorable conditions |
| Routine | 15 | Standard professional work |
| Moderate | 20 | Typical adventure challenge |
| Challenging | 25 | Requires expertise and good conditions |
| Difficult | 30 | Expert-level, complex task |
| Very Difficult | 35 | Exceptional skill and luck needed |
| Formidable | 40+ | Nearly impossible without advantages |

## Outcome Tier Effects

| Margin | Tier | Typical Effects |
|--------|------|------------------|
| < -20 | Critical Failure | Catastrophic, advance threat clocks, +Void |
| < 0 | Failure | No progress, minor complication |
| 0-4 | Marginal | Minimal success, partial info |
| 5-9 | Moderate | Standard success, useful progress, +1 clock |
| 10-14 | Good | Clear success, actionable intel, +1-2 clocks |
| 15-19 | Excellent | Great success, major advantage, +2 clocks |
| 20+ | Exceptional | Outstanding, breakthrough, +2-3 clocks |

## Validating Output

**Validate JSONL logs:**
```bash
cd scripts/aeonisk/multiagent
python3 validate_logging.py ../../multiagent_output/session_*.jsonl
```

**Reconstruct narrative:**
```bash
python3 reconstruct_narrative.py ../../multiagent_output/session_*.jsonl > story.md
```

## Troubleshooting

**Virtual environment not activated:**
```bash
# Symptoms: ModuleNotFoundError for chromadb, sentence_transformers
# Fix: cd scripts/aeonisk && source .venv/bin/activate
```

**Player keeps trying same action:**
- Action validator will reject with suggestions
- DM should narrate environmental changes that make repetition impossible

**Void not increasing:**
- Check ritual enforcement (no offering should add +1)
- Check void trigger detection in action intents

**Clocks not advancing:**
- DM must manually call `advance_clock()` after each resolution
- Consider margin size when determining ticks (excellent = 2 ticks, good = 1 tick)

**Suppressed errors:**
```bash
grep ERROR game.log | tail -20
```

## Next Steps

1. Read `.claude/ARCHITECTURE.md` for system architecture
2. Review `content/Aeonisk - YAGS Module - v1.2.2.md` for core rules
3. Read `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` for ML logging details
4. Experiment with different scenarios and clock configurations
