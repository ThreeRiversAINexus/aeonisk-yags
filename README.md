# Aeonisk-YAGS

**Multi-agent AI system that plays tabletop RPGs autonomously, generating structured training data for ML research.**

[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)
[![Dataset on HuggingFace](https://img.shields.io/badge/Dataset-HuggingFace-yellow.svg)](https://huggingface.co/ThreeRiversAINexus)

---

## What is Aeonisk-YAGS?

Aeonisk-YAGS is an open-source framework where AI agents—a Dungeon Master, player characters, and enemies—collaborate to play complete tabletop RPG sessions without human intervention. Every action, decision, and outcome is logged in structured JSONL format, creating rich training data for machine learning research.

**The core loop:**
1. **DM Agent** generates scenarios, describes environments, and adjudicates outcomes
2. **Player Agents** declare actions based on character abilities and tactical context
3. **Enemy Agents** use tactical AI with morale, positioning, and coordination
4. **Mechanics Engine** resolves dice rolls, damage, and game state changes
5. **Everything is logged** with full mechanical provenance for ML training

Built on the GPL-licensed YAGS ruleset (Attribute × Skill + d20), Aeonisk adds void corruption, scene clocks, faction dynamics, and a four-element economy—creating semantically rich scenarios that go far beyond abstract toy problems.

---

## Why This Exists

**The problem:** Corporate copyright prevents ML research on semantically rich game environments. You can't train on D&D mechanics (Wizards of the Coast), Star Wars factions (Disney), or any major IP without legal risk.

**The result:** Researchers are stuck with GridWorld, CartPole, or legally murky scraped data.

**The solution:** Aeonisk provides GPL-licensed infrastructure explicitly designed for ML research. No copyright enclosure. Rich semantic domains. Complete mechanical provenance.

---

## Key Features

### For ML Researchers

- **Structured outcome data** with 6-tier taxonomy (critical failure → exceptional success)
- **Complete mechanical provenance** for every outcome (dice rolls, modifiers, margins)
- **Multi-agent coordination data** with faction dynamics and morale systems
- **Counterfactual reasoning** support (each scenario has full outcome distributions)
- **Risk-aware training signals** beyond binary success/failure

### For Developers

- **Multi-provider LLM support** (Anthropic Claude, OpenAI GPT, local models planned)
- **Externalized YAML prompts** with versioning and multi-language support
- **O(n) tactical combat** using concentric ring positioning (vs O(n²) grid pathfinding)
- **Comprehensive logging** with 19 event types for debugging and analysis
- **Modular architecture** for extending mechanics, agents, or scenarios

---

## Quick Start

### Option A: Use the Dataset (ML Researchers)

**HuggingFace** (recommended):
```bash
# Dataset available at huggingface.co/ThreeRiversAINexus
# Growing collection with more scenarios being added regularly
```

**Local repository:**
```python
import yaml

with open('datasets/aeonisk_dataset_normalized_complete.txt', 'r') as f:
    for task in yaml.safe_load_all(f):
        scenario = task['scenario']
        outcomes = task['gold_answer']['outcome_explanation']

        # Access all 6 outcome tiers
        critical_failure = outcomes['critical_failure']
        exceptional_success = outcomes['exceptional']

        # Each tier includes narrative + mechanical effects
        print(f"Task: {task['task_id']}")
        print(f"Scenario: {scenario['context']}")
```

### Option B: Run the Multi-Agent System (Developers)

```bash
# Clone and setup
git clone https://github.com/ThreeRiversAINexus/aeonisk-yags.git
cd aeonisk-yags

# Create virtual environment (required)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API key
export ANTHROPIC_API_KEY="your-key-here"
# Or for OpenAI: export OPENAI_API_KEY="your-key-here"

# Run a session
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_combat.json
```

Output goes to `multiagent_output/session_*.jsonl`

**Full developer guide:** [scripts/README.md](scripts/README.md)

**Complete user and developer book:** [docs/README.md](docs/README.md)

The book covers installation, session configuration, the multi-agent architecture, round lifecycle, mechanics/state ownership, JSONL output, replay/debugging, prompt/schema extension, and testing. It also distinguishes the current structured simulator from the older interactive CLI.

---

## Example Output

Every session produces JSONL logs with events like:

```json
{
  "event_type": "action_resolution",
  "round": 3,
  "agent": "Kira",
  "action": "Hack the security terminal to disable alarms",
  "roll": {
    "attribute": "Intelligence",
    "skill": "Computers",
    "base": 45,
    "roll": 12,
    "total": 57,
    "difficulty": 50,
    "margin": 7,
    "success": true,
    "tier": "moderate"
  },
  "effects": {
    "narrative": "Kira's fingers dance across the holographic interface...",
    "mechanical": "Security systems disabled for 3 rounds",
    "void_change": 0
  }
}
```

19 event types capture everything: scenario setup, action declarations, combat exchanges, enemy spawns, character state changes, round summaries, and mission debriefs.

---

## Dataset Details

**Current size:** 58 scenarios with complete outcome distributions

**Outcome taxonomy (6 tiers):**
| Tier | Margin | Description |
|------|--------|-------------|
| Critical Failure | < -20 | Catastrophic consequences |
| Failure | < 0 | No progress, complications |
| Marginal | 0-4 | Minimal success |
| Moderate | 5-9 | Standard success |
| Good | 10-14 | Clear success with advantage |
| Exceptional | 20+ | Outstanding breakthrough |

**Scenario types:** Combat, investigation, social/negotiation, ritual/void mechanics

**What makes this different:**
- Multi-tier outcomes enable counterfactual reasoning (not just what happened, but what could have)
- Full mechanical provenance (you know exactly why each outcome occurred)
- Graduated reward signals for nuanced training
- Human-in-the-loop synthetic generation with schema enforcement

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Session Orchestrator                      │
│                      (session.py)                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │   DM    │    │ Player  │    │  Enemy  │    │   NPC   │  │
│  │  Agent  │    │ Agents  │    │ Agents  │    │ Agents  │  │
│  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘  │
│       │              │              │              │        │
│       └──────────────┴──────────────┴──────────────┘        │
│                          │                                  │
│                 ┌────────▼────────┐                         │
│                 │    Mechanics    │                         │
│                 │     Engine      │                         │
│                 │  (mechanics.py) │                         │
│                 └────────┬────────┘                         │
│                          │                                  │
│                 ┌────────▼────────┐                         │
│                 │  JSONL Logger   │                         │
│                 │  (19 event      │                         │
│                 │   types)        │                         │
│                 └─────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

**Key components:**
- **DM Agent** (`dm.py`) - Scenario generation, action adjudication, narrative synthesis
- **Player Agents** (`player.py`) - Character decision-making with personality and goals
- **Enemy Agents** (`enemy_combat.py`) - Tactical AI with morale, positioning, retreat logic
- **Mechanics Engine** (`mechanics.py`) - YAGS dice resolution, damage, void corruption
- **Prompt System** (`prompts/`) - Externalized YAML prompts for all LLM interactions

**Full architecture docs:** [.claude/ARCHITECTURE.md](.claude/ARCHITECTURE.md)

---

## Research Applications

**What you can build with this:**

- **LLM Benchmarking** - Compare reasoning quality on grounded tactical scenarios
- **Multi-Agent RL** - Coordination testbed with faction dynamics (PettingZoo integration planned)
- **Risk Assessment** - Outcome distributions enable risk-aware planning research
- **Counterfactual Reasoning** - Each scenario has 6 counterfactual outcomes to train on
- **Alignment Research** - Void corruption models gradual value drift
- **Narrative Generation** - Hundreds of examples of degree-appropriate storytelling

---

## Project Status

**Current:**
- Multi-agent simulation framework (stable)
- 58-scenario dataset with multi-tier outcomes
- Support for Anthropic Claude and OpenAI GPT models
- Comprehensive JSONL logging (19 event types)
- NPC de-escalation and conversion system
- Economy system with vendors and purchases

**In Development:**
- Expanded scenario library
- PettingZoo environment for RL research
- Local model support (Llama, Mistral)

**Roadmap:**
- Multi-language prompt support
- Benchmark comparisons across models
- Research paper on multi-tier outcome capture

---

## Documentation

| Document | Description |
|----------|-------------|
| [Developer Guide](scripts/README.md) | Installation, running sessions, configuration |
| [Session Config Reference](scripts/session_config_README.md) | All configuration options explained |
| [Architecture Deep-Dive](.claude/ARCHITECTURE.md) | System design and component interactions |
| [ML Logging Details](scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md) | Event types and schema documentation |
| [Dataset Guidelines](datasets/aeonisk_dataset_guidelines.txt) | Dataset format specification |

---

## Interactive Demo

Try the Aeonisk DM as a ChatGPT Custom GPT:
[chat.openai.com - Aeonisk DM](https://chatgpt.com/g/g-680299b1a5f08191b869fe352f33cc1a-aeonisk)

---

## Contributing

Contributions welcome! Areas of interest:

- **Dataset expansion** - More scenarios, edge cases, domain coverage
- **Model integrations** - Local models, new providers
- **RL integration** - PettingZoo environment completion
- **Prompt engineering** - Better outcome generation and agent behavior
- **Benchmarking** - Results and analysis across different models

**Note:** GPL license means improvements must be shared back. That's the point.

---

## License

- **Code & YAGS Mechanics:** GNU GPL v2
- **Dataset & Lore:** Aeonisk Permissive Commercial License (APCL) v1

Both permit commercial use. GPL requires sharing improvements; APCL requires attribution.

See [LICENSE](LICENSE) for complete terms.

---

## Citation

```bibtex
@software{aeonisk_yags_2025,
  title={Aeonisk-YAGS: Multi-Agent Tabletop RPG System for ML Training Data},
  author={{Three Rivers AI Nexus}},
  year={2025},
  publisher={GitHub},
  url={https://github.com/ThreeRiversAINexus/aeonisk-yags}
}
```

---

## Contact

**Three Rivers AI Nexus**
Email: threeriversainexus@gmail.com

Questions about dataset usage, commercial licensing, research collaborations, or technical support.

---

*Built because copyright shouldn't block research.*
