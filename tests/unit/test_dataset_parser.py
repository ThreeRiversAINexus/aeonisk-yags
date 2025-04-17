"""
Unit tests for the dataset parser module.
"""

import pytest
from aeonisk.dataset.parser import DatasetParser, DatasetParseError


class TestDatasetParser:
    """Test suite for the DatasetParser class."""

    def test_parser_initialization(self):
        """Test that the parser can be initialized."""
        parser = DatasetParser()
        assert parser is not None

    def test_parse_empty_string(self):
        """Test that parsing an empty string raises an error."""
        parser = DatasetParser()
        with pytest.raises(DatasetParseError):
            parser.parse("")

    def test_parse_invalid_format(self):
        """Test that parsing an invalid format raises an error."""
        parser = DatasetParser()
        with pytest.raises(DatasetParseError):
            parser.parse("This is not a valid dataset format")

    def test_parse_valid_dataset(self, sample_dataset_content):
        """Test parsing a valid dataset."""
        parser = DatasetParser()
        dataset = parser.parse(sample_dataset_content)
        
        # Check that the dataset has the expected structure
        assert "attributes" in dataset
        assert "skills" in dataset
        assert "character_generation" in dataset
        
        # Check specific content
        assert "primary" in dataset["attributes"]
        assert "Strength" in dataset["attributes"]["primary"]
        assert dataset["attributes"]["primary"]["Strength"]["abbreviation"] == "Str"
        
        # Check that task_id fields are parsed correctly
        assert "task_id" in dataset
        assert dataset["task_id"] == "YAGS-AEONISK-001"

    def test_parse_file(self, sample_dataset_path):
        """Test parsing a dataset from a file."""
        parser = DatasetParser()
        dataset = parser.parse_file(sample_dataset_path)
        
        # Check that the dataset has the expected structure
        assert "attributes" in dataset
        assert "skills" in dataset
        assert "character_generation" in dataset

    def test_validate_valid_dataset(self, sample_dataset_content):
        """Test validating a valid dataset."""
        parser = DatasetParser()
        dataset = parser.parse(sample_dataset_content)
        validation_result = parser.validate(dataset)
        
        assert validation_result.is_valid
        assert len(validation_result.errors) == 0

    def test_validate_invalid_dataset(self):
        """Test validating an invalid dataset."""
        parser = DatasetParser()
        invalid_dataset = {"invalid": "structure"}
        validation_result = parser.validate(invalid_dataset)
        
        assert not validation_result.is_valid
        assert len(validation_result.errors) > 0

    def test_save_dataset(self, tmp_path):
        """Test saving a dataset to a file."""
        parser = DatasetParser()
        dataset = {
            "attributes": {
                "primary": {
                    "Strength": {
                        "abbreviation": "Str",
                        "description": "Physical power"
                    }
                }
            },
            "skills": {
                "types": {
                    "Talents": {
                        "description": "Core skills"
                    }
                }
            }
        }
        
        output_path = tmp_path / "test_output.txt"
        parser.save(dataset, output_path)
        
        # Check that the file was created
        assert output_path.exists()
        
        # Check that the content can be parsed back
        loaded_dataset = parser.parse_file(output_path)
        assert "attributes" in loaded_dataset
        assert "primary" in loaded_dataset["attributes"]
        assert "Strength" in loaded_dataset["attributes"]["primary"]
