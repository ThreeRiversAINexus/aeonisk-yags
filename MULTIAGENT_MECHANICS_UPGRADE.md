# Multi-Agent System Mechanics Upgrade

This document describes the enhanced mechanical resolution system for the Aeonisk multi-agent gameplay.

## Overview

Based on the Codex Nexum review of our Bond Crisis session, we've implemented a comprehensive mechanical resolution system that addresses all identified issues:

1. ✅ Mechanical resolution (Attribute × Skill + d20 vs Difficulty)
2. ✅ Ritual requirements and cost enforcement
3. ✅ Void progression tracking
4. ✅ Intent de-duplication to prevent action loops
5. ✅ Scene clocks for tracking dramatic tension
6. ✅ Initiative/tempo system
7. ✅ Action Schema forcing structured declarations
8. ✅ Knowledge retrieval from game rules via ChromaDB

## New Components

### 1. Knowledge Retrieval (`knowledge_retrieval.py`)

**Purpose**: Provides DM and players access to game rules and lore.

**Features**:
- ChromaDB-based semantic search (with graceful fallback)
- Indexes all markdown content from `/content` directory
- Provides rule lookups for attributes, skills, rituals, void, difficulty

**Usage**:
```python
from aeonisk.multiagent.knowledge_retrieval import KnowledgeRetrieval

kr = KnowledgeRetrieval()
ritual_rules = kr.get_ritual_rules()
difficulty_guide = kr.get_difficulty_guidelines()
```

**Setup**:
- Optionally install `chromadb` for semantic search
- Falls back to keyword search if ChromaDB unavailable
- First run auto-indexes content files

### 2. Mechanics Engine (`mechanics.py`)

**Purpose**: Core YAGS mechanical resolution.

**Features**:
- `resolve_action()`: Attribute × Skill + d20 vs Difficulty
- `resolve_ritual()`: Enforces ritual requirements (tools, offerings)
- `VoidState`: Per-character void tracking with history
- `SceneClock`: Progress tracking for scenario beats (0-6 or custom)
- Outcome tiers: Failure, Marginal, Moderate, Good, Excellent, Exceptional
- Difficulty presets: Easy(10), Routine(15), Moderate(20), Challenging(25), Difficult(30), etc.

**Usage**:
```python
from aeonisk.multiagent.mechanics import MechanicsEngine, Difficulty

engine = MechanicsEngine()

# Regular action
result = engine.resolve_action(
    intent="Scan for void signatures",
    attribute="Perception",
    skill="Tech/Craft",
    attribute_value=4,
    skill_value=4,
    difficulty=Difficulty.CHALLENGING.value  # 25
)

# Ritual with requirements
result, effects = engine.resolve_ritual(
    intent="Harmonize resonance field",
    willpower=3,
    astral_arts=6,
    difficulty=20,
    has_primary_tool=True,
    has_offering=False,  # Will add +1 Void
    agent_id="player_01"
)
```

**Scene Clocks**:

The review suggested three example clocks (Sanctuary Corruption, Saboteur Exposure, Communal Stability) for the Bond Crisis scenario. **These are scenario-specific examples, not hardcoded.**

The DM should create clocks dynamically based on the scenario:

```python
# DM creates scenario-appropriate clocks
engine.create_scene_clock("Sanctuary Corruption", maximum=6,
                         description="Void contamination spreading")
engine.create_scene_clock("Saboteur Exposure", maximum=6,
                         description="How close to identifying the saboteur")
engine.create_scene_clock("Communal Stability", maximum=6,
                         description="Social cohesion of the commune")

# Advance based on action outcomes
if failed_ritual:
    engine.advance_clock("Sanctuary Corruption", ticks=1, reason="Failed harmonization")

if excellent_investigation:
    engine.advance_clock("Saboteur Exposure", ticks=2, reason="Critical evidence found")

# Check if filled (triggers scenario beat)
if engine.scene_clocks["Saboteur Exposure"].filled:
    # Trigger: collaborator revealed or makes desperate move
```

**General Clock Types**:
- **Threat Clocks**: Danger intensifying (corruption, pursuit, collapse)
- **Progress Clocks**: Party making headway (investigation, ritual completion, trust building)
- **Resource Clocks**: Finite resources depleting (time, supplies, stability)

DMs should create 2-4 clocks per scenario that track the most important dramatic questions.

### 3. Action Schema (`action_schema.py`)

**Purpose**: Forces structured action declarations and prevents repetition.

