"""
Dataset parser module for the Aeonisk YAGS toolkit.

This module provides tools for parsing, validating, and saving Aeonisk datasets.
"""

import os
import re
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Union, Optional


class DatasetParseError(Exception):
    """Exception raised when parsing a dataset fails."""
    pass


@dataclass
class ValidationResult:
    """Result of validating a dataset."""
    is_valid: bool
    errors: List[str]


class DatasetParser:
    """Parser for Aeonisk datasets."""

    def __init__(self):
        """Initialize the parser."""
        self.required_top_level_keys = [
            "attributes",
            "skills",
            "character_generation"
        ]

    def parse(self, content: str) -> Dict[str, Any]:
        """
        Parse a dataset from a string.

        Args:
            content: The dataset content as a string.

        Returns:
            A dictionary representing the parsed dataset.

        Raises:
            DatasetParseError: If the dataset cannot be parsed.
        """
        if not content:
            raise DatasetParseError("Dataset content is empty")

        try:
            # Split the content into sections based on the '---' separator
            sections = re.split(r'^---$', content, flags=re.MULTILINE)
            
            # Parse the first section as the main dataset
            main_section = sections[0]
            dataset = yaml.safe_load(main_section)
            
            if not isinstance(dataset, dict):
                raise DatasetParseError("Dataset must be a dictionary")
            
            # Parse additional sections if they exist
            if len(sections) > 1:
                for i, section in enumerate(sections[1:], 1):
                    if not section.strip():
                        continue
                    
                    section_data = yaml.safe_load(section)
                    if not isinstance(section_data, dict):
                        continue
                    
                    # If the section has a task_id, use it as a key
                    if "task_id" in section_data:
                        task_id = section_data["task_id"]
                        if "tasks" not in dataset:
                            dataset["tasks"] = {}
                        dataset["tasks"][task_id] = section_data
            
            return dataset
            
        except yaml.YAMLError as e:
            raise DatasetParseError(f"Failed to parse dataset: {str(e)}")
        except Exception as e:
            raise DatasetParseError(f"Unexpected error parsing dataset: {str(e)}")

    def parse_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse a dataset from a file.

        Args:
            file_path: Path to the dataset file.

        Returns:
            A dictionary representing the parsed dataset.

        Raises:
            DatasetParseError: If the dataset cannot be parsed.
            FileNotFoundError: If the file does not exist.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse(content)
        except FileNotFoundError:
            raise FileNotFoundError(f"Dataset file not found: {file_path}")
        except DatasetParseError as e:
            raise e
        except Exception as e:
            raise DatasetParseError(f"Error reading dataset file: {str(e)}")

    def validate(self, dataset: Dict[str, Any]) -> ValidationResult:
        """
        Validate a dataset.

        Args:
            dataset: The dataset to validate.

        Returns:
            A ValidationResult object indicating whether the dataset is valid.
        """
        errors = []

        # Check for required top-level keys
        for key in self.required_top_level_keys:
            if key not in dataset:
                errors.append(f"Missing required top-level key: {key}")

        # Check attributes structure if it exists
        if "attributes" in dataset:
            attributes = dataset["attributes"]
            if not isinstance(attributes, dict):
                errors.append("'attributes' must be a dictionary")
            else:
                if "primary" not in attributes:
                    errors.append("Missing 'primary' in attributes")
                elif not isinstance(attributes["primary"], dict):
                    errors.append("'attributes.primary' must be a dictionary")

        # Check skills structure if it exists
        if "skills" in dataset:
            skills = dataset["skills"]
            if not isinstance(skills, dict):
                errors.append("'skills' must be a dictionary")
            else:
                if "types" not in skills:
                    errors.append("Missing 'types' in skills")
                elif not isinstance(skills["types"], dict):
                    errors.append("'skills.types' must be a dictionary")

        # Check character_generation structure if it exists
        if "character_generation" in dataset:
            char_gen = dataset["character_generation"]
            if not isinstance(char_gen, dict):
                errors.append("'character_generation' must be a dictionary")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )

    def save(self, dataset: Dict[str, Any], file_path: Union[str, Path]) -> None:
        """
        Save a dataset to a file.

        Args:
            dataset: The dataset to save.
            file_path: Path to the output file.

        Raises:
            IOError: If the file cannot be written.
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # Extract tasks if they exist
            tasks = dataset.pop("tasks", {}) if "tasks" in dataset else {}
            
            # Convert the main dataset to YAML
            content = yaml.dump(dataset, sort_keys=False, default_flow_style=False)
            
            # Add tasks as separate sections if they exist
            if tasks:
                for task_id, task_data in tasks.items():
                    content += "\n---\n"
                    content += yaml.dump(task_data, sort_keys=False, default_flow_style=False)
            
            # Write to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            # Restore tasks to the dataset
            if tasks:
                dataset["tasks"] = tasks
                
        except Exception as e:
            raise IOError(f"Failed to save dataset: {str(e)}")
