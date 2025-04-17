# Aeonisk YAGS Game

A text-based RPG game set in the Aeonisk universe, using the YAGS (Yet Another Game System) ruleset.

## Overview

Aeonisk YAGS is a command-line RPG game that combines narrative storytelling with the YAGS rule system. The game features:

- Character creation and management
- Scenario generation using AI
- NPC generation and interaction
- Natural language action processing
- Automatic skill checks
- Session saving and loading

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/aeonisk-yags.git
cd aeonisk-yags
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your OpenAI API key in a `.env` file:
```
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o  # or another model of your choice
```

## Running the Game

To start the game, run:

```bash
python scripts/aeonisk_game.py
```

## CLI Specification

The game uses an enhanced CLI interface with clear separation between narrative and mechanical elements.

### Command Structure

#### Core Commands
- `start <name>` - Start a new game with a name
- `load <name>` - Load a saved game
- `help` - Show help information
- `exit/quit` - Exit the game

#### Character Commands
- `create <name> <concept>` - Create a new character
- `list` - List all characters
- `select <index>` - Select a character
- `character` - View character details

#### Game Actions
- `look/examine [object]` - Look around or examine something
- `talk <npc> [message]` - Talk to an NPC
- `do <action>` - Perform an action
- `go <location>` - Move to a location
- `use <item> [on <target>]` - Use an item, possibly on a target

#### Advanced Commands
- `check <attr> <skill> <diff>` - Perform a manual skill check
- `scenario [theme] [difficulty]` - Generate a scenario
- `npc [faction] [role]` - Generate an NPC
- `save <file>` - Save the current session
- `mechanics` - Toggle display of mechanical details

### Output Format

The game output is structured with clear separation between narrative and mechanical elements:

```
[NARRATIVE]
The dimly lit marketplace bustles with activity as you navigate through the crowd. 
The merchant's eyes widen slightly as you approach, recognition flickering across 
his face.

[MECHANICS]
• Perception + Awareness check: 3×2 + 15 = 21 vs difficulty 18 (SUCCESS)
• Success margin: +3
• Void Score: 0 (unchanged)
• Soulcredit: 0 (unchanged)

[Dataset entry recorded]
```

This format provides:
1. A narrative description of what happens
2. The mechanical details (skill checks, stats changes)
3. Confirmation that the action was recorded in the dataset

### Natural Language Actions

The game accepts natural language commands for actions. If a command doesn't match any of the predefined commands, it's treated as an action and processed accordingly.

For example:
- `look around the marketplace`
- `talk to the merchant about rare artifacts`
- `carefully examine the strange device`
- `sneak past the guards`

The system will automatically determine the appropriate skill checks based on the action description and context.

## Architecture

The game is built with a modular architecture:

- `scripts/aeonisk/core/models.py` - Pydantic models for game entities
- `scripts/aeonisk/engine/game.py` - Core game mechanics
- `scripts/aeonisk/engine/cli.py` - Command-line interface
- `scripts/aeonisk/openai/client.py` - OpenAI API integration
- `scripts/aeonisk/dataset/parser.py` - Dataset parsing and management

## Dataset Integration

The game automatically records all actions, skill checks, and outcomes in a structured dataset format. This data can be used for:

- Session continuity
- Game analysis
- AI training
- Character progression tracking

## License

[MIT License](LICENSE)
