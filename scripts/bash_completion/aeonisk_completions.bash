#!/bin/bash
# Bash completion scripts for Aeonisk YAGS CLI tools
#
# Installation:
#   Option 1: Source directly in your shell:
#     source /path/to/aeonisk-yags/scripts/bash_completion/aeonisk_completions.bash
#
#   Option 2: Add to your ~/.bashrc:
#     source /path/to/aeonisk-yags/scripts/bash_completion/aeonisk_completions.bash
#
#   Option 3: System-wide (Linux):
#     sudo cp /path/to/aeonisk-yags/scripts/bash_completion/aeonisk_completions.bash /etc/bash_completion.d/aeonisk
#
# Usage:
#   python scripts/run_multiagent_session.py <TAB>
#   python scripts/analyze_session.py <TAB>
#   python scripts/bulk_session_runner.py <TAB>

# Helper: Find session config JSON files
_aeonisk_find_configs() {
    local dir="${1:-.}"
    find "$dir" -maxdepth 3 -name "*.json" -path "*/session_configs/*" 2>/dev/null
    find "$dir" -maxdepth 2 -name "session_config*.json" 2>/dev/null
}

# Helper: Find JSONL session files
_aeonisk_find_jsonl() {
    local dir="${1:-.}"
    find "$dir" -maxdepth 3 -name "session_*.jsonl" 2>/dev/null
    find "$dir" -maxdepth 2 -name "*.jsonl" 2>/dev/null
}

# Helper: Find bulk run directories
_aeonisk_find_run_dirs() {
    local dir="${1:-bulk_output}"
    find "$dir" -maxdepth 1 -type d -name "run_*" 2>/dev/null
}

# =============================================================================
# run_multiagent_session.py completion
# =============================================================================
_complete_run_multiagent_session() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Main options
    opts="--log-level --create-config --random-seed --replay --replay-to-round --continue-from-round --log-agents-separately -h --help"

    case "${prev}" in
        --log-level)
            COMPREPLY=( $(compgen -W "TRACE DEBUG LLM INFO WARNING ERROR" -- "${cur}") )
            return 0
            ;;
        --create-config)
            # File path completion
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
        --random-seed|--replay-to-round|--continue-from-round)
            # Integer - no completion, user types number
            return 0
            ;;
        --replay)
            # JSONL file completion
            local jsonl_files=$(_aeonisk_find_jsonl)
            COMPREPLY=( $(compgen -W "${jsonl_files}" -- "${cur}") )
            # Also allow standard file completion
            COMPREPLY+=( $(compgen -f -X '!*.jsonl' -- "${cur}") )
            return 0
            ;;
    esac

    # If current word starts with -, complete options
    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # Default: complete config files (positional argument)
    local config_files=$(_aeonisk_find_configs "scripts")
    COMPREPLY=( $(compgen -W "${config_files}" -- "${cur}") )
    # Also allow standard file completion for JSON files
    COMPREPLY+=( $(compgen -f -X '!*.json' -- "${cur}") )
    return 0
}

# =============================================================================
# analyze_session.py completion
# =============================================================================
_complete_analyze_session() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Main options
    opts="--mode --discover --complete-only --min-rounds --search --limit --fields --count --index --schema --line --validate-fixture --validate-fixtures -h --help"

    # Modes for --mode
    local modes="summary clocks void errors"

    case "${prev}" in
        --mode)
            COMPREPLY=( $(compgen -W "${modes}" -- "${cur}") )
            return 0
            ;;
        --discover)
            # Directory completion
            COMPREPLY=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --min-rounds|--limit|--line)
            # Integer - no completion
            return 0
            ;;
        --search)
            # Common search patterns
            local search_patterns="event_type=session_start event_type=session_end event_type=action_resolution event_type=action_declaration event_type=round_start event_type=round_synthesis event_type=enemy_spawn event_type=enemy_defeat event_type=character_state event_type=void_change event_type=clock_advancement event_type=clock_completion event_type=llm_call round=0 round=1 round=2 round=3"
            COMPREPLY=( $(compgen -W "${search_patterns}" -- "${cur}") )
            return 0
            ;;
        --fields)
            # Common field names
            local common_fields="round,agent,roll.success,roll.margin event_type,round,agent action.intent,action.action_type scenario.theme,scenario.location effects.void_changes,effects.damage.dealt"
            COMPREPLY=( $(compgen -W "${common_fields}" -- "${cur}") )
            return 0
            ;;
    esac

    # If current word starts with -, complete options
    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # Default: complete JSONL files (positional argument)
    local jsonl_files=$(_aeonisk_find_jsonl "multiagent_output")
    jsonl_files+=" "$(_aeonisk_find_jsonl "tests/fixtures")
    COMPREPLY=( $(compgen -W "${jsonl_files}" -- "${cur}") )
    # Also allow standard file completion for JSONL files
    COMPREPLY+=( $(compgen -f -X '!*.jsonl' -- "${cur}") )
    return 0
}

