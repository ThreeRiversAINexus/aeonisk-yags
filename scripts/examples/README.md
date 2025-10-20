# Scripts Examples

This directory contains one-off utility scripts and experimental code that were used during development but are not part of the core infrastructure.

## Contents

### Cleanup Utilities
- `cleanup_backups.sh` - Remove backup files from the repository
- `cleanup_dev_files.sh` - Clean up development artifacts

### Demo/Test Scripts
- `demo.py` - Early demo of game mechanics
- `demo_player_system.py` - Player perspective system demo
- `run_player_perspective_demo.py` - Run player-focused gameplay scenarios
- `run_simple_multiagent.py` - Simplified multi-agent session runner
- `run_benchmark_example.py` - Benchmark testing for game engine

### YAGS Conversion Tools
- `convert_yagsbook.sh` - Convert YAGS XML books to markdown
- `debug_ast.lua` - Lua script for AST debugging
- `yags_tables.lua` - Lua table processing utilities
- `internal_podman_convert.sh` - Internal containerized conversion script

### Table Formatting Fixes
- `direct_table_fix.py` - Direct table format corrections
- `final_fixes.py` - Final formatting fixes for converted content
- `fix_duplicates.py` - Remove duplicate entries
- `fix_table_formatting.py` - Format table structures

## Active Infrastructure Scripts

The actively maintained infrastructure scripts remain in the parent `scripts/` directory:
- `start-services.sh` / `stop-services.sh` - Service lifecycle management
- `init-databases.sh` - Database initialization
- `check-prerequisites.sh` - Dependency verification
- `diagnose-connections.sh` - Connection troubleshooting
- `run_multiagent_session.py` - Multi-agent session orchestration (uses `aeonisk/multiagent/`)
- `run_tests.py` - Test runner
- `aeonisk_game.py` - Main game entry point
- `dataset_parser.py` - Dataset CLI entry point

## Python Toolkit

The core Python implementation is in `scripts/aeonisk/`:
- `engine/` - Game engine (character, actions, rules)
- `dataset/` - Dataset management and validation
- `multiagent/` - Multi-agent orchestration lab
- `benchmark/` - Performance benchmarking
- `llm/` - LLM provider integrations
- `rag/` - RAG system for content retrieval

## Usage

These example scripts are preserved for reference but may not work without modification. If you need similar functionality, check if it has been integrated into the main toolkit first.
