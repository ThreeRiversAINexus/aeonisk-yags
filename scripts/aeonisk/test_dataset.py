"""
Comprehensive test suite for the Aeonisk YAGS dataset system.

This test suite covers dataset parsing, validation, and CLI functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import json
import yaml

from aeonisk.dataset.cli import main, parse_args
from aeonisk.dataset.parser import DatasetParser, DatasetParseError
from aeonisk.dataset.manager import DatasetManager


class TestDatasetCLI:
    """Test suite for the dataset CLI functionality."""
    
    def test_parse_args_parse_command(self):
        """Test parsing arguments for the parse command."""
        args = parse_args(['parse', 'input.txt', '-o', 'output.json'])
        
        assert args.command == 'parse'
        assert args.input == 'input.txt'
        assert args.output == 'output.json'
    
    def test_parse_args_validate_command(self):
        """Test parsing arguments for the validate command."""
        args = parse_args(['validate', 'input.txt', '-v'])
        
        assert args.command == 'validate'
        assert args.input == 'input.txt'
        assert args.verbose is True
    
    def test_parse_args_convert_command(self):
        """Test parsing arguments for the convert command."""
        args = parse_args(['convert', 'input.txt', 'output.yaml', '-f', 'yaml'])
        
        assert args.command == 'convert'
        assert args.input == 'input.txt'
        assert args.output == 'output.yaml'
        assert args.format == 'yaml'
    
    def test_parse_args_no_command(self):
        """Test parsing arguments with no command."""
        args = parse_args([])
        
        assert args.command is None
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_parse_command_success(self, mock_parser_class):
        """Test main function with parse command."""
        # Mock parser
        mock_parser = Mock()
        mock_parser.parse_file.return_value = {"task_id": "test"}
        mock_parser_class.return_value = mock_parser
        
        # Mock file operations
        with patch('builtins.open', mock_open()):
            result = main(['parse', 'input.txt', '-o', 'output.json'])
        
        assert result == 0
        mock_parser.parse_file.assert_called_once_with('input.txt')
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_validate_command_valid(self, mock_parser_class):
        """Test main function with validate command for valid dataset."""
        # Mock parser
        mock_parser = Mock()
        mock_parser.parse_file.return_value = {"task_id": "test"}
        mock_validation_result = Mock()
        mock_validation_result.is_valid = True
        mock_parser.validate.return_value = mock_validation_result
        mock_parser_class.return_value = mock_parser
        
        result = main(['validate', 'input.txt'])
        
        assert result == 0
        mock_parser.parse_file.assert_called_once_with('input.txt')
        mock_parser.validate.assert_called_once()
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_validate_command_invalid(self, mock_parser_class):
        """Test main function with validate command for invalid dataset."""
        # Mock parser
        mock_parser = Mock()
        mock_parser.parse_file.return_value = {"task_id": "test"}
        mock_validation_result = Mock()
        mock_validation_result.is_valid = False
        mock_validation_result.errors = ["Error 1", "Error 2"]
        mock_parser.validate.return_value = mock_validation_result
        mock_parser_class.return_value = mock_parser
        
        result = main(['validate', 'input.txt'])
        
        assert result == 1
        mock_parser.parse_file.assert_called_once_with('input.txt')
        mock_parser.validate.assert_called_once()
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_convert_command_to_json(self, mock_parser_class):
        """Test main function with convert command to JSON."""
        # Mock parser
        mock_parser = Mock()
        mock_parser.parse_file.return_value = {"task_id": "test"}
        mock_parser_class.return_value = mock_parser
        
        # Mock file operations
        with patch('builtins.open', mock_open()):
            result = main(['convert', 'input.txt', 'output.json', '-f', 'json'])
        
        assert result == 0
        mock_parser.parse_file.assert_called_once_with('input.txt')
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_convert_command_to_yaml(self, mock_parser_class):
        """Test main function with convert command to YAML."""
        # Mock parser
        mock_parser = Mock()
        mock_parser.parse_file.return_value = {"task_id": "test"}
        mock_parser_class.return_value = mock_parser
        
        result = main(['convert', 'input.txt', 'output.yaml', '-f', 'yaml'])
        
        assert result == 0
        mock_parser.parse_file.assert_called_once_with('input.txt')
        mock_parser.save.assert_called_once()
    
    def test_main_no_command(self):
        """Test main function with no command."""
        result = main([])
        
        assert result == 1
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_file_not_found(self, mock_parser_class):
        """Test main function with file not found error."""
        # Mock parser to raise FileNotFoundError
        mock_parser = Mock()
        mock_parser.parse_file.side_effect = FileNotFoundError("File not found")
        mock_parser_class.return_value = mock_parser
        
        result = main(['parse', 'nonexistent.txt'])
        
        assert result == 1
    
    @patch('aeonisk.dataset.cli.DatasetParser')
    def test_main_parse_error(self, mock_parser_class):
        """Test main function with parse error."""
        # Mock parser to raise DatasetParseError
        mock_parser = Mock()
        mock_parser.parse_file.side_effect = DatasetParseError("Parse error")
        mock_parser_class.return_value = mock_parser
        
        result = main(['parse', 'input.txt'])
        
        assert result == 1


class TestDatasetParser:
    """Test suite for the DatasetParser class."""
    
    def test_parser_initialization(self):
        """Test parser initialization."""
        parser = DatasetParser()
        
        assert parser is not None
    
    def test_parse_valid_yaml_content(self):
        """Test parsing valid YAML content."""
        parser = DatasetParser()
        
        yaml_content = """
