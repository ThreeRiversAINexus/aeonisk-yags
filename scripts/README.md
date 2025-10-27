# Aeonisk Multi-Agent System - Developer Guide

**Running the AI-Powered Tabletop RPG System**

This guide covers installation, configuration, and usage of the Aeonisk multi-agent system. For dataset usage and research applications, see the [main README](../README.md).

## What Is This?

A Python-based multi-agent system where:
- **DM Agent** generates scenarios, adjudicates actions, and narrates outcomes
- **Player Agents** make tactical decisions, role-play characters, and pursue goals
- **Enemy Agents** use tactical AI for combat encounters with morale and positioning

Every session produces detailed JSONL logs capturing:
- Action declarations with attribute/skill selections and difficulty estimates
- Resolution outcomes with dice rolls and narrative descriptions
- Combat exchanges with damage calculations and positioning
- Character state changes (health, void score, soulcredit)
- Round summaries and mission debriefs

## Key Features

### 🎲 Complete Game Mechanics
- **YAGS-based system**: Attribute × Skill + d20 vs Difficulty
- **Void Score**: Spiritual corruption mechanic (0-10 scale)
- **Tactical positioning**: Far/Near range system for combat
- **Scene clocks**: Progress tracking for dramatic tension
- **Talismanic economy**: Four-element energy currency with vendor system

### 🤖 Autonomous AI Agents
- **Externalized prompts**: YAML-based prompt system with versioning
- **Multi-language ready**: Directory structure supports translations
- **Provider abstraction**: Ready for GPT-4, Claude, or local models
- **Action validation**: De-duplication and structural validation

### 📊 ML Training Data
- **10 event types**: scenario, action_declaration, action_resolution, combat_action, etc.
- **Dual combat schemas**: Full damage breakdowns for enemy→player, simplified for player→enemy
- **Narrative + structured data**: ~20,000+ chars per session
- **Validation tools**: Schema validation and narrative reconstruction

### 🎯 Enemy Tactical AI
- **Morale system**: Context-aware morale checks (HP, stuns, outnumbered)
- **Tactical decision-making**: Cover, flanking, focus fire, retreat
- **Escape mechanics**: Athletics checks for fleeing under fire
- **Faction-themed loot**: Currency drops based on enemy affiliation

## Quick Start

### Prerequisites
- Python 3.12+
- Anthropic API key (for Claude)
- OpenAI API key (optional, for GPT models)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aeonisk-yags.git
cd aeonisk-yags

# Set up virtual environment (REQUIRED for ChromaDB)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Running Your First Session

```bash
# From project root, with venv activated
python3 scripts/run_multiagent_session.py scripts/session_config_combat.json
```

This will:
1. Load the combat scenario configuration
2. Initialize DM, player, and enemy agents
3. Run a complete RPG session with tactical combat
4. Generate JSONL logs in `multiagent_output/`

**Watch the console** for:
- Scenario generation and scene clocks
- Player action declarations
- DM narration with dice rolls
- Enemy tactical decisions
- Round summaries

### Validating Output

```bash
# From project root
# Validate JSONL logs
python3 scripts/aeonisk/multiagent/validate_logging.py multiagent_output/session_*.jsonl

# Reconstruct narrative from logs
python3 scripts/aeonisk/multiagent/reconstruct_narrative.py multiagent_output/session_*.jsonl > story.md
```

### Session Configuration

Sessions are configured via JSON files (see `session_config_README.md` in this directory):

```json
{
  "scenario_theme": "Bond Crisis",
  "num_players": 3,
  "max_rounds": 15,
  "enemy_agent_config": {
    "enemy_spawn_frequency": 5,
    "loot_suggestions_enabled": true
  },
  "vendor_spawn_frequency": -1
}
```

**Key Options:**
- `scenario_theme`: "Bond Crisis", "Tactical Combat", "Investigation", "Ritual Challenge"
- `enemy_spawn_frequency`: Spawn enemies every N rounds (-1 to disable)
- `vendor_spawn_frequency`: Spawn vendors every N rounds (-1 to disable)
- `force_vendor_gate`: Require vendor interaction in scenario