**Features**:
- `ActionDeclaration` dataclass: Structured action with mechanical details
- `IntentDeduplicator`: Prevents agents from spamming same action
- `ActionValidator`: Validates actions and suggests alternatives
- Prompt templates for guiding agents

**What Agents Must Provide**:
```
INTENT: Brief action description
ATTRIBUTE: Strength/Agility/Endurance/Perception/Intelligence/Empathy/Willpower/Charisma
SKILL: Skill name or None
DIFFICULTY: Estimated target (10-35+)
JUSTIFICATION: Why this difficulty?
ACTION_TYPE: explore/investigate/ritual/social/combat/technical
DESCRIPTION: 1-2 sentence narrative
```

**For Rituals**:
```
RITUAL: yes
PRIMARY_TOOL: yes/no
OFFERING: yes/no
COMPONENTS: Description of materials
```

**De-duplication**:
The system tracks the last 2-3 actions per agent and rejects similar intents:

```python
validator = ActionValidator()

action = ActionDeclaration(
    intent="Scan for void signatures",
    attribute="Perception",
    skill="Tech/Craft",
    # ... other fields
)

is_valid, issues = validator.validate_action(action)
if not is_valid:
    # issues[0]: "Action too similar to recent intents: ['Scan for disruptions', 'Detect void traces']"
    # issues[1]: "Suggested alternatives: Try questioning NPCs; Search physical locations; etc."
```

### 4. Enhanced Prompts (`enhanced_prompts.py`)

**Purpose**: Provide mechanical scaffolding in agent system prompts.

**Features**:
- `get_dm_system_prompt()`: DM prompt with difficulty guidelines, outcome tiers, ritual rules
- `get_player_system_prompt()`: Player prompt with character stats, personality-driven guidance
- Context injection: Recent actions, scene clocks, knowledge base excerpts
- Action format templates

**Example DM Prompt Includes**:
- Difficulty standards (Easy: 10, Moderate: 20, Challenging: 25, etc.)
- Outcome tier definitions (margin-based)
- Ritual mechanics (requirements, void costs)
- Void trigger list
- Current scene clocks
- Recent action resolutions

**Example Player Prompt Includes**:
- Character sheet (attributes, skills, void, soulcredit)
- Personality parameters (risk tolerance, void curiosity, bond preference)
- Recent intents (with warning NOT to repeat)
- Action declaration format
- Personality-driven guidance

## Integration with Existing System

### Shared State Integration

The `SharedState` class now holds references to:
- `mechanics_engine`: The mechanics resolver
- `action_validator`: Action validation and de-duplication
- `knowledge_retrieval`: Rule/lore lookup

Initialize in session:
```python
shared_state = SharedState()
shared_state.initialize_mechanics()
```

### DM Agent Updates (Recommended)

The DM agent should:

1. **Initialize scene clocks** based on scenario:
```python
async def _generate_ai_scenario(self, config):
    # ... existing scenario generation ...

    # Create scenario-specific clocks
    mechanics = self.shared_state.get_mechanics_engine()

    if scenario.theme == "Bond Crisis":
        mechanics.create_scene_clock("Sanctuary Corruption", 6)
        mechanics.create_scene_clock("Saboteur Exposure", 6)
        mechanics.create_scene_clock("Communal Stability", 6)
    elif scenario.theme == "Corporate Intrigue":
        mechanics.create_scene_clock("Corporate Suspicion", 6)
        mechanics.create_scene_clock("Evidence Trail", 6)
    # etc.
```

2. **Resolve player actions mechanically**:
```python
async def _handle_action_declared(self, message):
    action_data = message.payload
    mechanics = self.shared_state.get_mechanics_engine()

    # Extract mechanical details from player action
    result = mechanics.resolve_action(
        intent=action_data['intent'],
        attribute=action_data['attribute'],
        skill=action_data.get('skill'),
        attribute_value=action_data['attribute_value'],
        skill_value=action_data.get('skill_value', 0),
        difficulty=action_data['difficulty']
    )

    # Update clocks based on outcome
    mechanics.update_clocks_from_action(result, action_data)

    # Check for void triggers
    if action_data.get('is_ritual'):
        mechanics.check_void_trigger(action_data['intent'], action_data['agent_id'], {})

    # Narrate with mechanical details
    narration = mechanics.format_resolution_for_narration(result)
    self.send_message_sync(MessageType.DM_NARRATION, None, {'narration': narration})
```

3. **Use knowledge retrieval** for rules questions:
```python
kr = self.shared_state.get_knowledge_retrieval()
ritual_rules = kr.get_ritual_rules()
difficulty_guide = kr.get_difficulty_guidelines()
```

