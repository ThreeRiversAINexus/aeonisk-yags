# Multi-Agent System Architecture

**Status:** Current as of 2025-10-23
**Branch:** feature/tactical-enemy-agents

## High-Level Overview

The Aeonisk multi-agent system is a **single-process, asyncio-based** architecture where AI agents (DM, players, enemies) interact via an in-memory message bus to simulate tabletop RPG sessions and generate ML training data.

```
┌─────────────────────────────────────────────────────────┐
│                    Session (Orchestrator)                │
│  - Game loop (declare → adjudicate → synthesize)        │
│  - Phase management (DECLARATION, ADJUDICATION, etc.)   │
│  - JSONL logging integration                            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│              Message Bus (MessageBus class)              │
│  - In-memory asyncio event system                       │
│  - Topic-based subscription                             │
│  - Async message delivery                               │
└────────┬────────────────────────────┬───────────────────┘
         │                            │
         ▼                            ▼
┌─────────────────┐         ┌─────────────────────────────┐
│   DM Agent      │         │   Player/Enemy Agents       │
│  - Narration    │         │  - Action declarations      │
│  - Adjudication │         │  - Character state          │
│  - Clock mgmt   │         │  - Tactical AI              │
└─────────────────┘         └─────────────────────────────┘
         │                            │
         └────────────┬───────────────┘
                      ▼
         ┌────────────────────────────┐
         │   Shared State             │
         │  - MechanicsEngine         │
         │  - ActionValidator         │
         │  - KnowledgeRetrieval      │
         │  - JSONLLogger             │
         └────────────────────────────┘
```

## Core Components

### 1. Session (`session.py`)

**Role:** Game loop orchestrator and phase manager

**Key Responsibilities:**
- Runs the 4-phase game loop:
  1. **DECLARATION** - Players/enemies declare actions
  2. **ADJUDICATION** - DM resolves actions one by one
  3. **SYNTHESIS** - DM summarizes the round
  4. **CLEANUP** - Enemy actions, state logging, round summary
- Integrates JSONL logging at appropriate points
- Manages scenario setup and game state
- Coordinates between agents via message bus

**Important Patterns:**
```python
# Round synthesis: DM generates, Session logs
# session.py:1484-1495
async def _handle_round_synthesis(self, message: Message):
    content = message.payload.get('content', '')
    mechanics = self.shared_state.get_mechanics_engine()
    if mechanics and hasattr(mechanics, 'jsonl_logger'):
        mechanics.jsonl_logger.log_round_synthesis(content, round_num)
```

**Location:** `scripts/aeonisk/multiagent/session.py` (~1500 lines)

### 2. Message Bus (`base.py`)

**Role:** In-memory async event system

**Architecture:**
- **NOT** Unix Domain Sockets (old architecture)
- **NOT** multi-process IPC
- **IS** asyncio-based publish/subscribe in single process

**Key Classes:**
- `MessageBus` - Manages subscriptions and delivery
- `Message` - Data structure for inter-agent communication
- `MessageType` - Enum of all message types

**Message Flow Example:**
```
Player → ACTION_DECLARED → Message Bus → DM
DM    → ACTION_RESOLVED  → Message Bus → Player, Session
Session → (logs to JSONL)
```

**Location:** `scripts/aeonisk/multiagent/base.py`

### 3. DM Agent (`dm.py`)

**Role:** Dungeon Master - narration, adjudication, scenario management

**Key Responsibilities:**
- Generate scenarios with themed scene clocks
- Resolve player/enemy actions with mechanical dice rolls
- Update scene clocks based on outcomes
- Generate narrative via LLM
- Create round synthesis summaries

**Scenario-Specific Clocks:**
```python
# dm.py creates 2-4 clocks per scenario type
SCENARIO_SEEDS = {
    'Bond Crisis': [
        ('Sanctuary Corruption', 6, 'Void contamination spreading'),
        ('Saboteur Exposure', 6, 'Progress identifying collaborator'),
        ('Communal Stability', 6, 'Social cohesion of commune')
    ],
    # ... more scenarios
}
```

**Location:** `scripts/aeonisk/multiagent/dm.py` (~1800 lines)

### 4. Player Agent (`player.py`)

**Role:** AI-controlled player character with personality

**Key Responsibilities:**
- Declare actions based on personality traits
- Use ActionDeclaration schema with mechanical details
- Validate actions (de-duplication, structure)
- Update character state (void, health, position)

