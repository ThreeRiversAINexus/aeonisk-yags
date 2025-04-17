# Aeonisk YAGS Toolkit

A toolkit for the Aeonisk RPG setting using the YAGS (Yet Another Game System).

## Overview

This toolkit provides tools for dataset management, game engine implementation, and OpenAI integration for playtesting the Aeonisk RPG. It includes:

- Dataset parsing and validation
- YAGS rule implementation
- OpenAI integration for generating game content
- Playtesting tools with interactive CLI

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aeonisk-yags.git
cd aeonisk-yags

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

## Configuration

Copy the `.env.example` file to `.env` and update the values:

```bash
cp .env.example .env
```

Edit the `.env` file with your OpenAI API key and other settings:

```
# OpenAI API configuration
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4
OPENAI_API_URL=https://api.openai.com/v1

# Application settings
DEBUG=False
LOG_LEVEL=INFO
```

## Usage

### Command-Line Tools

The toolkit provides several command-line tools:

#### Dataset Parser

```bash
# Parse and validate a dataset
./scripts/dataset_parser.py parse datasets/aeonisk-dataset-v1.0.1.txt

# Validate a dataset
./scripts/dataset_parser.py validate datasets/aeonisk-dataset-v1.0.1.txt

# Convert a dataset to JSON
./scripts/dataset_parser.py convert datasets/aeonisk-dataset-v1.0.1.txt output.json -f json
```

#### Game CLI

```bash
# Start the interactive game CLI
./scripts/aeonisk_game.py
```

The game CLI provides an interactive interface for playtesting the Aeonisk RPG. Type `help` to see available commands.

### Python API

#### Dataset Management

```python
from aeonisk.dataset.parser import DatasetParser

# Create a parser
parser = DatasetParser()

# Parse a dataset file
dataset = parser.parse_file('datasets/aeonisk-dataset-v1.0.1.txt')

# Validate a dataset
validation_result = parser.validate(dataset)

# Save a dataset
parser.save(dataset, 'path/to/output.txt')
```

#### Game Engine

```python
from aeonisk.engine.game import GameSession, Character

# Create a new game session
session = GameSession()

# Create a character
character = session.create_character('Elara Voss', 'Ex-military pilot turned smuggler')

# Perform a skill check
success, margin, description = session.skill_check(character, 'Agility', 'Athletics', difficulty=20)
print(description)

# Generate a scenario
scenario = session.generate_scenario(theme='cyberpunk', difficulty='moderate')

# Generate an NPC
npc = session.generate_npc(faction='Sovereign Nexus', role='enforcer')

# Process a player action
result = session.process_player_action(character, 'I attempt to hack into the security system')
```

#### OpenAI Integration

```python
from aeonisk.openai import client

# Generate a scenario
scenario = client.generate_scenario(theme='cyberpunk', difficulty='moderate')

# Generate an NPC
npc = client.generate_npc(faction='Sovereign Nexus', role='enforcer')

# Create a custom client with different settings
custom_client = client.OpenAIClient(
    model="gpt-3.5-turbo",
    api_url="https://custom.openai.com/v1"
)
```

## Development

### Running Tests

```bash
# Run all tests
./scripts/run_tests.py

# Run unit tests only
./scripts/run_tests.py -u

# Run with coverage
./scripts/run_tests.py -c

# Run specific tests
./scripts/run_tests.py -k "dataset"
```

### Code Style

This project uses Black for code formatting and Flake8 for linting:

```bash
# Format code
black scripts tests

# Check imports
isort scripts tests

# Lint code
flake8 scripts tests
```

## Project Structure

```
aeonisk-yags/
├── datasets/                # Sample datasets
├── scripts/                 # Python package and scripts
│   ├── aeonisk/             # Main package
│   │   ├── core/            # Core functionality
│   │   ├── dataset/         # Dataset parsing and validation
│   │   ├── engine/          # Game engine implementation
│   │   ├── openai/          # OpenAI integration
│   │   └── utils/           # Utility functions
│   ├── aeonisk_game.py      # Game CLI entry point
│   ├── dataset_parser.py    # Dataset parser entry point
│   └── run_tests.py         # Test runner script
├── tests/                   # Test suite
│   ├── unit/                # Unit tests
│   └── integration/         # Integration tests
├── yagsbook/                # YAGS DocBook submodule
├── .env.example             # Example environment variables
├── requirements.txt         # Dependencies
├── setup.py                 # Package setup script
└── README.md                # This file
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
