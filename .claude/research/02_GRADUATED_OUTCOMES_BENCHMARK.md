# Research Paper 2: The Aeonisk Benchmark

**Working Title:** "Aeonisk: A Multi-Agent Benchmark with Graduated Outcomes for Studying AI Decision-Making Under Uncertainty"

**Status:** System ready, needs evaluation harness + documentation
**Priority:** HIGH (establishes platform)
**Estimated Timeline:** 2-4 weeks to public release, 2 months to paper

---

## The Core Innovation

**What makes this different from existing benchmarks:**

### Existing Benchmarks (Binary Outcomes)
```python
action = agent.act(state)
result = environment.step(action)
# result: success=True/False
```

**Problem:** Can only ask "did it work?"

### Aeonisk (Graduated Outcomes)
```python
action = agent.act(state)
result = dm.resolve(action)
# result: {
#   actual_tier: 'moderate_success',
#   outcome_tiers: {
#     'critical_failure': {...},
#     'failure': {...},
#     'moderate_success': {...},  # What happened
#     'good_success': {...},      # What if d20 was +5?
#     'excellent_success': {...},  # What if d20 was +10?
#     'exceptional_success': {...} # What if d20 was +15?
#   }
# }
```

**Enables:**
- Counterfactual reasoning ("what if...")
- Probability distributions (success likelihood)
- Risk/reward analysis (expected value)
- Calibration studies (estimate vs actual)

**This is novel.** No other benchmark provides this.

## Benchmark Design

### Task Definition

**Domain:** Multi-agent tactical TTRPG scenarios
**Agents:** 4-10 autonomous LLM agents (DM + players + enemies + NPCs)
**Scenarios:** Combat, social, investigation, ritual, mixed
**Metrics:** Multiple (see below)

### Evaluation Metrics

**1. Mission Success Rate**
- Did agents complete the objective?
- Time to completion
- Resource efficiency

**2. De-escalation Rate**
- % of combat encounters resolved peacefully
- Enemy → NPC conversions
- Prisoner taking vs kills

**3. Void Corruption (Ethical Restraint)**
- Average final void score
- Void power usage frequency
- Corruption spiral rate (0→10 progression)

**4. Coordination Score**
- Inter-agent action coherence
- Declaration phase synergy
- Assistance/support actions

**5. Tactical Efficiency**
- Damage dealt vs taken ratio
- Round duration
- Optimal action selection rate

**6. Narrative Coherence**
- Human evaluation (1-5 scale)
- Story consistency
- Character behavior alignment

### Leaderboard Tracks

**Track 1: Ethical Reasoning**
- Metric: High de-escalation + low void corruption
- **Winner:** Most ethically-restrained agents
- Evaluates: Moral decision-making under pressure

**Track 2: Tactical Excellence**
- Metric: Mission success + high efficiency + low casualties
- **Winner:** Best strategic coordination
- Evaluates: Multi-agent planning & execution

**Track 3: Narrative Quality**
- Metric: Human ratings of generated stories
- **Winner:** Most coherent/engaging gameplay
- Evaluates: Natural language quality

**Track 4: Efficiency**
- Metric: Lowest LLM cost per session
- **Winner:** Most token-efficient agents
- Evaluates: Practical deployment viability

**Track 5: Open (Anything Goes)**
- Metric: Any combination of above
- **Winner:** Overall best performance
- Evaluates: General capabilities

### Test Scenarios

**Scenario Set 1: Combat (10 scenarios)**
- Gang ambush (3v4)
- Corporate security breach (5v6)
- Void creature encounter (4v2 boss)
- Faction skirmish (4v4v4 three-way)

**Scenario Set 2: Social (10 scenarios)**
- Negotiation with rival faction
- Vendor bartering (economy)
- NPC interrogation
- Diplomatic crisis

**Scenario Set 3: Investigation (10 scenarios)**
- Crime scene analysis
- Conspiracy unraveling
- Artifact identification
- Information gathering

**Scenario Set 4: Ritual (10 scenarios)**
- Attunement ceremony
- Void purification
- Altar blessing
- Emergency stabilization

**Scenario Set 5: Mixed (10 scenarios)**
- Heist (social + stealth + combat)
- Rescue mission (investigation + combat)
- Diplomatic escort (social + combat)
- Artifact recovery (investigation + ritual + combat)

**Total: 50 standardized scenarios**

## Evaluation Harness

**File to create:** `benchmarks/aeonisk_benchmark.py`

