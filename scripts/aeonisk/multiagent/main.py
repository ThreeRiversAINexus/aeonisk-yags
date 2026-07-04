"""
Main entry point for the Aeonisk Multi-Agent Self-Playing System.
"""

import asyncio
import argparse
import json
import logging
import sys
import signal
from pathlib import Path
from dotenv import load_dotenv

from .session import SelfPlayingSession, EXAMPLE_CONFIG
from .launch_config import (
    LOG_LEVEL_CHOICES,
    effective_routing_report,
    validate_session_config,
)

# Load environment variables from .env file
load_dotenv()

# Initialize custom log levels (TRACE=5, LLM=15)
# This must happen before any logging configuration
from . import custom_log_levels  # noqa: F401


def setup_logging(level: str = "INFO"):
    """Set up logging configuration."""
    import sys

    # Shorter format: just time + level + message (saves tokens)
    console_format = '%(asctime)s %(levelname)-5s - %(message)s'
    date_format = '%H:%M:%S'

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(logging.Formatter(console_format, datefmt=date_format))

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,  # Root level DEBUG, handlers filter
        handlers=[console_handler]
    )

    # Set HTTP client loggers to LLM level (15)
    # This way they appear with --log-level LLM but not with --log-level DEBUG
    # Makes DEBUG useful for mechanics without HTTP spam
    http_loggers = [
        "httpcore",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpx",
        "urllib3",
        "urllib3.connectionpool",
        "requests",
        "openai",
        "openai._base_client",
        "anthropic",
        "anthropic._base_client",
    ]

    for logger_name in http_loggers:
        logging.getLogger(logger_name).setLevel(logging.LLM)

    # Suppress internal message bus noise (agent connect/disconnect spam)
    logging.getLogger("aeonisk.multiagent.base").setLevel(logging.WARNING)

    # Anthropic/OpenAI client logs now respect LLM level
    # Use --log-level LLM to see API details, --log-level DEBUG for mechanics only


def create_example_config(output_path: str):
    """Create an example configuration file."""
    try:
        with open(output_path, 'w') as f:
            json.dump(EXAMPLE_CONFIG, f, indent=2)
        print(f"Example configuration created at: {output_path}")
    except (OSError, PermissionError) as e:
        print(f"Failed to create configuration file: {e}")
        sys.exit(1)


def _load_config_data(config_path: str) -> dict:
    """Load a session config file (JSON or YAML) without side effects."""
    path = Path(config_path)
    with open(path, 'r') as f:
        if path.suffix in ('.yaml', '.yml'):
            import yaml
            return yaml.safe_load(f)
        return json.load(f)


