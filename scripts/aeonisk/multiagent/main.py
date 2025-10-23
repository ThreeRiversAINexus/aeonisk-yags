"""
Main entry point for the Aeonisk Multi-Agent Self-Playing System.
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

from .session import SelfPlayingSession, EXAMPLE_CONFIG

# Load environment variables from .env file
load_dotenv()


def setup_logging(level: str = "INFO"):
    """Set up logging configuration."""
    import sys

    # Shorter format: just time + level + message (saves tokens)
    console_format = '%(asctime)s %(levelname)-5s - %(message)s'
    file_format = '%(asctime)s %(levelname)-5s - %(message)s'
    date_format = '%H:%M:%S'

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(logging.Formatter(console_format, datefmt=date_format))

    # File handler (captures everything including print statements)
    file_handler = logging.FileHandler('multiagent.log')
    file_handler.setLevel(logging.DEBUG)  # Always capture everything to file
    file_handler.setFormatter(logging.Formatter(file_format, datefmt=date_format))

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG,  # Root level DEBUG, handlers filter
        handlers=[console_handler, file_handler]
    )

    # Redirect print() to also go to log file
    class PrintLogger:
        """Captures print() statements and sends them to log file."""
        def __init__(self, original_stdout, log_file):
            self.original_stdout = original_stdout
            self.log_file = log_file

        def write(self, message):
            # Write to original stdout (console)
            self.original_stdout.write(message)
            # Also write to log file (without logging formatting)
            if message.strip():  # Don't log empty lines
                self.log_file.write(message)
                self.log_file.flush()

        def flush(self):
            self.original_stdout.flush()
            self.log_file.flush()

    # Wrap stdout to capture print statements
    log_file = open('multiagent.log', 'a')
    sys.stdout = PrintLogger(sys.stdout, log_file)

    # Suppress spammy third-party loggers for cleaner output
    # Even at DEBUG level, we don't need HTTP connection internals
    logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Suppress internal message bus noise (agent connect/disconnect spam)
    logging.getLogger("aeonisk.multiagent.base").setLevel(logging.WARNING)

    # Keep anthropic client logs - shows actual prompts/responses at DEBUG
    # (No need to set explicitly, respects root level)


def create_example_config(output_path: str):
    """Create an example configuration file."""
    try:
        with open(output_path, 'w') as f:
            json.dump(EXAMPLE_CONFIG, f, indent=2)
        print(f"Example configuration created at: {output_path}")
    except (OSError, PermissionError) as e:
        print(f"Failed to create configuration file: {e}")
        sys.exit(1)


async def run_session(config_path: str):
    """Run a self-playing session."""
    if not Path(config_path).exists():
        print(f"Configuration file not found: {config_path}")
        print("Use --create-config to generate an example configuration.")
        return
        
    try:
        session = SelfPlayingSession(config_path)
        await session.start_session()
    except KeyboardInterrupt:
        print("\nSession interrupted by user")
    except Exception as e:
        logging.error(f"Session error: {e}", exc_info=True)
        print(f"Session failed: {e}")


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
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set logging level (use DEBUG for detailed ChromaDB visibility)'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log_level)
    
    # Create example config if requested
    if args.create_config:
        create_example_config(args.create_config)
        return
    
    # Run session
    print("=== Aeonisk Multi-Agent Self-Playing System ===")
    print(f"Configuration: {args.config}")
    print("Starting session...")
    print("Press Ctrl+C to stop\n")
    
    asyncio.run(run_session(args.config))


if __name__ == "__main__":
    main()