---
task_id: YAGS-TEST-001
domain:
  core: rule_application
  subdomain: skill_check
scenario: Test scenario
environment: Test environment
stakes: Test stakes
characters:
  - name: Test Character
    attributes:
      Strength: 4
      Agility: 3
    skills:
      Athletics: 3
goal: Test goal
expected_fields:
  - attribute_used
  - skill_used
gold_answer:
  attribute_used: Agility
  skill_used: Athletics
"""
        
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            result = parser.parse_file('test.yaml')
        
        assert len(result) == 1
        assert result[0]['task_id'] == 'YAGS-TEST-001'
        assert result[0]['domain']['core'] == 'rule_application'
        assert result[0]['scenario'] == 'Test scenario'
    
    def test_parse_multiple_documents(self):
        """Test parsing multiple YAML documents."""
        parser = DatasetParser()
        
        yaml_content = """
---
task_id: YAGS-TEST-001
domain:
  core: rule_application
  subdomain: skill_check
scenario: Test scenario 1
environment: Test environment
stakes: Test stakes
characters:
  - name: Test Character
goal: Test goal
expected_fields:
  - attribute_used
gold_answer:
  attribute_used: Agility
---
task_id: YAGS-TEST-002
domain:
  core: combat
  subdomain: melee
scenario: Test scenario 2
environment: Test environment
stakes: Test stakes
characters:
  - name: Test Character
goal: Test goal
expected_fields:
  - attribute_used
gold_answer:
  attribute_used: Strength
"""
        
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            result = parser.parse_file('test.yaml')
        
        assert len(result) == 2
        assert result[0]['task_id'] == 'YAGS-TEST-001'
        assert result[1]['task_id'] == 'YAGS-TEST-002'
    
    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML content."""
        parser = DatasetParser()
        
        invalid_yaml = """
---
task_id: YAGS-TEST-001
domain:
  core: rule_application
  subdomain: skill_check
scenario: Test scenario
  invalid_yaml: [
environment: Test environment
"""
        
        with patch('builtins.open', mock_open(read_data=invalid_yaml)):
            with pytest.raises(DatasetParseError):
                parser.parse_file('test.yaml')
    
    def test_validate_valid_task(self):
        """Test validating a valid task."""
        parser = DatasetParser()
        
        tasks = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {
                    'core': 'rule_application',
                    'subdomain': 'skill_check'
                },
                'scenario': 'Test scenario',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            }
        ]
        
        result = parser.validate(tasks)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_missing_required_fields(self):
        """Test validating task with missing required fields."""
        parser = DatasetParser()
        
        tasks = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {
                    'core': 'rule_application',
                    'subdomain': 'skill_check'
                },
                'scenario': 'Test scenario',
                # Missing required fields: environment, stakes, characters, goal, expected_fields, gold_answer
            }
        ]
        
        result = parser.validate(tasks)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any('environment' in error for error in result.errors)
        assert any('stakes' in error for error in result.errors)
        assert any('characters' in error for error in result.errors)
        assert any('goal' in error for error in result.errors)
        assert any('expected_fields' in error for error in result.errors)
        assert any('gold_answer' in error for error in result.errors)
    
    def test_validate_invalid_domain(self):
        """Test validating task with invalid domain structure."""
        parser = DatasetParser()
        
        tasks = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': 'invalid_domain',  # Should be a dict
                'scenario': 'Test scenario',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            }
        ]
        
        result = parser.validate(tasks)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any('domain' in error for error in result.errors)
    
    def test_save_to_file(self):
        """Test saving tasks to file."""
        parser = DatasetParser()
        
        tasks = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {
                    'core': 'rule_application',
                    'subdomain': 'skill_check'
                },
                'scenario': 'Test scenario',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            }
        ]
        
        with patch('builtins.open', mock_open()) as mock_file:
            parser.save(tasks, 'output.yaml')
        
        mock_file.assert_called_once_with('output.yaml', 'w', encoding='utf-8')
        # Verify that write was called (indicating YAML was written)
        mock_file().write.assert_called()


