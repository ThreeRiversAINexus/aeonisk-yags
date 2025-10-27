# Aeonisk: Open Multi-Agent Research Infrastructure

**GPL-licensed benchmark for tactical reasoning, risk assessment, and multi-agent coordination**

## The Problem

Corporate copyright prevents ML research on semantically rich environments:
- **Can't train on D&D mechanics** (Wizards of the Coast)
- **Can't use Star Wars factions** (Disney)
- **Can't touch any major IP** without legal risk

Researchers are forced to use:
- Abstract toy problems (GridWorld, CartPole)
- Scraped data (legally murky)
- Synthetic LLM output (circular training)

**This stifles research.**

## The Solution

Aeonisk provides GPL-licensed infrastructure explicitly designed for ML research:

### 📊 Aeonisk-86 Benchmark Dataset

**86 tactical scenarios with complete outcome distributions**

Unlike datasets capturing only realized outcomes, Aeonisk-86 provides the ENTIRE outcome space:
- **6-tier taxonomy**: Critical failure → Exceptional success
- **516 distinct labeled outcomes** (86 scenarios × 6 tiers)
- **Full mechanical provenance** for each outcome
- **Narrative + mechanical effects** specified

**Novel contributions:**
- Multi-tier outcome capture enables counterfactual reasoning
- Complete risk profiles for each scenario
- Graduated reward signals beyond binary success/failure
- Human-in-the-loop synthetic generation with schema enforcement

**Dataset:** `datasets/aeonisk_dataset_normalized_complete.txt` | [Hugging Face - COMING SOON]

### 🎮 Multi-Agent Simulation Environment

**O(n) tactical combat system designed for large-scale simulation**

- Concentric ring positioning (vs O(n²) grid pathfinding)
- Declare/resolve framework (commitment under uncertainty)
- Faction dynamics with corruption mechanics
- Full Python implementation with autonomous agents

**Code:** This repository ([Setup Guide](scripts/README.md))

### 🔬 Research Applications

**What you can do with this:**

- **Benchmarking**: Compare LLM reasoning on grounded tactical scenarios
- **Multi-Agent RL**: Coordination testbed with faction dynamics
- **Risk Assessment**: Outcome distributions enable risk-aware planning
- **Counterfactual Reasoning**: Each scenario has 6 counterfactual outcomes
- **Graduated Rewards**: Move beyond binary success/failure
- **Alignment Research**: Void corruption models alignment drift
- **Narrative Generation**: 516 examples of degree-appropriate storytelling

## Quick Start

### Using The Dataset

```python
# Load from repository
import yaml

with open('datasets/aeonisk_dataset_normalized_complete.txt', 'r') as f:
    dataset = yaml.safe_load_all(f)

for task in dataset:
    scenario = task['scenario']
    outcomes = task['gold_answer']['outcome_explanation']
    # outcomes contains all 6 tiers with narratives + mechanics

    # Example: Access specific outcome tier
    critical_failure = outcomes['critical_failure']
    exceptional_success = outcomes['exceptional']
```

**Coming soon:** Hugging Face dataset with standardized API

### Running The Multi-Agent System

```bash
# Setup (one-time)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run a session
python3 scripts/run_multiagent_session.py scripts/session_config_combat.json
```

Generates complete RPG sessions with:
- DM scenario generation
- Player tactical decisions
- Enemy AI with morale system
- Detailed JSONL logs for analysis

**Full setup guide:** [scripts/README.md](scripts/README.md)

## Why GPL?

This project is **explicitly GPL-licensed to route around copyright enclosure**.

ML researchers should be able to use familiar, semantically rich domains without legal risk. D&D shouldn't be off-limits. Neither should any rich semantic space.

If you think copyright enclosure is a problem:
- Use this dataset
- Extend this system
- Build on this infrastructure

GPL means improvements must be shared. That's the point.

## Dataset Details

**Location:** `datasets/aeonisk_dataset_normalized_complete.txt`

