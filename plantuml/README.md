# PlantUML Architecture Diagrams

Comprehensive architecture documentation for the Multi-Agent RPG System.

## Diagrams

1. **01_system_architecture.puml** - High-level system components and relationships
2. **02_session_flow.puml** - Session execution flow (initialization → round loop → debrief)
3. **03_agent_interactions.puml** - Agent roles and interaction patterns
4. **04_llm_provider_architecture.puml** - Multi-provider LLM system (Anthropic/OpenAI)
5. **05_entity_lifecycle.puml** - Enemy ↔ NPC conversion state machine
6. **06_mechanics_processing.puml** - Damage/void/clock processing pipeline
7. **07_jsonl_logging.puml** - ML training data logging system

## Rendering Diagrams

### Option 1: Online Viewer (Quickest)

Visit [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/) and paste diagram code.

### Option 2: VS Code Extension

1. Install extension: [PlantUML](https://marketplace.visualstudio.com/items?itemName=jebbs.plantuml)
2. Open `.puml` file
3. Press `Alt+D` to preview

### Option 3: Command Line (Local)

**Prerequisites:**
```bash
# Install Java (required for PlantUML)
sudo apt install default-jre

# Install Graphviz (for diagram rendering)
sudo apt install graphviz

# Download PlantUML JAR
wget https://github.com/plantuml/plantuml/releases/download/v1.2024.8/plantuml-1.2024.8.jar -O plantuml.jar
```

**Render single diagram:**
```bash
java -jar plantuml.jar 01_system_architecture.puml
# Output: 01_system_architecture.png
```

**Render all diagrams:**
```bash
java -jar plantuml.jar *.puml
```

**Generate SVG (scalable):**
```bash
java -jar plantuml.jar -tsvg 01_system_architecture.puml
# Output: 01_system_architecture.svg
```

**Generate PDF:**
```bash
java -jar plantuml.jar -tpdf 01_system_architecture.puml
# Output: 01_system_architecture.pdf
```

## Diagram Contents

### 01_system_architecture.puml
Shows the complete system component hierarchy:
- Entry point (run_multiagent_session.py)
- Core orchestration (SessionCoordinator, SharedState, TurnManager)
- Agent layer (DM, Player, Enemy, NPC agents + LLM clients)
- LLM provider layer (Anthropic, OpenAI, Local)
- Game systems (MechanicsEngine, TargetIDMapper, AgentConversion, SceneClocks)
- Data layer (JSONLLogger, PromptLoader, JSONL/YAML files)

**Key insights:**
- SharedState provides MechanicsEngine via `get_mechanics_engine()` pattern
- LLM clients support multi-provider (Anthropic/OpenAI/Local)
- Clear separation: orchestration → agents → LLM → game systems

### 02_session_flow.puml
Detailed sequence diagram of a complete session:
- **Initialization:** Config loading, state setup, agent creation
- **Scenario generation:** DM creates setting, spawns enemies, sets clocks
- **Round loop:** DM synthesis → Player turns → Enemy turns → NPC turns → Round summary
- **Session end:** Mission debrief, JSONL close

**Key insights:**
- DM synthesis phase handles entity conversions (NPC ↔ Enemy)
- Each player action goes through: declaration → DM resolution → mechanics processing
- Enemy/NPC actions follow same resolution flow
- JSONL logging happens after mechanics processing

### 03_agent_interactions.puml
Component diagram showing agent responsibilities:
- **DM Agent:** Scenario generation, action resolution, round synthesis/summary, debrief
- **Player Agent:** Action declaration, intent analysis, combat actions
- **Enemy Agent:** Tactical analysis, target selection, combat actions
- **NPC Agent:** Simple actions (flee, hide, plead, comply, dialogue, assist, pass)
- **Shared State:** Character states, combat state, scene clocks, environment
- **Mechanics Engine:** Damage/void/roll processing, effect application

**Key insights:**
- NPCs have limited action set (no attack/tactical)
- All agents read from SharedState, only MechanicsEngine writes
- DM resolution extracts mechanics from narration (damage, void, etc.)
- Scene clocks are bidirectional (progress 0→max, countdown max→0)

### 04_llm_provider_architecture.puml
Multi-provider LLM architecture:
- **Base LLM Client:** Abstract interface for all agent LLM clients
- **Provider implementations:** AnthropicProvider, OpenAIProvider, LocalProvider
- **Pydantic AI framework:** Provider-agnostic structured output
- **Schema definitions:** Scenario, PlayerAction, ActionResolution, RoundSynthesis

**Key insights:**
- OpenAI has 10x higher rate limits (400 req/min vs 75 req/min)
- GPT-5-mini output tokens are 8x cheaper than Claude Sonnet 4.5
- Same Pydantic schemas work across all providers
- Rate limits auto-adjust based on provider

### 05_entity_lifecycle.puml
State machine for entity conversions:
- **Enemy Agent states:** Spawned → Active → Defeated/Surrendered
- **NPC Agent states:** Spawned → Active → Prisoner/Ally/Hostile
- **Conversion paths:** Enemy ↔ NPC with agent_id preservation

**Key insights:**
- **agent_id is STABLE across all conversions** (critical design principle)
- Deescalation: Enemy → NPC (surrender, intimidation, morale break)
- Escalation: NPC → Enemy (attacked, betrayal)
- NPCs can become prisoners (subdued) or allies (befriended)
- NO keyword detection - all via Pydantic schemas (Deescalation/Escalation/NPCSpawn)

### 06_mechanics_processing.puml
Detailed mechanics processing flow:
- **DM generates ActionResolution** with structured fields (narration, roll, effects, void_changes)
- **Mechanics extracts effects:** Damage → HP/wounds, Healing → HP/stabilize, Void → corruption, Clocks → tick updates
- **State updates:** Character HP, void scores, wounds, defeat status
- **JSONL logging:** Action resolution + character state changes

**Key insights:**
- Roll tiers: margin ≥20 (exceptional), ≥10 (great), ≥0 (success), <0 (failure)
- Wound threshold = HP/3 (e.g., 12 HP → 4 damage = 1 wound)
- Void ≥8 triggers high void warning, ≥10 = corrupted
- Clocks trigger events when countdown reaches 0 or progress reaches max

### 07_jsonl_logging.puml
ML training data pipeline:
- **10+ event types:** session_start, scenario, action_declaration/resolution, round_synthesis/summary, character_state, combat_action, enemy_spawn/defeat, mission_debrief, llm_call
- **Analysis tools:** analyze_session.py (quick analysis), extract_fixture.py (round extraction), replay_fixture.py (replay with caching), diff_fixtures.py (compare sessions), validate_logging.py (schema validation), reconstruct_narrative.py (story rebuild)

**Key insights:**
- Each JSONL line = 1 JSON event (50KB - 5MB per session)
- Use analyze_session.py instead of reading huge JSONL files directly
- ML use cases: action→resolution mapping, tactical decisions, damage extraction, void progression, story generation
- Replay system allows testing with selective LLM caching (players cached, DM live)

## Quick Reference

**File naming convention:**
- `<number>_<topic>.puml`
- Numbers indicate suggested reading order

**Diagram relationships:**
1. Start with `01_system_architecture.puml` for overall structure
2. Follow execution flow in `02_session_flow.puml`
3. Understand agent roles in `03_agent_interactions.puml`
4. Learn LLM integration in `04_llm_provider_architecture.puml`
5. Study entity system in `05_entity_lifecycle.puml`
6. Deep dive mechanics in `06_mechanics_processing.puml`
7. Explore ML logging in `07_jsonl_logging.puml`

## Maintenance

**Updating diagrams after code changes:**
1. Identify affected diagram(s)
2. Edit `.puml` file
3. Re-render to verify syntax
4. Commit both `.puml` and rendered output

**Adding new diagrams:**
1. Follow naming convention: `<number>_<topic>.puml`
2. Include title and notes
3. Update this README with description
4. Consider relationships to existing diagrams

## Additional Resources

- **Project docs:** `.claude/ARCHITECTURE.md`, `.claude/README.md`
- **CLAUDE.md:** Essential patterns and quick reference
- **Logging implementation:** `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`
- **Session config guide:** `scripts/session_config_README.md`
- **PlantUML docs:** https://plantuml.com/
