#!/usr/bin/env python3
"""
Script to run the test suite for the Aeonisk YAGS toolkit.
"""

import argparse
import os
import sys
import subprocess


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run tests for the Aeonisk YAGS toolkit",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "-u", "--unit",
        action="store_true",
        help="Run unit tests only"
    )
    
    parser.add_argument(
        "-i", "--integration",
        action="store_true",
        help="Run integration tests only"
    )
    
    parser.add_argument(
        "-c", "--coverage",
        action="store_true",
        help="Run tests with coverage"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Run tests in verbose mode"
    )
    
    parser.add_argument(
        "-k", "--keyword",
        help="Only run tests that match the given keyword expression"
    )
    
    parser.add_argument(
        "test_path",
        nargs="?",
        help="Path to a specific test file or directory"
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the script."""
    args = parse_args()
    
    # Build the pytest command
    cmd = ["pytest"]
    
    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    
    # Add coverage
    if args.coverage:
        cmd.append("--cov=scripts/aeonisk")
        cmd.append("--cov-report=term")
        cmd.append("--cov-report=html")
    
    # Add keyword filter
    if args.keyword:
        cmd.append(f"-k {args.keyword}")
    
    # Add test path
    if args.test_path:
        cmd.append(args.test_path)
    elif args.unit:
        cmd.append("tests/unit")
    elif args.integration:
        cmd.append("tests/integration")
    else:
        cmd.append("tests")
    
    # Run the tests
    print(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(" ".join(cmd), shell=True)
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
