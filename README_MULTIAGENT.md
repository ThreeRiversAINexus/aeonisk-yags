# Aeonisk Multi-Agent Self-Playing System

A distributed system for generating realistic Aeonisk YAGS gameplay data through autonomous AI agents, with full human-in-the-loop capability.

## Features

- **Multi-Agent Architecture**: AI DM, AI Players, coordinated via IPC
- **Human Takeover**: Jump into any agent role at any time
- **Text-Only Interface**: Pure text-based interaction, no graphics
- **Data Generation**: Produces structured gameplay data for training
- **Real-Time Control**: Switch between AI and human control seamlessly

## Quick Start

### 1. Create Configuration

```bash
python scripts/run_multiagent_session.py --create-config example_session.json
```

### 2. Run Session

```bash
python scripts/run_multiagent_session.py example_session.json
```

### 3. Take Control

When the session starts, you'll see a human interface prompt:

```
[Observer]> agents
Available Agents:
  dm_01 (AIDMAgent)
  player_01 (AIPlayerAgent) 
  player_02 (AIPlayerAgent)

[Observer]> control player_01
You now control player_01
[Controlling player_01]> explore the mysterious chamber
```

## Human Interface Commands

### Observer Mode (No Agent Controlled)
- `agents` - List all available agents
- `control <agent>` - Take control of an agent
- `status` - Show current status
- `help` - Show all commands

### Agent Control Mode
- `release` - Return agent to AI control
- `status` - Show character/agent status
- `say <message>` - Speak in character
- Any text - Perform actions as that agent

### Agent-Specific Actions
When controlling a **Player**:
- `explore <description>` - Explore something
- `interact <target>` - Interact with someone/something
- `ritual <name>` - Attempt a ritual
- `status` - View character stats

When controlling the **DM**:
- Respond to player actions with narrative
- Describe scenes and outcomes
- Control NPCs and environment

## Configuration

Example `session_config.json`:

```json
{
  "session_name": "test_session",
  "max_turns": 20,
  "output_dir": "./multiagent_output",
  "enable_human_interface": true,
  "agents": {
    "dm": {
      "llm": {
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7
      }
    },
    "players": [
      {
        "name": "Zara Nightwhisper",
        "faction": "Tempest Industries",
        "personality": {
          "riskTolerance": 8,
          "voidCuriosity": 9,
          "bondPreference": "avoids"
        },
        "attributes": {"Body": 6, "Mind": 8, "Soul": 7},
        "skills": {"Astral Arts": 5, "Investigation": 4},
        "goals": ["Explore void manipulation"]
      }
    ]
  }
}
```

## Architecture

### Processes
- **Game Coordinator**: Manages IPC bus and data collection
- **AI DM**: Orchestrates scenarios and responds to actions
- **AI Players**: Make personality-driven decisions
- **Human Interface**: Text console for human takeover

### Communication
- **IPC**: Unix Domain Sockets for inter-process messaging
- **Message Types**: Turn requests, actions, narration, state sync
- **Real-Time**: Asynchronous message passing

### Data Output
Sessions generate structured data files:
- `session_{id}.json` - Machine-readable gameplay data
- `session_{id}.yaml` - Human-readable session log
- Compatible with existing benchmark system

## Text-Based Gameplay Example

```
=== Starting Session abc123 ===

[DM dm_01] Generated scenario: Void Corruption
Location: Abandoned Astral Node
Situation: The situation involves Void containment

DM: The party finds themselves at Abandoned Astral Node. The situation involves Void containment. 
The air carries a distinct tension, and you sense the void's influence at level 3/10.

[Player Zara Nightwhisper] AI Action: investigate the void presence

[DM] You approach the void disturbance. The reality seems to shimmer and bend around a central point...

[Observer]> control player_01
You now control player_01
[Controlling player_01]> carefully examine the void disturbance using my Astral Arts skill

[Zara Nightwhisper] Declared: carefully examine the void disturbance using my Astral Arts skill

[HUMAN DM] player_01 declared action:
Action: explore
Description: carefully examine the void disturbance using my Astral Arts skill

Your response as DM: You extend your astral senses toward the disturbance. Roll Mind + Astral Arts vs 14.
```

## Integration with Existing Systems

- **Personality System**: Uses your existing `generateAIPersonality` and decision-making logic
- **Character System**: Compatible with Aeonisk character structure
- **Scenario Seeds**: Leverages existing `SCENARIO_SEEDS` from aiDM.ts
- **Data Format**: Outputs data compatible with benchmark system

## Development

The system is modular and extensible:

- `base.py` - IPC infrastructure and agent framework
- `dm.py` - AI Dungeon Master implementation
- `player.py` - AI Player with personality-driven decisions
- `session.py` - Session orchestration and data collection
- `human_interface.py` - Text-based human control interface

## Use Cases

1. **Training Data Generation**: Let AI agents play to generate large datasets
2. **Testing**: Human DM with AI players to test scenarios
3. **Hybrid Play**: Mix of AI and human players for unique experiences
4. **Scenario Validation**: Test campaign ideas with AI players
5. **Benchmark Generation**: Create evaluation datasets for LLM capabilities