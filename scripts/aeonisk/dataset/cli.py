"""
Command-line interface for the dataset parser.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from aeonisk.dataset.parser import DatasetParser, DatasetParseError


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        args: Command-line arguments. If None, sys.argv[1:] is used.

    Returns:
        An argparse.Namespace object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Aeonisk dataset parser CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Parse command
    parse_parser = subparsers.add_parser("parse", help="Parse a dataset file")
    parse_parser.add_argument("input", help="Input dataset file")
    parse_parser.add_argument(
        "-o", "--output", 
        help="Output file (JSON format). If not provided, prints to stdout."
    )
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a dataset file")
    validate_parser.add_argument("input", help="Input dataset file")
    validate_parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Print detailed validation errors"
    )
    
    # Convert command
    convert_parser = subparsers.add_parser("convert", help="Convert a dataset file to another format")
    convert_parser.add_argument("input", help="Input dataset file")
    convert_parser.add_argument("output", help="Output dataset file")
    convert_parser.add_argument(
        "-f", "--format", 
        choices=["yaml", "json"], 
        default="yaml",
        help="Output format"
    )
    
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        args: Command-line arguments. If None, sys.argv[1:] is used.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parsed_args = parse_args(args)
    
    if not parsed_args.command:
        print("Error: No command specified. Use --help for usage information.")
        return 1
    
    parser = DatasetParser()
    
    try:
        if parsed_args.command == "parse":
            dataset = parser.parse_file(parsed_args.input)
            
            if parsed_args.output:
                with open(parsed_args.output, 'w', encoding='utf-8') as f:
                    json.dump(dataset, f, indent=2)
                print(f"Dataset parsed and saved to {parsed_args.output}")
            else:
                print(json.dumps(dataset, indent=2))
                
        elif parsed_args.command == "validate":
            dataset = parser.parse_file(parsed_args.input)
            validation_result = parser.validate(dataset)
            
            if validation_result.is_valid:
                print(f"Dataset is valid: {parsed_args.input}")
                return 0
            else:
                print(f"Dataset is invalid: {parsed_args.input}")
                if parsed_args.verbose:
                    for error in validation_result.errors:
                        print(f"  - {error}")
                else:
                    print(f"  Found {len(validation_result.errors)} errors. Use --verbose for details.")
                return 1
                
        elif parsed_args.command == "convert":
            dataset = parser.parse_file(parsed_args.input)
            
            if parsed_args.format == "json":
                with open(parsed_args.output, 'w', encoding='utf-8') as f:
                    json.dump(dataset, f, indent=2)
            else:  # yaml
                parser.save(dataset, parsed_args.output)
                
            print(f"Dataset converted and saved to {parsed_args.output}")
            
    except FileNotFoundError as e:
        print(f"Error: {str(e)}")
        return 1
    except DatasetParseError as e:
        print(f"Error parsing dataset: {str(e)}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