### Player Agent Updates (Recommended)

Player agents should:

1. **Use enhanced prompts** with action schema:
```python
from aeonisk.multiagent.enhanced_prompts import get_player_system_prompt
from aeonisk.multiagent.action_schema import ActionDeclaration

# Build system prompt with mechanical scaffolding
system_prompt = get_player_system_prompt(
    character_name=self.character_state.name,
    character_stats={'attributes': {...}, 'skills': {...}},
    personality=self.personality,
    goals=self.character_state.goals,
    recent_intents=self.recent_intents,
    void_score=self.character_state.void_score
)
```

2. **Parse LLM responses into ActionDeclarations**:
```python
validator = self.shared_state.get_action_validator()

# Parse LLM response into structured action
action = validator.parse_llm_response(llm_response, self.agent_id, self.character_state.name)

# Validate (checks for duplicates, structural issues)
is_valid, issues = validator.validate_action(action)

if not is_valid:
    # Re-prompt with suggestions
    # ...
```

3. **Track void state**:
```python
mechanics = self.shared_state.get_mechanics_engine()
void_state = mechanics.get_void_state(self.agent_id)
self.character_state.void_score = void_state.score
```

## Session Initialization Example

```python
from aeonisk.multiagent.session import SelfPlayingSession
from aeonisk.multiagent.shared_state import SharedState

# Create session with config
session = SelfPlayingSession('session_config.json')

# Initialize mechanics in shared state
session.shared_state.initialize_mechanics()

# DM creates scenario-specific clocks during scenario setup
# (in _generate_ai_scenario or _request_human_scenario)

await session.start_session()
```

## Testing the System

Run a test session with the Bond Crisis scenario:

```bash
cd scripts
python3 run_multiagent_session.py session_config.json
```

Expected improvements:
- ✅ Every action produces a dice roll with margin
- ✅ Rituals enforce tool/offering requirements
- ✅ Void scores change based on actions
- ✅ Agents don't spam identical actions
- ✅ Scene clocks track dramatic progression
- ✅ DM provides mechanical detail in narration

## Configuration Notes

### Session Config

No changes to `session_config.json` required. The mechanical systems initialize automatically via `shared_state`.

### Optional: ChromaDB Setup

For semantic rule lookup:

```bash
pip install chromadb
```

On first run, the system will auto-index content from `/content` directory into `~/.aeonisk/chromadb/`.

If ChromaDB is not installed, the system falls back to keyword search.

## Next Steps

1. **Test** the system with a full session
2. **Tune** difficulty recommendations based on outcomes
3. **Expand** knowledge base with more content files
4. **Add** ritual component database for validation
5. **Implement** initiative order for multi-character combat
6. **Create** scenario templates with pre-defined clocks

## Architecture Summary

```
Session (session.py)
  └─ SharedState (shared_state.py)
      ├─ MechanicsEngine (mechanics.py)
      │   ├─ resolve_action()
      │   ├─ resolve_ritual()
      │   ├─ VoidState tracking
      │   └─ SceneClock management
      ├─ ActionValidator (action_schema.py)
      │   ├─ ActionDeclaration validation
      │   └─ IntentDeduplicator
      └─ KnowledgeRetrieval (knowledge_retrieval.py)
          ├─ ChromaDB semantic search
          └─ Markdown content indexing

DM Agent (dm.py)
  └─ Uses mechanics for resolution
  └─ Creates scenario-specific clocks
  └─ Queries knowledge base

Player Agent (player.py)
  └─ Uses action schema for declarations
  └─ Validates against duplicates
  └─ Tracks void state
```

## Files Modified/Created

**New Files**:
- `scripts/aeonisk/multiagent/knowledge_retrieval.py` - Rule/lore retrieval
- `scripts/aeonisk/multiagent/mechanics.py` - Core YAGS resolution
- `scripts/aeonisk/multiagent/action_schema.py` - Structured actions
- `scripts/aeonisk/multiagent/enhanced_prompts.py` - Mechanical scaffolding

**Modified Files**:
- `scripts/aeonisk/multiagent/shared_state.py` - Added mechanics integration
- `requirements.txt` - Added chromadb, anthropic

**Documentation**:
- `MULTIAGENT_MECHANICS_UPGRADE.md` - This file

## Credits

Based on review by Codex Nexum of the Bond Crisis session (2025-10-20).

Core principles from YAGS (Yet Another Game System) and Aeonisk v1.2.2 module.
