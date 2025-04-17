"""
Pytest configuration for the Aeonisk YAGS toolkit.

This file contains fixtures and setup for the test suite.
"""

import os
import pytest
from pathlib import Path


@pytest.fixture
def sample_dataset_path():
    """Return the path to the sample dataset file."""
    return Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                            'datasets', 'aeonisk-dataset-v1.0.1.txt'))


@pytest.fixture
def sample_dataset_content(sample_dataset_path):
    """Return the content of the sample dataset file."""
    with open(sample_dataset_path, 'r', encoding='utf-8') as f:
        return f.read()
