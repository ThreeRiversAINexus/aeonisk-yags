# Aeonisk YAGS Engine

A comprehensive toolkit for building datasets, training models, and evaluating language model performance on Aeonisk YAGS tabletop RPG gameplay tasks. This engine provides everything needed to benchmark, develop, and deploy AI-powered game masters and assistants for the Aeonisk RPG setting.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Module Documentation](#module-documentation)
  - [Benchmark System](#benchmark-system)
  - [Dataset Management](#dataset-management)
  - [Game Engine](#game-engine)
  - [OpenAI Integration](#openai-integration)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Overview

The Aeonisk YAGS engine consists of four main modules:

1. **benchmark/**: Language model benchmarking and evaluation system
2. **dataset/**: Dataset parsing, validation, and management tools
3. **engine/**: Interactive game engine with CLI interface
4. **openai/**: OpenAI API integration for content generation

### Key Features

- **Multi-Model Benchmarking**: Compare OpenAI, Anthropic, and local models
- **Automated Evaluation**: AI-powered judging across multiple dimensions
- **Interactive Game Engine**: CLI-based game master interface
- **Dataset Management**: YAML-based dataset parsing and validation
- **Content Generation**: Scenario, NPC, and action analysis generation
- **Comprehensive Testing**: 400+ unit tests with mocked API calls
- **Modern Task Runner**: Uses Task instead of Make for cleaner build automation

## Installation

### Prerequisites

- Python 3.8 or higher
- API keys for cloud providers (optional but recommended)
- Git for version control

### Basic Installation

```bash
# Clone the repository
git clone <repository-url>
cd aeonisk-yags

# Install dependencies
pip install -r scripts/aeonisk/benchmark/requirements.txt

# Set up environment variables
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
```

### Development Installation

```bash
# Install Task (modern alternative to Make)
curl -sL https://taskfile.dev/install.sh | sh

# Alternative installation methods:
# brew install go-task/tap/go-task (macOS)
# choco install go-task (Windows)
# snap install task --classic (Linux)

# Note: The installer places task in ./bin/task
# You can add it to PATH or use ./bin/task directly

# Install additional development dependencies
pip install pytest pytest-asyncio black isort mypy

# Install in development mode
pip install -e .

# Quick development setup
task setup-dev
```

### Docker Installation (Optional)

```bash
# Build Docker image
docker build -t aeonisk-engine .

# Run with environment variables
docker run -e OPENAI_API_KEY="your-key" aeonisk-engine
```

## Quick Start

### Using Task (Recommended)

First, install Task if you haven't already:

```bash
# Install Task
curl -sL https://taskfile.dev/install.sh | sh

# Show all available commands
task --list

# Quick setup for development
task setup-dev
```

### 1. Benchmark Language Models

```bash
# Quick benchmark with default settings
task benchmark-quick

# Full benchmark suite
task benchmark-full

# Manual benchmark configuration
python -m aeonisk.benchmark.cli --create-config benchmark_config.json
python -m aeonisk.benchmark.cli --config benchmark_config.json --suite
```

### 2. Manage Datasets

```bash
# Validate sample datasets
task dataset-validate

# Manual dataset operations
python -m aeonisk.dataset.cli parse datasets/sample.txt -o parsed_dataset.json
python -m aeonisk.dataset.cli validate datasets/sample.txt -v
python -m aeonisk.dataset.cli convert datasets/sample.txt output.yaml -f yaml
```

### 3. Run Interactive Game Engine

```bash
# Start the game engine
task engine-cli

# Test with example session
task example-session
```

### 4. Run Tests

```bash
# Run all tests
task test

# Run specific test suites
task test-benchmark
task test-dataset
task test-engine
task test-openai

# Run tests with coverage
task test-coverage

# Quick test (no coverage)
task test-fast
```

### 5. Test OpenAI Integration

```bash
# Test OpenAI setup
task openai-test

# Programmatic usage
python -c "
from aeonisk.openai import generate_scenario, generate_npc, analyze_player_action

# Generate a scenario
scenario = generate_scenario(theme='cyberpunk', difficulty='moderate')

# Generate an NPC
npc = generate_npc(faction='corporate', role='security_chief')

# Analyze a player action
character = {'name': 'Hacker', 'concept': 'Digital infiltrator'}
analysis = analyze_player_action(character, 'hack the security system')
"
```

## Module Documentation

### Benchmark System

The benchmark system evaluates language models on Aeonisk YAGS gameplay tasks.

#### Core Components

- **BenchmarkRunner**: Main orchestration class
- **ModelManager**: Handles multiple LLM providers
- **AIJudge**: GPT-4 powered evaluation system
- **DatasetLoader**: Loads and filters benchmark tasks
- **ReportGenerator**: Creates comprehensive analysis reports

#### Configuration Example

```json
{
  "name": "aeonisk_benchmark",
  "description": "Comprehensive Aeonisk YAGS model evaluation",
  "dataset_path": "datasets/aeonisk_dataset_normalized_complete.txt",
  "models": [
    {
      "id": "gpt4",
      "provider": "openai",
      "model": "gpt-4",
      "api_key": "${OPENAI_API_KEY}",
      "timeout": 30
    },
    {
      "id": "claude",
      "provider": "anthropic", 
      "model": "claude-3-sonnet-20240229",
      "api_key": "${ANTHROPIC_API_KEY}",
      "timeout": 30
    }
  ],
  "use_ai_judge": true,
  "sample_size": 50,
  "generate_whitepaper": true
}
```

#### CLI Commands

```bash
# Create sample configuration
python -m aeonisk.benchmark.cli --create-config config.json

# Run single benchmark
python -m aeonisk.benchmark.cli --config config.json

# Run benchmark suite with multiple configurations
python -m aeonisk.benchmark.cli --config config.json --suite

# Run with custom output directory
python -m aeonisk.benchmark.cli --config config.json --output results/

# Enable verbose logging
python -m aeonisk.benchmark.cli --config config.json --verbose
```

#### Programmatic Usage

```python
from aeonisk.benchmark import BenchmarkRunner, BenchmarkConfig

# Create configuration
config = BenchmarkConfig(
    name="custom_benchmark",
    dataset_path="datasets/sample.txt",
    models=[{
        "provider": "openai",
        "model": "gpt-4",
        "api_key": "your-key"
    }],
    sample_size=25
)

# Run benchmark
runner = BenchmarkRunner(config)
results = await runner.run_benchmark()

# Access results
print(f"Top model: {list(results.model_rankings.keys())[0]}")
for model, rank in results.model_rankings.items():
    print(f"{model}: Rank {rank}")
```

### Dataset Management

The dataset system handles parsing, validation, and management of YAGS task datasets.

#### Dataset Format

Datasets use YAML format with the following structure:

```yaml
---
task_id: YAGS-AEONISK-001
domain:
  core: rule_application
  subdomain: skill_check_athletics
scenario: >
  Character attempts a challenging athletic maneuver while under pressure...
environment: Dangerous terrain with time constraints
stakes: >
  Success allows escape from pursuing enemies, failure results in injury...
characters:
  - name: Character Name
    attributes: {strength: 4, agility: 3, health: 3}
    skills: {athletics: 3, stealth: 2}
    void_score: 1
    soulcredit: 0
goal: >
  Determine appropriate YAGS mechanics and narrative outcomes...
expected_fields:
  - attribute_used
  - skill_used
  - roll_formula
  - difficulty_guess
  - outcome_explanation
gold_answer:
  attribute_used: Agility
  skill_used: Athletics
  roll_formula: "Agility 3 x Athletics 3 = 9; 9 + d20"
  difficulty_guess: 20
  outcome_explanation:
    critical_success:
      narrative: "Exceptional athletic performance..."
      mechanical_effect: "No injury, bonus progress"
    success:
      narrative: "Successful maneuver..."
      mechanical_effect: "Objective achieved"
    failure:
      narrative: "Stumbles but recovers..."
      mechanical_effect: "Minor setback"
    critical_failure:
      narrative: "Catastrophic failure..."
      mechanical_effect: "Injury and major setback"
```

#### CLI Commands

```bash
# Parse dataset to JSON
python -m aeonisk.dataset.cli parse input.txt -o output.json

# Validate dataset with detailed errors
python -m aeonisk.dataset.cli validate input.txt --verbose

# Convert between formats
python -m aeonisk.dataset.cli convert input.txt output.yaml --format yaml

# Batch operations
find datasets/ -name "*.txt" -exec python -m aeonisk.dataset.cli validate {} \;
```

#### Programmatic Usage

```python
from aeonisk.dataset import DatasetParser, DatasetManager

# Parse dataset
parser = DatasetParser()
tasks = parser.parse_file("dataset.txt")

# Validate dataset
validation_result = parser.validate(tasks)
if not validation_result.is_valid:
    for error in validation_result.errors:
        print(f"Error: {error}")

# Dataset management
manager = DatasetManager()
dataset1 = manager.load_dataset("dataset1.txt")
dataset2 = manager.load_dataset("dataset2.txt")

# Merge datasets
merged = manager.merge_datasets([dataset1, dataset2])
manager.save_dataset(merged, "merged_dataset.txt")

# Get statistics
stats = manager.get_task_statistics(merged)
print(f"Total tasks: {stats['total_tasks']}")
print(f"Domains: {stats['domains']}")
```

### Game Engine

The game engine provides an interactive CLI for running Aeonisk YAGS games.

#### Key Features

- Interactive character creation and management
- Automated skill check resolution
- AI-powered scenario and NPC generation
- Session save/load functionality
- Narrative/mechanics display toggle
- Dataset recording for training data

#### CLI Commands

```bash
# Start the game engine
python -m aeonisk.engine.cli

# Game commands (within the engine):
help                           # Show all commands
start <name>                   # Start new game
create <name> <concept>        # Create character
list                          # List characters
select <index>                # Select character
character                     # Show character details
check <attr> <skill> <diff>   # Manual skill check
scenario [theme] [difficulty] # Generate scenario
npc [faction] [role]          # Generate NPC
look [target]                 # Look around/examine
talk <npc> [message]          # Talk to NPC
do <action>                   # Perform action
go <location>                 # Move to location
use <item> [on <target>]      # Use item
save <file>                   # Save session
load <file>                   # Load session
mechanics                     # Toggle mechanics display
exit/quit                     # Exit game
```

#### Example Session

```
> start cyberpunk_campaign
Started a new game: cyberpunk_campaign

> create Alice "Digital Infiltrator"
Created character: Alice (Digital Infiltrator)

> scenario cyberpunk moderate
Generating scenario with theme: cyberpunk and difficulty: moderate...

[SCENARIO]
Theme: Cyberpunk
Difficulty: Moderate
Setting: Neo-Tokyo Corporate District

Objective: Infiltrate MegaCorp tower to retrieve stolen data

> do hack the security terminal
Performing action: hack the security terminal...

[NARRATIVE]
Alice interfaces with the terminal, her neural implants glowing as she navigates the digital defenses...

[MECHANICS]
• Intelligence + Hacking check: 4×5 + 16 = 36 vs difficulty 24 (SUCCESS)
• Success margin: +12
• Void Score: 0 (unchanged)
• Soulcredit: 1 (+1)

[Dataset entry recorded]

> save cyberpunk_session.json
Session saved to cyberpunk_session.json
```

#### Programmatic Usage

```python
from aeonisk.engine.game import GameSession

# Create session
session = GameSession()

# Create character
character = session.create_character("Hacker", "Digital infiltrator")

# Perform skill check
success, margin, description = session.skill_check(
    character, "Intelligence", "Hacking", 20
)

# Generate content
scenario = session.generate_scenario(theme="cyberpunk")
npc = session.generate_npc(faction="corporate", role="security")

# Process player action
result = session.process_player_action(character, "hack the mainframe")

# Save session
session.save_session("session.json")
```

### OpenAI Integration

The OpenAI module provides seamless integration with OpenAI's API for content generation.

#### Configuration

```python
# Environment variable (recommended)
export OPENAI_API_KEY="your-openai-key"

# Or programmatic initialization
from aeonisk.openai.client import OpenAIClient

client = OpenAIClient(
    api_key="your-key",
    model="gpt-4",
    api_url="https://api.openai.com/v1"  # Optional custom endpoint
)
```

#### Content Generation

```python
from aeonisk.openai import generate_scenario, generate_npc, analyze_player_action

# Generate scenario
scenario = generate_scenario(
    theme="mystery",
    difficulty="challenging",
    setting="Victorian London",
    characters=[
        {"name": "Detective Holmes", "concept": "Brilliant investigator"},
        {"name": "Dr. Watson", "concept": "Loyal companion"}
    ]
)

# Generate NPC
npc = generate_npc(
    faction="Scotland Yard",
    role="Inspector",
    importance="major"
)

# Analyze player action
character = {
    "name": "Holmes",
    "concept": "Master Detective",
    "attributes": {"Intelligence": 5, "Perception": 4},
    "skills": {"Investigation": 6, "Deduction": 5},
    "void_score": 0,
    "soulcredit": 3
}

analysis = analyze_player_action(
    character=character,
    action_text="examine the crime scene for clues",
    scenario=scenario,
    previous_actions=[]
)

# Format response
from aeonisk.openai.client import format_game_response

formatted = format_game_response(
    action_result=analysis,
    character=character,
    include_mechanics=True
)
print(formatted)
```

#### Custom Client Usage

```python
from aeonisk.openai.client import OpenAIClient

client = OpenAIClient(api_key="your-key")

# Basic text generation
response = client.generate_text(
    prompt="Describe a cyberpunk street scene",
    system_message="You are a creative sci-fi writer",
    temperature=0.8,
    max_tokens=500
)

# Advanced scenario generation
scenario = client.generate_scenario(
    theme="space opera",
    difficulty="epic",
    setting="Galactic Empire",
    characters=[{"name": "Captain Rex", "concept": "Rebel pilot"}]
)
```

## Configuration

### Environment Variables

```bash
# Required for OpenAI integration
export OPENAI_API_KEY="your-openai-api-key"

# Optional: Custom OpenAI endpoint
export OPENAI_API_URL="https://api.openai.com/v1"

# Optional: Default model
export OPENAI_MODEL="gpt-4"

# Required for Anthropic integration
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# Optional: Logging level
export AEONISK_LOG_LEVEL="INFO"
```

### Configuration Files

#### Benchmark Configuration (`benchmark_config.json`)

```json
{
  "name": "comprehensive_benchmark",
  "description": "Full evaluation of Aeonisk YAGS capabilities",
  "dataset_path": "datasets/aeonisk_dataset_normalized_complete.txt",
  "models": [
    {
      "id": "gpt4",
      "provider": "openai",
      "model": "gpt-4",
      "api_key": "${OPENAI_API_KEY}",
      "timeout": 30,
      "max_retries": 3
    },
    {
      "id": "gpt35_turbo",
      "provider": "openai",
      "model": "gpt-3.5-turbo",
      "api_key": "${OPENAI_API_KEY}",
      "timeout": 30,
      "max_retries": 3
    },
    {
      "id": "claude_sonnet",
      "provider": "anthropic",
      "model": "claude-3-sonnet-20240229",
      "api_key": "${ANTHROPIC_API_KEY}",
      "timeout": 30,
      "max_retries": 3
    },
    {
      "id": "local_llama",
      "provider": "local",
      "model": "llama2:13b",
      "base_url": "http://localhost:11434",
      "endpoint": "/api/generate",
      "timeout": 60
    }
  ],
  "use_ai_judge": true,
  "judge_model": "gpt-4",
  "evaluation_dimensions": [
    "mechanical_accuracy",
    "narrative_quality",
    "rules_adherence", 
    "consistency",
    "creativity",
    "difficulty_appropriate"
  ],
  "sample_size": null,
  "random_seed": 42,
  "filter_domains": null,
  "filter_difficulty": null,
  "max_concurrent_requests": 5,
  "timeout_seconds": 30,
  "retry_attempts": 3,
  "output_dir": "benchmark_results",
  "save_raw_responses": true,
  "generate_whitepaper": true
}
```

#### Dataset Configuration (`dataset_config.yaml`)

```yaml
# Dataset validation rules
validation:
  required_fields:
    - task_id
    - domain
    - scenario
    - environment
    - stakes
    - characters
    - goal
    - expected_fields
    - gold_answer
  
  domain_structure:
    core: [rule_application, combat, ritual_check, social_interaction]
    subdomain: [skill_check_athletics, melee_combat, void_ritual, persuasion]
  
  character_fields:
    required: [name]
    optional: [attributes, skills, void_score, soulcredit, bonds, equipment]

# Dataset processing options
processing:
  normalize_text: true
  validate_yaml: true
  check_duplicates: true
  generate_statistics: true

# Output formats
output:
  formats: [yaml, json]
  compression: false
  backup_originals: true
```

## Usage Examples

### Example 1: Quick Model Comparison

```bash
# Create a quick benchmark comparing GPT models
cat > quick_benchmark.json << EOF
{
  "name": "gpt_comparison",
  "dataset_path": "datasets/sample_tasks.txt", 
  "models": [
    {"id": "gpt4", "provider": "openai", "model": "gpt-4", "api_key": "${OPENAI_API_KEY}"},
    {"id": "gpt35", "provider": "openai", "model": "gpt-3.5-turbo", "api_key": "${OPENAI_API_KEY}"}
  ],
  "sample_size": 10,
  "use_ai_judge": true
}
EOF

python -m aeonisk.benchmark.cli --config quick_benchmark.json
```

### Example 2: Custom Game Session

```python
#!/usr/bin/env python3
"""Custom game session script."""

from aeonisk.engine.game import GameSession
from aeonisk.core.models import Character

def main():
    # Create session
    session = GameSession()
    
    # Create pre-made characters
    hacker = session.create_character("Zero", "Elite hacker")
    hacker.attributes["Intelligence"] = 5
    hacker.skills["Hacking"] = 6
    hacker.skills["Electronics"] = 4
    
    samurai = session.create_character("Katana", "Cybernetic warrior")
    samurai.attributes["Agility"] = 5 
    samurai.skills["Melee"] = 6
    samurai.skills["Athletics"] = 4
    
    # Generate cyberpunk scenario
    scenario = session.generate_scenario(
        theme="cyberpunk",
        difficulty="challenging"
    )
    
    print("=== CYBERPUNK CAMPAIGN ===")
    print(f"Scenario: {scenario.get('Scenario Overview', {}).get('Objective', 'Unknown')}")
    
    # Simulate some actions
    session.select_character(0)  # Select hacker
    
    # Hack attempt
    success, margin, desc = session.skill_check(hacker, "Intelligence", "Hacking", 22)
    print(f"\nHacking attempt: {'SUCCESS' if success else 'FAILURE'} (margin: {margin})")
    print(desc)
    
    # Save session
    session.save_session("cyberpunk_campaign.json")
    print("\nSession saved!")

if __name__ == "__main__":
    main()
```

### Example 3: Dataset Processing Pipeline

```python
#!/usr/bin/env python3
"""Dataset processing pipeline."""

from aeonisk.dataset import DatasetParser, DatasetManager
import glob
import os

def process_datasets():
    parser = DatasetParser()
    manager = DatasetManager()
    
    # Find all dataset files
    dataset_files = glob.glob("datasets/*.txt")
    
    all_datasets = []
    
    for file_path in dataset_files:
        print(f"Processing {file_path}...")
        
        try:
            # Parse dataset
            tasks = parser.parse_file(file_path)
            
            # Validate dataset
            validation = parser.validate(tasks)
            if not validation.is_valid:
                print(f"  ERRORS in {file_path}:")
                for error in validation.errors[:5]:  # Show first 5 errors
                    print(f"    - {error}")
                continue
            
            print(f"  ✓ Valid dataset with {len(tasks)} tasks")
            all_datasets.append(tasks)
            
        except Exception as e:
            print(f"  ✗ Failed to process {file_path}: {e}")
    
    if all_datasets:
        # Merge all valid datasets
        merged = manager.merge_datasets(all_datasets)
        
        # Save merged dataset
        output_file = "datasets/merged_dataset.txt"
        manager.save_dataset(merged, output_file)
        
        # Generate statistics
        stats = manager.get_task_statistics(merged)
        
        print(f"\n=== FINAL STATISTICS ===")
        print(f"Total tasks: {stats['total_tasks']}")
        print(f"Domains: {dict(stats['domains'])}")
        print(f"Output saved to: {output_file}")

if __name__ == "__main__":
    process_datasets()
```

### Example 4: Automated Scenario Generation

```python
#!/usr/bin/env python3
"""Automated scenario generation for campaign prep."""

from aeonisk.openai import generate_scenario, generate_npc
import json

def generate_campaign_content():
    """Generate a complete campaign starter pack."""
    
    themes = ["cyberpunk", "fantasy", "horror", "space_opera"]
    difficulties = ["easy", "moderate", "challenging", "epic"]
    
    campaign_content = {
        "scenarios": [],
        "npcs": [],
        "campaign_notes": ""
    }
    
    # Generate scenarios for each theme/difficulty combination
    for theme in themes:
        for difficulty in difficulties:
            print(f"Generating {theme} {difficulty} scenario...")
            
            scenario = generate_scenario(
                theme=theme,
                difficulty=difficulty,
                setting="Aeonisk"
            )
            
            if "error" not in scenario:
                campaign_content["scenarios"].append({
                    "theme": theme,
                    "difficulty": difficulty,
                    "content": scenario
                })
    
    # Generate diverse NPCs
    factions = ["Corporate", "Resistance", "Academic", "Criminal", "Government"]
    roles = ["Leader", "Specialist", "Enforcer", "Informant", "Wildcard"]
    
    for faction in factions:
        for role in roles:
            print(f"Generating {faction} {role}...")
            
            npc = generate_npc(
                faction=faction,
                role=role,
                importance="major"
            )
            
            if "error" not in npc:
                campaign_content["npcs"].append(npc)
    
    # Save campaign content
    with open("campaign_starter_pack.json", "w") as f:
        json.dump(campaign_content, f, indent=2)
    
    print(f"\n✓ Generated {len(campaign_content['scenarios'])} scenarios")
    print(f"✓ Generated {len(campaign_content['npcs'])} NPCs")
    print("✓ Campaign starter pack saved to campaign_starter_pack.json")

if __name__ == "__main__":
    generate_campaign_content()
```

## Testing

The engine includes a comprehensive test suite with over 400 unit tests covering all major functionality.

### Running Tests with Task

```bash
# Run all tests
task test

# Run specific test modules
task test-benchmark
task test-dataset
task test-engine
task test-openai

# Run tests with coverage
task test-coverage

# Run tests without coverage (faster)
task test-fast

# Run unit tests only
task test-unit

# Run integration tests only
task test-integration

# Clean up test artifacts
task clean
```

### Advanced Testing

```bash
# Run specific test classes (manual pytest)
python -m pytest test_benchmark.py::TestBenchmarkRunner -v

# Run tests in parallel
python -m pytest test_*.py -n auto

# Run with specific markers
python -m pytest -m "not slow" -v
```

### Test Organization

- **test_benchmark.py**: Benchmark system tests with mocked API calls
- **test_dataset.py**: Dataset parsing and validation tests
- **test_engine.py**: Game engine and CLI tests
- **test_openai_client.py**: OpenAI integration tests with mocked responses

### Mock Testing

All tests use mocked API calls to prevent real costs:

```python
@patch('aeonisk.benchmark.cli.load_config_file')
def test_generate_scenario(self, mock_load_config_file):
    # Mock OpenAI response
    mock_response = Mock()
    mock_response.choices[0].message.content = '{"test": "scenario"}'
    mock_load_config_file.return_value = mock_response
    
    # Test scenario generation
    client = OpenAIClient(api_key="test_key")
    result = client.generate_scenario(theme="test")
    
    # Verify results without making real API calls
    assert result == {"test": "scenario"}
    mock_load_config_file.assert_called_once()
```

### Continuous Integration

```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r scripts/aeonisk/benchmark/requirements.txt
        pip install pytest pytest-asyncio pytest-cov
    
    - name: Run tests
      run: |
        python -m pytest scripts/aeonisk/test_*.py -v --cov=aeonisk
```

## Troubleshooting

### Common Issues

#### API Key Errors

```bash
# Verify environment variables
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Test API connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models
```

**Solution**: Ensure API keys are properly set and have sufficient credits.

#### Dataset Loading Issues

```
Error: Dataset file not found: datasets/sample.txt
```

**Solutions**:
- Verify file path is correct
- Check file permissions
- Ensure file is valid YAML format
- Use absolute paths if needed

#### Memory/Performance Issues

```
Error: Request timeout after 30 seconds
```

**Solutions**:
- Increase timeout in configuration
- Reduce sample size for testing
- Use local models for development
- Implement request batching

#### Import Errors

```
ModuleNotFoundError: No module named 'aeonisk'
```

**Solutions**:
- Install in development mode: `pip install -e .`
- Add to Python path: `export PYTHONPATH="${PYTHONPATH}:$(pwd)"`
- Use absolute imports: `python -m aeonisk.benchmark.cli`

#### Local Model Connection

```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Check model availability
ollama list

# Pull required model
ollama pull llama2:7b
```

### Performance Optimization

#### Benchmark Performance

```json
{
  "max_concurrent_requests": 3,    // Reduce for rate limits
  "timeout_seconds": 60,          // Increase for slow models
  "retry_attempts": 5,            // Increase for reliability
  "sample_size": 25              // Reduce for faster testing
}
```

#### Memory Optimization

```python
# Process datasets in chunks
def process_large_dataset(file_path, chunk_size=100):
    parser = DatasetParser()
    tasks = parser.parse_file(file_path)
    
    for i in range(0, len(tasks), chunk_size):
        chunk = tasks[i:i+chunk_size]
        yield chunk
```

#### API Rate Limiting

```python
import asyncio
import aiohttp

# Custom rate limiter
async def rate_limited_request(session, url, delay=1.0):
    await asyncio.sleep(delay)
    async with session.get(url) as response:
        return await response.json()
```

### Debugging

#### Enable Verbose Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Or via environment
export AEONISK_LOG_LEVEL=DEBUG
```

#### Debug Configuration

```json
{
  "debug": {
    "save_all_responses": true,
    "include_timestamps": true,
    "validate_schemas": true,
    "trace_execution": true
  }
}
```

#### Common Debug Commands

```bash
# Test configuration validation
python -c "
from aeonisk.benchmark.cli import validate_config
import json
with open('config.json') as f:
    config = json.load(f)
errors = validate_config(config)
print('Errors:', errors)
"

# Test dataset parsing
python -c "
from aeonisk.dataset.parser import DatasetParser
parser = DatasetParser()
try:
    tasks = parser.parse_file('dataset.txt')
    print(f'Loaded {len(tasks)} tasks')
except Exception as e:
    print(f'Error: {e}')
"

# Test OpenAI connection
python -c "
from aeonisk.openai.client import OpenAIClient
try:
    client = OpenAIClient()
    result = client.generate_text('test')
    print('OpenAI connection successful')
except Exception as e:
    print(f'OpenAI error: {e}')
"
```

## Contributing

### Development Setup

```bash
# Clone repository
git clone <repository-url>
cd aeonisk-yags

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in development mode
pip install -e .
pip install -r scripts/aeonisk/benchmark/requirements.txt

# Install development tools
pip install black isort mypy pytest pytest-asyncio pytest-cov
```

### Code Standards

```bash
# Format code
black scripts/aeonisk/
isort scripts/aeonisk/

# Type checking
mypy scripts/aeonisk/

# Run tests
pytest scripts/aeonisk/test_*.py -v
```

### Adding New Features

1. **Follow test-driven development**:
   ```bash
   # Write tests first
   touch scripts/aeonisk/test_new_feature.py
   
   # Implement feature
   touch scripts/aeonisk/new_feature.py
   
   # Run tests
   pytest scripts/aeonisk/test_new_feature.py -v
   ```

2. **Document your changes**:
   - Add docstrings to all functions
   - Update README.md if needed
   - Add usage examples
   - Update type hints

3. **Create comprehensive tests**:
   - Unit tests for all functions
   - Integration tests for workflows
   - Mock external API calls
   - Test error conditions

4. **Follow existing patterns**:
   - Use Pydantic models for data validation
   - Use async/await for I/O operations
   - Use structured logging
   - Follow naming conventions

### Submitting Changes

1. Create feature branch: `git checkout -b feature/new-feature`
2. Make changes with tests
3. Run full test suite: `pytest scripts/aeonisk/test_*.py`
4. Update documentation
5. Submit pull request with description

### Architecture Guidelines

- **Modular design**: Each module should be independently testable
- **Clear interfaces**: Use Pydantic models for data validation
- **Error handling**: Graceful degradation with informative errors
- **Async support**: Use async/await for I/O operations
- **Configuration-driven**: Externalize settings in JSON/YAML
- **Comprehensive logging**: Structure logs for debugging

---

## License

This project is part of the Aeonisk YAGS toolkit and follows the same licensing terms as the parent project.

## Support

For issues and questions:
1. Check this documentation
2. Review existing tests for usage examples
3. Check the troubleshooting section
4. Run tests with `--verbose` flag
5. Submit issues with full context and logs

## Changelog

### Version 0.1.0
- Initial release with benchmark, dataset, engine, and OpenAI modules
- Comprehensive test suite with 400+ tests
- Full CLI interfaces for all modules
- Complete documentation and examples
- Support for OpenAI, Anthropic, and local models