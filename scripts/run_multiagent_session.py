#!/usr/bin/env python3
"""
Entry point for running Aeonisk multi-agent self-playing sessions.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aeonisk.multiagent.main import main

if __name__ == "__main__":
    main()