**Action Declaration Pattern:**
```python
action = ActionDeclaration(
    intent="Scan the disrupted resonance field",
    description="Zara calibrates her void-tech scanner...",
    attribute="Perception",
    skill="Tech/Craft",
    difficulty_estimate=25,
    difficulty_justification="Challenging: masked frequencies",
    character_name="Zara Nightwhisper",
    agent_id=self.agent_id,
    action_type="investigate"
)
```

**Location:** `scripts/aeonisk/multiagent/player.py`

### 5. Enemy Agent (`enemy_combat.py`)

**Role:** Tactical AI for enemy combatants

**Key Features:**
- Autonomous AI decision-making (not DM-controlled)
- Group mechanics (squad of 4 = 1 agent)
- Tactical combat integration
- Void tracking and corruption
- LLM-driven target selection and actions

**Tactical Patterns:**
- Ranged enemies maintain Far range, use cover
- Melee enemies close to Near, focus wounded targets
- Supports prioritize healing/buffing allies

**Location:** `scripts/aeonisk/multiagent/enemy_combat.py` (~1400 lines)

### 6. Shared State (`shared_state.py`)

**Role:** Centralized access to game systems

**Provided Services:**
```python
class SharedState:
    mechanics_engine: MechanicsEngine      # Dice, clocks, void
    action_validator: ActionValidator      # De-duplication
    knowledge_retrieval: KnowledgeRetrieval # RAG for rules
    # ... scenario, narrative state
```

**Critical Pattern:**
```python
# ✅ CORRECT - Only way to access mechanics
mechanics = self.shared_state.get_mechanics_engine()

# ❌ WRONG - These don't exist
mechanics = self.coordinator.mechanics
mechanics = self.mechanics
```

**Location:** `scripts/aeonisk/multiagent/shared_state.py`

### 7. Mechanics Engine (`mechanics.py`)

**Role:** Core YAGS game mechanics

**Key Systems:**
- **Action Resolution:** Attribute × Skill + d20 vs DC
- **Scene Clocks:** Progress tracking (6-10 ticks)
- **Void Tracking:** Per-character corruption (0-10)
- **Ritual System:** Tool/offering requirements
- **JSONL Logging:** JSONLLogger class (lines 55-509)

**Resolution Example:**
```python
resolution = mechanics.resolve_action(
    intent="Scan disrupted field",
    attribute="Perception",
    skill="Tech/Craft",
    attribute_value=4,
    skill_value=4,
    difficulty=25
)
# Roll: 4 × 4 + d20 = 16 + 14 = 30 vs DC 25
# Margin: +5, Outcome: MODERATE success
```

**Location:** `scripts/aeonisk/multiagent/mechanics.py` (~600 lines)

## Threading Model

**Asyncio-Based (Primary):**
- All agents run in same process
- Message bus is async/await
- DM and agents are async message handlers

**Threading (Minimal):**
- **Only** for human interface CLI input (`human_interface.py`)
- Separate daemon thread for `input()` calls
- Everything else is asyncio

```python
# human_interface.py:52
command_thread = threading.Thread(target=self._command_loop, daemon=True)
command_thread.start()
```

## Message Types & Flow

### Key Message Types

```python
class MessageType(Enum):
    SCENARIO_SETUP       # DM → All: Scenario start
    ACTION_DECLARED      # Player/Enemy → DM: Action with mechanics
    ACTION_RESOLVED      # DM → Player/Enemy: Resolution + narration
    ROUND_SYNTHESIS      # DM → All: Round summary
    CHARACTER_UPDATE     # Agent → Session: State change
    # ... see base.py for full list
```

### Typical Round Flow

```
1. Session broadcasts TURN_REQUEST (DECLARATION phase)
2. Players/Enemies respond with ACTION_DECLARED
3. Session enters ADJUDICATION phase
4. DM receives ACTION_DECLARED messages
5. DM resolves each action:
   - mechanics.resolve_action()
   - Update clocks
   - Generate narrative
   - Broadcast ACTION_RESOLVED
6. Session enters SYNTHESIS phase
7. DM generates round summary
8. DM broadcasts ROUND_SYNTHESIS (is_round_synthesis: True)
9. Session receives and logs it
10. Session enters CLEANUP phase
11. Enemy agents take actions
12. Session logs character states + round summary
```

## Data Flow: Content Generation vs Logging

**Important Pattern:** Content generation and logging often happen in different places.

**Example - Round Synthesis:**
```
DM generates summary (dm.py:998-1012)
    ↓
DM broadcasts message with is_round_synthesis: True
    ↓
Session receives message (session.py:1484)
    ↓
Session logs it (session.py:1489-1495) ← NOT DM!
```