## Dataset & Benchmarking

### Aeonisk-86 Dataset

The repository includes a normalized dataset of 86 RPG tasks:
- **Location**: `datasets/aeonisk_dataset_normalized_complete.txt`
- **Structure**: See `datasets/aeonisk_dataset_guidelines.txt` for format specification
- **Content**: Multi-tier outcomes, complete stat blocks, faction context

**Use cases:**
- Training language models on RPG mechanics
- Benchmarking DM adjudication quality
- Fine-tuning for narrative generation

### Aeonisk DM GPT

Try the interactive Aeonisk Dungeon Master:
[Aeonisk DM on ChatGPT](https://chatgpt.com/g/g-680299b1a5f08191b869fe352f33cc1a-aeonisk)

## Project Structure

```
aeonisk-yags/
├── scripts/
│   ├── aeonisk/
│   │   ├── multiagent/          # Multi-agent system (PRIMARY)
│   │   │   ├── session.py       # Game orchestrator
│   │   │   ├── dm.py            # DM agent
│   │   │   ├── player.py        # Player agents
│   │   │   ├── enemy_combat.py  # Enemy AI agents
│   │   │   ├── mechanics.py     # Game mechanics + logging
│   │   │   ├── prompt_loader.py # YAML prompt system
│   │   │   └── prompts/         # Externalized prompts
│   └── run_multiagent_session.py  # Main entry point
├── content/                     # Game rules and lore
├── datasets/                    # Aeonisk-86 dataset
├── multiagent_output/          # Session JSONL logs
├── .venv/                      # Virtual environment (activate first!)
├── .claude/                    # Detailed architecture docs
│   ├── ARCHITECTURE.md         # System architecture deep-dive
│   └── README.md               # AI assistant orientation
├── CLAUDE.md                   # Project instructions (auto-loaded)
└── requirements.txt            # Python dependencies
```

## Future Work

### PettingZoo Integration (In Development)
We're developing a PettingZoo-compatible environment for reinforcement learning research:
- **Multi-agent RL**: Train player agents via PPO/DQN
- **Standardized API**: Compatible with existing RL libraries
- **Tactical scenarios**: Combat, negotiation, investigation
- **Partial observability**: Hidden information and fog of war

This will enable:
- Policy gradient training on RPG decision-making
- Emergent cooperation strategies
- Benchmarking RL algorithms on complex social scenarios

## Documentation

- **Quick Reference**: This README (developer guide)
- **Dataset & Research**: [Main README](../README.md)
- **Architecture Deep-Dive**: `../.claude/ARCHITECTURE.md`
- **Session Configuration**: `session_config_README.md`
- **ML Logging Details**: `aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`
- **AI Assistant Guide**: `../.claude/README.md`

## License

**Aeonisk Content**: Licensed under the Aeonisk Permissive Commercial License (APCL) v1
**YAGS Rules Engine**: Licensed under GNU GPL v2 (see `../yags/LICENSE.md`)

Both licenses permit commercial use. The APCL requires attribution; the GPL requires sharing improvements. See `../LICENSE` for complete APCL text.

## Contributing

This is an open project! Contributions welcome for:
- New scenario types and enemy tactics
- Additional language models (GPT-4, local models)
- Prompt engineering improvements
- ML training experiments with the dataset
- PettingZoo RL integration

**Getting Started**:
1. Review `../.claude/ARCHITECTURE.md` for system design
2. Check `../CLAUDE.md` for critical patterns and common pitfalls
3. Run tests: `pytest aeonisk/`
4. Submit PRs with clear descriptions

See the [main README](../README.md) for research applications and dataset contributions.

## Contact

**Three Rivers AI Nexus**
Email: threeriversainexus@gmail.com

For questions about:
- Commercial licensing arrangements
- Dataset usage and citations
- Collaboration opportunities
- Technical support

---

Built to enable open research in AI-assisted tabletop gaming.
No corporate copyright restrictions—just GPL and permissive commercial use.
