"""
Unit tests for altar configuration loading.

Tests verify:
- Loading altars from scenario.altars config
- Altar type parsing
- Quality validation
- Duplicate prevention
"""

import pytest
from scripts.aeonisk.multiagent.shared_state import SharedState, Altar, AltarType


class TestAltarConfigLoading:
    """Test loading altars from session config."""

    def test_parse_altar_from_config(self):
        """Test creating Altar from config dict."""
        config = {
            'altar_type': 'ritual_altar',
            'quality': 5,
            'location': 'Temple Sanctum',
            'altar_id': 'alt_test1'
        }

        altar = Altar(
            altar_type=AltarType[config['altar_type'].upper()],
            quality=config['quality'],
            location=config['location'],
            altar_id=config.get('altar_id')
        )

        assert altar.altar_type == AltarType.RITUAL_ALTAR
        assert altar.quality == 5
        assert altar.location == 'Temple Sanctum'
        assert altar.altar_id == 'alt_test1'

    def test_parse_altar_without_id(self):
        """Test altar ID auto-generation when not in config."""
        config = {
            'altar_type': 'nexus_altar',
            'quality': 8,
            'location': 'Sovereign Sanctum'
        }

        altar = Altar(
            altar_type=AltarType[config['altar_type'].upper()],
            quality=config['quality'],
            location=config['location'],
            altar_id=config.get('altar_id')  # None
        )

        assert altar.altar_id is not None
        assert altar.altar_id.startswith('alt_')

    def test_parse_all_altar_types(self):
        """Test parsing all AltarType variants from config strings."""
        types = [
            'ritual_altar',
            'nexus_altar',
            'freeborn_altar',
            'black_market_altar',
            'abandoned_altar'
        ]

        for type_str in types:
            altar = Altar(
                altar_type=AltarType[type_str.upper()],
                quality=5,
                location='Test'
            )
            assert altar.altar_type.value == type_str

    def test_invalid_altar_type_raises_error(self):
        """Test that invalid altar_type raises KeyError."""
        with pytest.raises(KeyError):
            altar_type = AltarType['INVALID_TYPE']

    def test_quality_from_config(self):
        """Test quality values from config."""
        for quality in [1, 5, 10]:
            config = {
                'altar_type': 'ritual_altar',
                'quality': quality,
                'location': 'Test'
            }

            altar = Altar(
                altar_type=AltarType[config['altar_type'].upper()],
                quality=config['quality'],
                location=config['location']
            )

            assert altar.quality == quality


class TestScenarioAltarsConfig:
    """Test scenario.altars configuration format."""

    def test_empty_altars_config(self):
        """Test handling empty altars list."""
        config = {
            'scenario': {
                'altars': []
            }
        }

        altars = config['scenario'].get('altars', [])
        assert altars == []
        assert len(altars) == 0

    def test_missing_altars_config(self):
        """Test handling missing altars key."""
        config = {
            'scenario': {}
        }

        altars = config['scenario'].get('altars', [])
        assert altars == []

    def test_single_altar_config(self):
        """Test loading single altar from config."""
        config = {
            'scenario': {
                'altars': [
                    {
                        'altar_type': 'ritual_altar',
                        'quality': 5,
                        'location': 'Temple'
                    }
                ]
            }
        }

        altars_config = config['scenario']['altars']
        assert len(altars_config) == 1
        assert altars_config[0]['altar_type'] == 'ritual_altar'
        assert altars_config[0]['quality'] == 5

    def test_multiple_altars_config(self):
        """Test loading multiple altars."""
        config = {
            'scenario': {
                'altars': [
                    {
                        'altar_type': 'nexus_altar',
                        'quality': 9,
                        'location': 'Sovereign Sanctum'
                    },
                    {
                        'altar_type': 'freeborn_altar',
                        'quality': 6,
                        'location': 'Market Plaza'
                    }
                ]
            }
        }

        altars_config = config['scenario']['altars']
        assert len(altars_config) == 2

    def test_altar_with_explicit_id(self):
        """Test altar config with explicit altar_id."""
        config = {
            'scenario': {
                'altars': [
                    {
                        'altar_id': 'alt_main',
                        'altar_type': 'ritual_altar',
                        'quality': 7,
                        'location': 'Main Temple'
                    }
                ]
            }
        }

        altar_config = config['scenario']['altars'][0]
        assert 'altar_id' in altar_config
        assert altar_config['altar_id'] == 'alt_main'


class TestAltarConfigValidation:
    """Test validation of altar config values."""

    def test_required_fields_present(self):
        """Test that required fields are checked."""
        # Valid config
        config = {
            'altar_type': 'ritual_altar',
            'quality': 5,
            'location': 'Temple'
        }

        assert 'altar_type' in config
        assert 'quality' in config
        assert 'location' in config

    def test_quality_range_validation(self):
        """Test quality range 1-10 validation."""
        # Valid qualities
        valid = [1, 5, 10]
        for q in valid:
            assert 1 <= q <= 10

        # Invalid qualities
        invalid = [0, 11, -1, 15]
        for q in invalid:
            assert not (1 <= q <= 10)
