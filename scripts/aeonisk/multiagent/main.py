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
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('multiagent.log')
        ]
    )

    # Suppress spammy loggers for cleaner narrative output
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aeonisk.multiagent.base").setLevel(logging.WARNING)


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