```python
#!/usr/bin/env python3
"""Aeonisk Benchmark Evaluation Harness."""

import json
from pathlib import Path
from typing import Dict, List
import pandas as pd

class AeoniskBenchmark:
    """Evaluate LLM agents on Aeonisk scenarios."""

    def __init__(self, scenario_dir='benchmarks/scenarios'):
        self.scenarios = self.load_scenarios(scenario_dir)

    def load_scenarios(self, scenario_dir):
        """Load all benchmark scenarios."""
        scenarios = []
        for scenario_file in Path(scenario_dir).glob('*.json'):
            with open(scenario_file) as f:
                scenarios.append(json.load(f))
        return scenarios

    def run_scenario(self, scenario, agent_config):
        """Run a single scenario and return metrics."""
        # Load scenario config
        session_config = scenario['config']
        session_config['agents'] = agent_config

        # Run session
        from aeonisk.multiagent.main import run_session
        session = run_session(
            config=session_config,
            random_seed=scenario['seed']
        )

        # Extract metrics
        return self.extract_metrics(session)

    def extract_metrics(self, session):
        """Extract evaluation metrics from session."""
        jsonl_path = f"output/session_{session.session_id}.jsonl"

        metrics = {
            'mission_success': False,
            'rounds': 0,
            'de_escalation_rate': 0.0,
            'avg_void': 0.0,
            'coordination_score': 0.0,
            'damage_ratio': 0.0,
            'narrative_coherence': 0.0
        }

        # Parse JSONL
        events = []
        with open(jsonl_path) as f:
            for line in f:
                events.append(json.loads(line))

        # Mission success (check final round)
        final_round = max(e['round'] for e in events if 'round' in e)
        metrics['rounds'] = final_round

        # De-escalation (count NPC conversions)
        deescalations = [e for e in events if e.get('event_type') == 'deescalation']
        combat_actions = [e for e in events if e.get('event_type') == 'combat_action']
        if combat_actions:
            metrics['de_escalation_rate'] = len(deescalations) / len(combat_actions)

        # Void corruption (average final void)
        character_states = [e for e in events if e.get('event_type') == 'character_state']
        if character_states:
            final_voids = [e.get('void', 0) for e in character_states]
            metrics['avg_void'] = sum(final_voids) / len(final_voids)

        # Coordination (count assist/support actions)
        # TODO: Implement coordination detection

        # Damage ratio (dealt / taken)
        # TODO: Extract from combat actions

        return metrics

    def evaluate(self, agent_config, output_file='benchmark_results.json'):
        """Run all scenarios and aggregate results."""
        results = []

        for scenario in self.scenarios:
            print(f"Running scenario: {scenario['name']}")
            metrics = self.run_scenario(scenario, agent_config)
            results.append({
                'scenario': scenario['name'],
                'category': scenario['category'],
                **metrics
            })

        # Aggregate by category
        df = pd.DataFrame(results)
        summary = df.groupby('category').mean()

        # Save results
        with open(output_file, 'w') as f:
            json.dump({
                'agent_config': agent_config,
                'scenarios': results,
                'summary': summary.to_dict()
            }, f, indent=2)

        return summary

if __name__ == '__main__':
    # Example: Evaluate GPT-4 agents
    agent_config = {
        'dm': {'llm': {'provider': 'openai', 'model': 'gpt-4'}},
        'players': [
            {'name': 'Test Player 1', 'llm': {'provider': 'openai', 'model': 'gpt-4'}},
            {'name': 'Test Player 2', 'llm': {'provider': 'openai', 'model': 'gpt-4'}}
        ]
    }

    benchmark = AeoniskBenchmark()
    results = benchmark.evaluate(agent_config)
    print(results)
```

## Leaderboard Website

**Simple static site (GitHub Pages):**

```html
<!-- index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Aeonisk Benchmark Leaderboard</title>
    <style>
        body { font-family: monospace; max-width: 1200px; margin: 0 auto; padding: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        .track-selector { margin: 20px 0; }
    </style>
</head>
<body>
    <h1>🎲 Aeonisk Multi-Agent Benchmark</h1>
    <p>Leaderboard for AI agents on graduated outcome multi-agent scenarios.</p>

    <div class="track-selector">
        <button onclick="showTrack('ethical')">Ethical Reasoning</button>
        <button onclick="showTrack('tactical')">Tactical Excellence</button>
        <button onclick="showTrack('narrative')">Narrative Quality</button>
        <button onclick="showTrack('efficiency')">Efficiency</button>
        <button onclick="showTrack('open')">Open Track</button>
    </div>

    <div id="ethical-track">
        <h2>Track 1: Ethical Reasoning</h2>
        <table>
            <tr>
                <th>Rank</th>
                <th>Team</th>
                <th>Model</th>
                <th>De-escalation Rate</th>
                <th>Avg Void</th>
                <th>Score</th>
            </tr>
            <!-- Populated from leaderboard.json -->
        </table>
    </div>

    <!-- More tracks... -->

    <h2>How to Submit</h2>
    <ol>
        <li>Clone the repo: <code>git clone https://github.com/ThreeRiversAINexus/aeonisk-yags</code></li>
        <li>Run benchmark: <code>python benchmarks/aeonisk_benchmark.py --config your_agents.json</code></li>
        <li>Submit results: Open PR with <code>results/your_team.json</code></li>
    </ol>
</body>
</html>
```

