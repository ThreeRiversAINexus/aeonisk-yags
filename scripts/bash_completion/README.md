# Shell Completion Scripts for Aeonisk YAGS

Tab completion for the main CLI tools:
- `run_multiagent_session.py` - Run multi-agent sessions
- `analyze_session.py` - Analyze JSONL session logs
- `bulk_session_runner.py` - Bulk session orchestration

## Bash Installation

### Option 1: Source in current shell (temporary)
```bash
source scripts/bash_completion/aeonisk_completions.bash
```

### Option 2: Add to ~/.bashrc (permanent)
```bash
echo 'source /path/to/aeonisk-yags/scripts/bash_completion/aeonisk_completions.bash' >> ~/.bashrc
source ~/.bashrc
```

### Option 3: System-wide (Linux)
```bash
sudo cp scripts/bash_completion/aeonisk_completions.bash /etc/bash_completion.d/aeonisk
```

## Zsh Installation

### Step 1: Create completions directory
```bash
mkdir -p ~/.zsh/completions
```

### Step 2: Copy completion file
```bash
cp scripts/bash_completion/_aeonisk ~/.zsh/completions/_aeonisk
```

### Step 3: Add to ~/.zshrc
```bash
# Add these lines to ~/.zshrc
fpath=(~/.zsh/completions $fpath)
autoload -Uz compinit && compinit
```

### Step 4: Reload
```bash
source ~/.zshrc
# Or restart your terminal
```

## Usage Examples

```bash
# Config file completion
python scripts/run_multiagent_session.py scripts/session_configs/<TAB>

# Option completion
python scripts/run_multiagent_session.py --<TAB>
python scripts/run_multiagent_session.py --log-level <TAB>

# JSONL file completion
python scripts/analyze_session.py multiagent_output/<TAB>
python scripts/analyze_session.py --mode <TAB>

# Search pattern completion
python scripts/analyze_session.py session.jsonl --search event_type=<TAB>

# Bulk runner completion
python scripts/bulk_session_runner.py --config <TAB>
python scripts/bulk_session_runner.py --workers <TAB>
python scripts/bulk_session_runner.py --run-dir bulk_output/<TAB>
```

## What's Completed

### run_multiagent_session.py
- Config file paths (auto-discovers from `scripts/session_configs/`)
- `--log-level`: TRACE, DEBUG, LLM, INFO, WARNING, ERROR
- `--replay`: JSONL files
- `--random-seed`, `--replay-to-round`, `--continue-from-round`: integers
- `--create-config`, `--log-agents-separately`: flags

### analyze_session.py
- JSONL file paths (auto-discovers from `multiagent_output/`, `tests/fixtures/`)
- `--mode`: summary, clocks, void, errors
- `--search`: common event type patterns
- `--fields`: common field combinations
- `--discover`: directory completion
- `--limit`, `--line`, `--min-rounds`: integers
- `--validate-fixture`, `--validate-fixtures`, `--count`, `--index`, `--schema`: flags

### bulk_session_runner.py
- `--config`, `--configs`: config file paths
- `--run-dir`: bulk run directories in `bulk_output/`
- `--output-dir`: directory completion
- `--log-level`: DEBUG, INFO, WARNING, ERROR, LLM, TRACE
- `--proxy`: common localhost URLs
- `--runs`, `--workers`, `--progress-interval`, `--session-timeout`: common integer values
- All boolean flags: `--resume`, `--no-replay`, `--progress`, `--show-errors`, etc.
