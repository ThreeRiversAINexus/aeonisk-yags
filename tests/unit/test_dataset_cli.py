"""
Unit tests for the dataset CLI module.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from aeonisk.dataset.cli import main


class TestDatasetCLI:
    """Test suite for the dataset CLI module."""

    def test_parse_command(self, sample_dataset_path, capsys):
        """Test the parse command."""
        # Test parsing to stdout
        exit_code = main(["parse", str(sample_dataset_path)])
        assert exit_code == 0
        
        captured = capsys.readouterr()
        assert captured.out
        
        # Verify the output is valid JSON
        parsed_output = json.loads(captured.out)
        assert "attributes" in parsed_output
        assert "skills" in parsed_output
        
    def test_parse_command_with_output(self, sample_dataset_path, tmp_path):
        """Test the parse command with output file."""
        output_path = tmp_path / "output.json"
        
        exit_code = main(["parse", str(sample_dataset_path), "-o", str(output_path)])
        assert exit_code == 0
        
        # Verify the output file exists and contains valid JSON
        assert output_path.exists()
        with open(output_path, 'r', encoding='utf-8') as f:
            parsed_output = json.load(f)
        
        assert "attributes" in parsed_output
        assert "skills" in parsed_output
        
    def test_validate_command_valid(self, sample_dataset_path, capsys):
        """Test the validate command with a valid dataset."""
        exit_code = main(["validate", str(sample_dataset_path)])
        assert exit_code == 0
        
        captured = capsys.readouterr()
        assert "Dataset is valid" in captured.out
        
    def test_validate_command_invalid(self, tmp_path, capsys):
        """Test the validate command with an invalid dataset."""
        # Create an invalid dataset file
        invalid_dataset_path = tmp_path / "invalid.yaml"
        with open(invalid_dataset_path, 'w', encoding='utf-8') as f:
            f.write("invalid: structure")
        
        exit_code = main(["validate", str(invalid_dataset_path)])
        assert exit_code == 1
        
        captured = capsys.readouterr()
        assert "Dataset is invalid" in captured.out
        
    def test_validate_command_verbose(self, tmp_path, capsys):
        """Test the validate command with verbose output."""
        # Create an invalid dataset file
        invalid_dataset_path = tmp_path / "invalid.yaml"
        with open(invalid_dataset_path, 'w', encoding='utf-8') as f:
            f.write("invalid: structure")
        
        exit_code = main(["validate", str(invalid_dataset_path), "-v"])
        assert exit_code == 1
        
        captured = capsys.readouterr()
        assert "Dataset is invalid" in captured.out
        assert "Missing required top-level key" in captured.out
        
    def test_convert_command_to_json(self, sample_dataset_path, tmp_path):
        """Test the convert command to JSON format."""
        output_path = tmp_path / "output.json"
        
        exit_code = main(["convert", str(sample_dataset_path), str(output_path), "-f", "json"])
        assert exit_code == 0
        
        # Verify the output file exists and contains valid JSON
        assert output_path.exists()
        with open(output_path, 'r', encoding='utf-8') as f:
            parsed_output = json.load(f)
        
        assert "attributes" in parsed_output
        assert "skills" in parsed_output
        
    def test_convert_command_to_yaml(self, sample_dataset_path, tmp_path):
        """Test the convert command to YAML format."""
        output_path = tmp_path / "output.yaml"
        
        exit_code = main(["convert", str(sample_dataset_path), str(output_path), "-f", "yaml"])
        assert exit_code == 0
        
        # Verify the output file exists
        assert output_path.exists()
        
        # Verify the output can be parsed back
        from aeonisk.dataset.parser import DatasetParser
        parser = DatasetParser()
        dataset = parser.parse_file(output_path)
        
        assert "attributes" in dataset
        assert "skills" in dataset
        
    def test_nonexistent_file(self, capsys):
        """Test handling of nonexistent files."""
        exit_code = main(["parse", "nonexistent.yaml"])
        assert exit_code == 1
        
        captured = capsys.readouterr()
        assert "Error: Dataset file not found" in captured.out
        
    def test_no_command(self, capsys):
        """Test handling of no command."""
        exit_code = main([])
        assert exit_code == 1
        
        captured = capsys.readouterr()
        assert "Error: No command specified" in captured.out