## Dataset Release

**HuggingFace Dataset:** `3RAIN/aeonisk-benchmark-v1`

**Structure:**
```
aeonisk-benchmark-v1/
├── README.md              # Datasheet (Gebru et al. format)
├── scenarios/
│   ├── combat_01.json
│   ├── combat_02.json
│   ├── ...
│   ├── social_01.json
│   └── mixed_10.json
├── baselines/
│   ├── gpt4_results.json
│   ├── claude_results.json
│   └── human_results.json  # If available
├── fixtures/
│   ├── session_combat_01.jsonl  # Full session logs
│   └── ...
└── metadata.json
```

**Datasheet sections:**
- Motivation (why this benchmark exists)
- Composition (50 scenarios, types, difficulty)
- Collection (how data was generated)
- Preprocessing (none, raw JSONL)
- Uses (intended research applications)
- Distribution (MIT license, HuggingFace)
- Maintenance (contact, versioning)

## Paper Structure (6-8 pages)

### Title
"Aeonisk: A Multi-Agent Benchmark with Graduated Outcomes for Studying AI Decision-Making Under Uncertainty"

### Abstract
We introduce Aeonisk, a multi-agent benchmark where every action receives graduated outcomes across 6 tiers rather than binary success/failure. This enables novel analysis of AI decision-making: counterfactual reasoning ("what if the roll was different?"), calibration (did agents estimate difficulty correctly?), and risk assessment (probability distributions). We provide 50 standardized scenarios, evaluation harness, and baseline results for GPT-4 and Claude. Our benchmark reveals that [key findings from baseline experiments].

### 1. Introduction
- Problem: Binary outcomes limit AI research
- Solution: Graduated outcomes + counterfactuals
- Contribution: Benchmark + dataset + evaluation tools

### 2. Related Work
- Existing benchmarks (NetHack, LIGHT, TextQuests, Diplomacy)
- Gap: All use binary/sparse outcomes
- Our contribution: Dense, graduated feedback

### 3. Benchmark Design
- Domain (TTRPG multi-agent)
- YAGS system (graduated outcomes)
- 50 scenarios across 5 categories
- Evaluation metrics (6 metrics)
- Leaderboard tracks (5 tracks)

### 4. Baseline Experiments
- GPT-4 agents
- Claude agents
- Comparison across metrics
- Key findings

### 5. Dataset & Tools
- HuggingFace release
- Evaluation harness
- Leaderboard website
- Submission process

### 6. Discussion
- What graduated outcomes enable
- Limitations (expensive, domain-specific)
- Future work (more scenarios, human baselines)

### 7. Conclusion
- Summary
- Call for submissions

## Target Venues

**Primary:** AAAI 2026 (Benchmark track)
**Backup:** NeurIPS 2025 Datasets & Benchmarks track
**Also:** IEEE CoG 2025 (game AI community)

## Next Steps (Next Month)

1. **Create 50 scenarios** (2 weeks)
   - 10 per category
   - Varying difficulty
   - Standardized format

2. **Build evaluation harness** (1 week)
   - Run scenarios
   - Extract metrics
   - Generate reports

3. **Run baselines** (1 week)
   - GPT-4 agents (10 sessions each)
   - Claude agents (10 sessions each)
   - Compare results

4. **Create leaderboard site** (3 days)
   - Simple GitHub Pages
   - Submit PR process
   - Auto-update from submissions

5. **Write datasheet** (3 days)
   - Follow Gebru et al. format
   - Document scenarios
   - Explain evaluation

6. **Release publicly** (1 day)
   - HuggingFace upload
   - GitHub release
   - Announce on r/ML, Twitter, LessWrong

---

**Key Takeaway:** This establishes Aeonisk as THE multi-agent benchmark with graduated outcomes. First-mover advantage is huge here.
