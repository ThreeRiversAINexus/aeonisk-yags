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


@pytest.fixture
def sample_dataset_content_v1_1_2():
    """Return the content of the sample dataset file for v1.1.2."""
    # Placeholder content - will be updated when the new dataset is created
    return """
# Aeonisk RPG Glossary (Based on YAGS Module v1.1.2)
# For Code Integration & AI Context
task_id: YAGS-AEONISK-V112-001
skills:
  list:
    Attunement:
      attribute: Willpower
      type: Aeonisk
      description: Aligning raw Seeds to elements.
    Dreamwork:
      attribute: Willpower # Or Empathy
      type: Aeonisk
      description: Navigating and influencing dreams.
seed_economy:
  states:
    Raw_Seed: { description: Unstable potential }
    Attuned_Seed: { description: Aligned to element }
    Converted_Seed: { description: Expended energy }
  attunement_process: { skill: Attunement, attribute: Willpower }
  degradation_cycle: 7
dreamwork:
  triggers: [rest, ritual, bond, trauma, void]
  outcomes: [bond_shift, void_change, insight, confrontation]
  group_dreams: { enabled: true, trigger: shared_rest }
void_system:
  environmental_disruption:
    thresholds:
      - { score: 5, effect: minor }
      - { score: 7, effect: significant }
      - { score: 9, effect: severe }
      - { score: 10, effect: claimed }
  void_spike:
    trigger_threshold: 2
    effect: stun
"""