class TestDatasetManager:
    """Test suite for the DatasetManager class."""
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = DatasetManager()
        
        assert manager is not None
    
    def test_load_dataset_success(self):
        """Test loading a dataset successfully."""
        manager = DatasetManager()
        
        # Mock successful file read
        yaml_content = """
---
task_id: YAGS-TEST-001
domain:
  core: rule_application
  subdomain: skill_check
scenario: Test scenario
environment: Test environment
stakes: Test stakes
characters:
  - name: Test Character
goal: Test goal
expected_fields:
  - attribute_used
gold_answer:
  attribute_used: Agility
"""
        
        with patch('builtins.open', mock_open(read_data=yaml_content)):
            result = manager.load_dataset('test.yaml')
        
        assert len(result) == 1
        assert result[0]['task_id'] == 'YAGS-TEST-001'
    
    def test_load_dataset_file_not_found(self):
        """Test loading a non-existent dataset."""
        manager = DatasetManager()
        
        with patch('builtins.open', side_effect=FileNotFoundError()):
            with pytest.raises(FileNotFoundError):
                manager.load_dataset('nonexistent.yaml')
    
    def test_save_dataset_success(self):
        """Test saving a dataset successfully."""
        manager = DatasetManager()
        
        tasks = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {
                    'core': 'rule_application',
                    'subdomain': 'skill_check'
                },
                'scenario': 'Test scenario',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            }
        ]
        
        with patch('builtins.open', mock_open()) as mock_file:
            manager.save_dataset(tasks, 'output.yaml')
        
        mock_file.assert_called_once_with('output.yaml', 'w', encoding='utf-8')
        mock_file().write.assert_called()
    
    def test_merge_datasets(self):
        """Test merging multiple datasets."""
        manager = DatasetManager()
        
        dataset1 = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {'core': 'rule_application', 'subdomain': 'skill_check'},
                'scenario': 'Test scenario 1',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            }
        ]
        
        dataset2 = [
            {
                'task_id': 'YAGS-TEST-002',
                'domain': {'core': 'combat', 'subdomain': 'melee'},
                'scenario': 'Test scenario 2',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Strength'}
            }
        ]
        
        merged = manager.merge_datasets([dataset1, dataset2])
        
        assert len(merged) == 2
        assert merged[0]['task_id'] == 'YAGS-TEST-001'
        assert merged[1]['task_id'] == 'YAGS-TEST-002'
    
    def test_merge_datasets_duplicate_task_ids(self):
        """Test merging datasets with duplicate task IDs."""
        manager = DatasetManager()
        
        dataset1 = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {'core': 'rule_application', 'subdomain': 'skill_check'},
                'scenario': 'Test scenario 1',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            }
        ]
        
        dataset2 = [
            {
                'task_id': 'YAGS-TEST-001',  # Duplicate task ID
                'domain': {'core': 'combat', 'subdomain': 'melee'},
                'scenario': 'Test scenario 2',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Strength'}
            }
        ]
        
        with pytest.raises(ValueError):
            manager.merge_datasets([dataset1, dataset2])
    
    def test_get_task_statistics(self):
        """Test getting task statistics."""
        manager = DatasetManager()
        
        tasks = [
            {
                'task_id': 'YAGS-TEST-001',
                'domain': {'core': 'rule_application', 'subdomain': 'skill_check'},
                'scenario': 'Test scenario 1',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Agility'}
            },
            {
                'task_id': 'YAGS-TEST-002',
                'domain': {'core': 'combat', 'subdomain': 'melee'},
                'scenario': 'Test scenario 2',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Strength'}
            },
            {
                'task_id': 'YAGS-TEST-003',
                'domain': {'core': 'rule_application', 'subdomain': 'ritual'},
                'scenario': 'Test scenario 3',
                'environment': 'Test environment',
                'stakes': 'Test stakes',
                'characters': [{'name': 'Test Character'}],
                'goal': 'Test goal',
                'expected_fields': ['attribute_used'],
                'gold_answer': {'attribute_used': 'Willpower'}
            }
        ]
        
        stats = manager.get_task_statistics(tasks)
        
        assert stats['total_tasks'] == 3
        assert stats['domains']['rule_application'] == 2
        assert stats['domains']['combat'] == 1
        assert stats['subdomains']['skill_check'] == 1
        assert stats['subdomains']['melee'] == 1
        assert stats['subdomains']['ritual'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])