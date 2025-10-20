#!/usr/bin/env python3
"""
Entry point for running Aeonisk multi-agent self-playing sessions.
"""

import sys
import os
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file in the aeonisk directory
dotenv_path = os.path.join(os.path.dirname(__file__), 'aeonisk', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"Loaded environment from: {dotenv_path}")
else:
    # Try loading from default .env location
    load_dotenv()
    print("Loaded environment from default .env location")

from aeonisk.multiagent.main import main

if __name__ == "__main__":
    main()