**Why:** Separation of concerns - DM focuses on content, Session orchestrates logging.

## ML Logging System

**Architecture:**
- `JSONLLogger` class in `mechanics.py` (lines 55-509)
- 10 event types (scenario, action_declaration, action_resolution, round_synthesis, etc.)
- Dual combat schemas (enemy→player vs player→enemy)
- Comprehensive logging (~20,000+ chars per session)

**Integration Points:**
- Session startup → log scenario
- Player action declaration → log action_declaration
- DM resolution → log action_resolution (via mechanics)
- Session receives round synthesis → log round_synthesis
- Cleanup phase → log character_state, round_summary
- Combat → log combat_action (bidirectional)
- Enemy spawn/defeat → log enemy_spawn, enemy_defeat

**Output:** `multiagent_output/session_*.jsonl`

**Validation:** `python3 validate_logging.py ../../multiagent_output/session_*.jsonl`

**See:** `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md` for full details

## Knowledge Retrieval (RAG)

**System:** ChromaDB + sentence-transformers (requires venv)

**Indexed Content:**
- `content/` - Aeonisk game rules
- `converted_yagsbook/markdown/` - Core YAGS mechanics

**Usage:**
```python
kr = self.shared_state.get_knowledge_retrieval()
ritual_rules = kr.get_ritual_rules()
results = kr.query("How do bonds work?", n_results=2)
```

**Fallback:** Keyword search if ChromaDB not installed

**Location:** `scripts/aeonisk/multiagent/knowledge_retrieval.py`

## Configuration

**Session Config:** `scripts/session_config_combat.json`

**Key Fields:**
- `session_name` - Output file prefix
- `max_rounds` - Round limit
- `scenario_seed` - Scenario type or "random"
- `agents.players[]` - Player character definitions
- `agents.enemies[]` - Enemy definitions (if enabled)
- `llm` - Model provider/config (OpenAI, Anthropic)

## Directory Structure

```
scripts/aeonisk/multiagent/
├── base.py              # Message bus, agent framework
├── session.py           # Game loop orchestrator
├── dm.py                # DM agent
├── player.py            # Player agent
├── enemy_combat.py      # Enemy agent + tactical AI
├── mechanics.py         # YAGS mechanics + JSONLLogger
├── shared_state.py      # Centralized state
├── knowledge_retrieval.py  # RAG system
├── action_schema.py     # Action validation
├── enhanced_prompts.py  # LLM prompts
├── validate_logging.py  # JSONL validation
├── reconstruct_narrative.py  # Story rebuilder
└── LOGGING_IMPLEMENTATION.md
```

## Common Pitfalls

### 1. Forgetting Virtual Environment
```bash
# ❌ WRONG
python3 run_multiagent_session.py session_config_combat.json

# ✅ CORRECT
cd scripts/aeonisk && source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_config_combat.json
```

### 2. Wrong Mechanics Access
```python
# ❌ All wrong
mechanics = self.coordinator.mechanics
mechanics = self.mechanics

# ✅ Only this works
mechanics = self.shared_state.get_mechanics_engine()
```

### 3. Ignoring Suppressed Errors
Message handler errors are caught and logged but don't crash:
```bash
grep ERROR game.log | tail -20
```

### 4. Assuming IPC/Multi-Process
Old docs mentioned Unix sockets. Current architecture is **asyncio-based, single-process**.

## Performance Notes

- **LLM calls:** ~2-3 seconds per turn (rate-limited)
- **ChromaDB indexing:** ~5-10 seconds first run, instant after
- **Memory:** Minimal, single-process
- **Concurrency:** Asyncio handles all agents concurrently

## Testing

**Run session:**
```bash
cd scripts/aeonisk && source .venv/bin/activate
python3 ../run_multiagent_session.py ../session_config_combat.json
```

**Validate output:**
```bash
python3 multiagent/validate_logging.py ../../multiagent_output/session_*.jsonl
```

**Reconstruct narrative:**
```bash
python3 multiagent/reconstruct_narrative.py ../../multiagent_output/session_*.jsonl
```

**Check logs:**
```bash
tail -100 game.log
grep ERROR game.log
```

## References

- **CLAUDE.md** - Main guide (auto-loaded)
- **LOGGING_IMPLEMENTATION.md** - ML logging details
- **content/** - Game rules (canonical source)
- **converted_yagsbook/markdown/** - Core YAGS mechanics

---

**Last Updated:** 2025-10-23 (Documentation reset)