**Schema:** See `datasets/aeonisk_dataset_guidelines.txt`

**Properties:**
- 86 scenarios across multiple domains (combat, social, investigation, ritual)
- 6-tier outcome taxonomy per scenario
- Full attribute/skill/difficulty specifications
- Consistent YAML format
- Complete mechanical provenance

**Methodology:**
- Human-in-the-loop synthetic generation
- Schema enforcement for consistency
- AI adjudication using YAGS ruleset
- Multi-tier capture (not just realized outcomes)

**Outcome Tiers:**
- **Critical Failure** (< -20 margin): Catastrophic consequences
- **Failure** (< 0): No progress, complications
- **Marginal** (0-4): Minimal success
- **Moderate** (5-9): Standard success
- **Good** (10-14): Clear success
- **Excellent** (15-19): Major advantage
- **Exceptional** (20+): Outstanding breakthrough

## System Architecture

Built on:
- **YAGS Core Rules** (GPL v2) - Attribute × Skill + d20 system
- **Aeonisk Module** - Void/Soulcredit/Bond mechanics
- **Multi-Agent Framework** - Autonomous DM, players, enemies
- **O(n) Tactical System** - Ring-based positioning

Full architecture docs: `.claude/ARCHITECTURE.md`

## Project Status

**Current (v0.1):**
- ✅ 86-task dataset with multi-tier outcomes
- ✅ Multi-agent simulation framework
- ✅ O(n) tactical combat system
- ✅ Autonomous DM, player, and enemy agents
- ✅ JSONL logging for ML training data

**In Development:**
- 🚧 PettingZoo integration for RL research
- 🚧 Hugging Face dataset publication
- 📝 Research paper on multi-tier outcome capture

**Future Work:**
- Expanded dataset (200+ scenarios)
- Additional scenario types
- Multi-language prompt support
- Benchmark comparisons across models

## For Developers

Want to run the multi-agent system? See [**scripts/README.md**](scripts/README.md) for:
- Detailed installation and setup
- Running sessions and configurations
- Validating JSONL output
- Architecture and codebase tour

## Documentation

- **Dataset Schema**: `datasets/aeonisk_dataset_guidelines.txt`
- **System Architecture**: `.claude/ARCHITECTURE.md`
- **Code Setup**: `scripts/README.md`
- **Session Config**: `scripts/session_config_README.md`
- **ML Logging Details**: `scripts/aeonisk/multiagent/LOGGING_IMPLEMENTATION.md`

## Contributing

Contributions welcome for:
- **Dataset expansion**: More scenarios, domains, edge cases
- **Prompt engineering**: Better outcome generation
- **RL integration**: PettingZoo environment completion
- **Model comparisons**: Benchmark results and analysis

GPL requirement: Improvements must be shared back.

## Interactive Demo

Try the Aeonisk DM GPT:
[ChatGPT Custom GPT](https://chatgpt.com/g/g-680299b1a5f08191b869fe352f33cc1a-aeonisk)

## License

- **Dataset & Lore**: Aeonisk Permissive Commercial License (APCL) v1
- **Code & YAGS Mechanics**: GNU GPL v2

Both permit commercial use. APCL requires attribution; GPL requires sharing improvements. See `LICENSE` for complete APCL text and `yags/LICENSE.md` for YAGS GPL terms.

## Citation

```bibtex
@dataset{aeonisk86_2025,
  title={Aeonisk-86: Multi-Agent Tactical Reasoning Benchmark with Complete Outcome Distributions},
  author={Three Rivers AI Nexus},
  year={2025},
  publisher={GitHub},
  url={https://github.com/yourusername/aeonisk-yags}
}
```

## Contact

**Three Rivers AI Nexus**
Email: threeriversainexus@gmail.com

Questions about:
- Dataset usage and citations
- Commercial licensing arrangements
- Research collaborations
- Technical support

---

Built because copyright shouldn't block research.