# =============================================================================
# bulk_session_runner.py completion
# =============================================================================
_complete_bulk_session_runner() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Main options
    opts="--config --configs --runs --runs-per-config --workers --output-dir --proxy --resume --no-replay --run-dir --log-level --skip-health-check --progress --progress-interval --show-errors --session-timeout --regenerate-fixtures --extract -h --help"

    # Log levels
    local log_levels="DEBUG INFO WARNING ERROR LLM TRACE"

    case "${prev}" in
        --config)
            # Single config file completion
            local config_files=$(_aeonisk_find_configs "scripts")
            COMPREPLY=( $(compgen -W "${config_files}" -- "${cur}") )
            COMPREPLY+=( $(compgen -f -X '!*.json' -- "${cur}") )
            return 0
            ;;
        --configs)
            # Multiple config files completion
            local config_files=$(_aeonisk_find_configs "scripts")
            COMPREPLY=( $(compgen -W "${config_files}" -- "${cur}") )
            COMPREPLY+=( $(compgen -f -X '!*.json' -- "${cur}") )
            return 0
            ;;
        --output-dir)
            # Directory completion
            COMPREPLY=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --run-dir)
            # Bulk run directory completion
            local run_dirs=$(_aeonisk_find_run_dirs)
            COMPREPLY=( $(compgen -W "${run_dirs}" -- "${cur}") )
            COMPREPLY+=( $(compgen -d -- "${cur}") )
            return 0
            ;;
        --log-level)
            COMPREPLY=( $(compgen -W "${log_levels}" -- "${cur}") )
            return 0
            ;;
        --proxy)
            # Common proxy URLs
            COMPREPLY=( $(compgen -W "http://localhost:8000 http://127.0.0.1:8000" -- "${cur}") )
            return 0
            ;;
        --runs|--runs-per-config|--workers|--progress-interval|--session-timeout)
            # Integer - suggest common values
            case "${prev}" in
                --runs|--runs-per-config)
                    COMPREPLY=( $(compgen -W "1 5 10 20 50 100" -- "${cur}") )
                    ;;
                --workers)
                    COMPREPLY=( $(compgen -W "1 2 4 8 10 16 20" -- "${cur}") )
                    ;;
                --progress-interval)
                    COMPREPLY=( $(compgen -W "5 10 15 30 60" -- "${cur}") )
                    ;;
                --session-timeout)
                    COMPREPLY=( $(compgen -W "3600 7200 36000 90000" -- "${cur}") )
                    ;;
            esac
            return 0
            ;;
    esac

    # If current word starts with -, complete options
    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # No positional arguments by default
    return 0
}

# =============================================================================
# Register completions
# =============================================================================

# Function to detect and complete based on which script is being called
_aeonisk_completion() {
    local script_name=""

    # Find which script is being run (look for the .py file in COMP_WORDS)
    for word in "${COMP_WORDS[@]}"; do
        case "$word" in
            *run_multiagent_session.py|*run_multiagent_session)
                script_name="run_multiagent_session"
                break
                ;;
            *analyze_session.py|*analyze_session)
                script_name="analyze_session"
                break
                ;;
            *bulk_session_runner.py|*bulk_session_runner)
                script_name="bulk_session_runner"
                break
                ;;
        esac
    done

    case "$script_name" in
        run_multiagent_session)
            _complete_run_multiagent_session
            ;;
        analyze_session)
            _complete_analyze_session
            ;;
        bulk_session_runner)
            _complete_bulk_session_runner
            ;;
        *)
            # Default file completion
            COMPREPLY=( $(compgen -f -- "${COMP_WORDS[COMP_CWORD]}") )
            ;;
    esac
}

# Register completions for python/python3 commands
# These work when running: python scripts/run_multiagent_session.py <TAB>
complete -F _aeonisk_completion python
complete -F _aeonisk_completion python3

# Also register direct completions if scripts are made executable and added to PATH
complete -F _complete_run_multiagent_session run_multiagent_session.py
complete -F _complete_run_multiagent_session run_multiagent_session
complete -F _complete_analyze_session analyze_session.py
complete -F _complete_analyze_session analyze_session
complete -F _complete_bulk_session_runner bulk_session_runner.py
complete -F _complete_bulk_session_runner bulk_session_runner

# Print confirmation when sourced
echo "Aeonisk YAGS bash completions loaded. Try:"
echo "  python scripts/run_multiagent_session.py <TAB>"
echo "  python scripts/analyze_session.py <TAB>"
echo "  python scripts/bulk_session_runner.py <TAB>"