async def run_session(config_path: str, random_seed: int = None, log_agents_separately: bool = False):
    """Run a self-playing session."""
    if not Path(config_path).exists():
        print(f"Configuration file not found: {config_path}")
        print("Use --create-config to generate an example configuration.")
        return None

    session = SelfPlayingSession(
        config_path,
        random_seed=random_seed,
        log_agents_separately=log_agents_separately
    )
    await session.start_session()
    return session


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Aeonisk Multi-Agent Self-Playing System"
    )
    
    parser.add_argument(
        'config',
        nargs='?',
        default='session_config.json',
        help='Path to session configuration file'
    )
    
    parser.add_argument(
        '--create-config',
        metavar='PATH',
        help='Create an example configuration file at the specified path'
    )
    
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=LOG_LEVEL_CHOICES,
        help='Set logging level (TRACE=ultra-verbose, DEBUG=detailed, LLM=API calls only, INFO=standard)'
    )

    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip session config preflight validation (not recommended)'
    )

    parser.add_argument(
        '--random-seed',
        type=int,
        help='Random seed for deterministic sessions (for testing and replay)'
    )

    parser.add_argument(
        '--replay',
        metavar='LOGFILE',
        help='Replay a session from JSONL log file'
    )

    parser.add_argument(
        '--replay-to-round',
        type=int,
        default=999,
        help='Stop replay after this round (default: replay entire session)'
    )

    parser.add_argument(
        '--continue-from-round',
        type=int,
        help='Replay rounds 1-N with cached responses, then continue LIVE from round N+1 onwards (hybrid mode)'
    )

    parser.add_argument(
        '--log-agents-separately',
        action='store_true',
        help='Log full LLM prompts and responses to separate human-readable files per agent (agent_logs/{session_id}/player_01.log, etc.)'
    )

    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log_level)
    
    # Create example config if requested
    if args.create_config:
        create_example_config(args.create_config)
        return

    # Replay mode
    if args.replay:
        from .replay import replay_from_log
        print("=== Aeonisk Session Replay ===")
        print(f"Log file: {args.replay}")
        if args.continue_from_round:
            print(f"Continue from round: {args.continue_from_round} (hybrid mode)")
        else:
            print(f"Replay to round: {args.replay_to_round}")
        print()
        result = asyncio.run(replay_from_log(
            args.replay,
            args.replay_to_round,
            continue_from_round=args.continue_from_round,
            execute=True
        ))
        if result:
            print(f"\nReplay completed: {result.get('status', 'unknown')}")
        return

    # Preflight: validate config and show effective LLM routing before
    # any agent starts, so misrouted strategies are visible immediately.
    if Path(args.config).exists():
        try:
            config_data = _load_config_data(args.config)
        except Exception as e:
            print(f"Failed to parse configuration {args.config}: {e}")
            sys.exit(1)

        if not args.skip_validation:
            errors = validate_session_config(config_data, path=args.config)
            if errors:
                print(f"Configuration failed validation "
                      f"({len(errors)} error(s)):")
                for err in errors:
                    print(f"  ✗ {err}")
                print("Use --skip-validation to run anyway.")
                sys.exit(1)

        print("Effective LLM routing:")
        for line in effective_routing_report(config_data):
            print(line)
        print()

    # Run session
    print("=== Aeonisk Multi-Agent Self-Playing System ===")
    print(f"Configuration: {args.config}")
    if args.random_seed:
        print(f"Using random seed: {args.random_seed}")
    if args.log_agents_separately:
        print("Agent prompt logging enabled: agent_logs/{session_id}/*.log")
    print("Starting session...")
    print("Press Ctrl+C to stop\n")

    # Track session for signal handler
    session_holder = {'session': None, 'log_agents_separately': args.log_agents_separately}

    def handle_interrupt(signum, frame):
        """Handle Ctrl-C by logging termination and printing session info."""
        print("\n\n=== Session interrupted by user ===", file=sys.stderr, flush=True)
        session = session_holder.get('session')
        if session and hasattr(session, 'session_id') and session.session_id:
            try:
                # Log termination to JSONL
                if (session.shared_state and
                    session.shared_state.mechanics_engine and
                    hasattr(session.shared_state.mechanics_engine, 'jsonl_logger') and
                    session.shared_state.mechanics_engine.jsonl_logger):
                    session.shared_state.mechanics_engine.jsonl_logger.log_session_termination(
                        reason="interrupted",
                        details="User pressed Ctrl+C"
                    )

                output_dir = session.config.get('output_dir', './output')
                jsonl_path = f"{output_dir}/session_{session.session_id}.jsonl"
                print(f"\nSession ID: {session.session_id}", file=sys.stderr, flush=True)
                print(f"JSONL log: {jsonl_path}", file=sys.stderr, flush=True)
                if session_holder['log_agents_separately']:
                    print(f"Agent logs: agent_logs/{session.session_id}/", file=sys.stderr, flush=True)
                print("", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"Error getting session info: {e}", file=sys.stderr, flush=True)
        else:
            print("(Session not yet initialized)", file=sys.stderr, flush=True)
        # Restore default handler and re-raise to trigger normal shutdown
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        raise KeyboardInterrupt()

    # Install signal handler
    signal.signal(signal.SIGINT, handle_interrupt)

    async def run_with_tracking():
        """Wrapper to track session object for signal handler."""
        if not Path(args.config).exists():
            print(f"Configuration file not found: {args.config}")
            print("Use --create-config to generate an example configuration.")
            return None

        session = SelfPlayingSession(
            args.config,
            random_seed=args.random_seed,
            log_agents_separately=args.log_agents_separately
        )
        # Track session immediately so signal handler can access it
        session_holder['session'] = session
        await session.start_session()
        return session

    try:
        asyncio.run(run_with_tracking())
    except KeyboardInterrupt:
        # Session info already printed by signal handler
        pass
    except Exception as e:
        # Log crash to JSONL before re-raising
        print(f"\n\n=== Session crashed ===", file=sys.stderr, flush=True)
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        session = session_holder.get('session')
        if session and hasattr(session, 'session_id') and session.session_id:
            try:
                if (session.shared_state and
                    session.shared_state.mechanics_engine and
                    hasattr(session.shared_state.mechanics_engine, 'jsonl_logger') and
                    session.shared_state.mechanics_engine.jsonl_logger):
                    session.shared_state.mechanics_engine.jsonl_logger.log_session_termination(
                        reason="crashed",
                        details=f"{type(e).__name__}: {e}"
                    )
            except Exception:
                pass  # Don't mask the original error
        raise


if __name__ == "__main__":
    main()