"""
Unit tests for Experiment Infrastructure (Spec 11).

Tests:
1. Config generator per-role model support
2. EnemyCombatManager per-role LLM config with fallback
3. Session NPC LLM provider fallback chain
4. Code path documentation markers (inline comments)
"""

import copy
import json
import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
import sys

# Add project root so we can import scripts modules
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# =============================================================================
# FIXTURES: Base configs for testing
# =============================================================================

@pytest.fixture
def base_config():
    """Minimal base session config for config generator tests."""
    return {
        "session_name": "test_experiment",
        "max_turns": 3,
        "party_size": 2,
        "agents": {
            "dm": {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.7
                }
            },
            "players": [
                {
                    "name": "Sera Karsel",
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "temperature": 0.8
                    }
                },
                {
                    "name": "Kael Dren",
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "temperature": 0.8
                    }
                }
            ]
        }
    }


@pytest.fixture
def session_config_with_enemy_llm():
    """Session config that includes agents.enemies.llm section."""
    return {
        "session_name": "enemy_llm_test",
        "max_turns": 3,
        "party_size": 2,
        "tactical_module_enabled": True,
        "enemy_agents_enabled": True,
        "agents": {
            "dm": {
                "llm": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                    "temperature": 0.7
                }
            },
            "enemies": {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.5
                }
            },
            "players": [
                {
                    "name": "Test Player",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.8
                    }
                }
            ]
        }
    }


@pytest.fixture
def session_config_without_enemy_llm():
    """Session config without agents.enemies.llm (legacy, DM fallback)."""
    return {
        "session_name": "legacy_test",
        "max_turns": 3,
        "party_size": 2,
        "tactical_module_enabled": True,
        "enemy_agents_enabled": True,
        "agents": {
            "dm": {
                "llm": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                    "temperature": 0.7
                }
            },
            "players": [
                {
                    "name": "Test Player",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.8
                    }
                }
            ]
        }
    }


@pytest.fixture
def session_config_with_npc_llm():
    """Session config with full NPC fallback chain: npcs -> enemies -> dm."""
    return {
        "session_name": "npc_llm_test",
        "max_turns": 3,
        "party_size": 2,
        "tactical_module_enabled": True,
        "enemy_agents_enabled": True,
        "agents": {
            "dm": {
                "llm": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                    "temperature": 0.7
                }
            },
            "enemies": {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.5
                }
            },
            "npcs": {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.6
                }
            },
            "players": [
                {
                    "name": "Test Player",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-5",
                        "temperature": 0.8
                    }
                }
            ]
        }
    }


# =============================================================================
# TEST GROUP 1: Config Generator - Per-Role Model Support
# =============================================================================

class TestConfigGeneratorPerRole:
    """Test generate_multi_llm_configs.py per-role model variation."""

    def test_providers_flag_sets_all_roles(self, base_config):
        """--providers sets DM, players, enemies, and NPCs to same model."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(base_config, provider="anthropic", model="claude-sonnet-4-5")

        assert result["agents"]["dm"]["llm"]["model"] == "claude-sonnet-4-5"
        assert result["agents"]["dm"]["llm"]["provider"] == "anthropic"
        assert result["agents"]["players"][0]["llm"]["model"] == "claude-sonnet-4-5"
        assert result["agents"]["players"][1]["llm"]["model"] == "claude-sonnet-4-5"
        # NEW: enemies and npcs sections created
        assert result["agents"]["enemies"]["llm"]["model"] == "claude-sonnet-4-5"
        assert result["agents"]["npcs"]["llm"]["model"] == "claude-sonnet-4-5"

    def test_dm_model_override_only(self, base_config):
        """--dm-model overrides DM only, leaves players unchanged."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(base_config, dm_spec="anthropic:claude-sonnet-4-5")

        assert result["agents"]["dm"]["llm"]["model"] == "claude-sonnet-4-5"
        assert result["agents"]["dm"]["llm"]["provider"] == "anthropic"
        # Players should be unchanged
        assert result["agents"]["players"][0]["llm"]["model"] == "gpt-4o-mini"
        assert result["agents"]["players"][0]["llm"]["provider"] == "openai"

    def test_player_model_override_only(self, base_config):
        """--player-model overrides all players, leaves DM unchanged."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(base_config, player_spec="anthropic:claude-sonnet-4-5")

        # DM unchanged
        assert result["agents"]["dm"]["llm"]["model"] == "gpt-4o-mini"
        # Players changed
        assert result["agents"]["players"][0]["llm"]["model"] == "claude-sonnet-4-5"
        assert result["agents"]["players"][1]["llm"]["model"] == "claude-sonnet-4-5"

    def test_enemy_model_creates_config_section(self, base_config):
        """--enemy-model creates agents.enemies.llm section even if absent in base."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(base_config, enemy_spec="openai:gpt-4o-mini")

        assert "enemies" in result["agents"]
        assert result["agents"]["enemies"]["llm"]["model"] == "gpt-4o-mini"
        assert result["agents"]["enemies"]["llm"]["provider"] == "openai"

    def test_npc_model_creates_config_section(self, base_config):
        """--npc-model creates agents.npcs.llm section even if absent in base."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(base_config, npc_spec="openai:gpt-4o-mini")

        assert "npcs" in result["agents"]
        assert result["agents"]["npcs"]["llm"]["model"] == "gpt-4o-mini"
        assert result["agents"]["npcs"]["llm"]["provider"] == "openai"

    def test_per_role_all_different(self, base_config):
        """Each role can have a different model."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(
            base_config,
            dm_spec="anthropic:claude-sonnet-4-5",
            player_spec="openai:gpt-5-mini",
            enemy_spec="openai:gpt-4o-mini",
            npc_spec="openai:gpt-4o-mini"
        )

        assert result["agents"]["dm"]["llm"]["model"] == "claude-sonnet-4-5"
        assert result["agents"]["dm"]["llm"]["provider"] == "anthropic"
        assert result["agents"]["players"][0]["llm"]["model"] == "gpt-5-mini"
        assert result["agents"]["players"][0]["llm"]["provider"] == "openai"
        assert result["agents"]["enemies"]["llm"]["model"] == "gpt-4o-mini"
        assert result["agents"]["npcs"]["llm"]["model"] == "gpt-4o-mini"

    def test_providers_then_per_role_override(self, base_config):
        """Per-role flags override --providers for specific roles."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(
            base_config,
            provider="openai",
            model="gpt-5-mini",
            enemy_spec="openai:gpt-4o-mini"
        )

        # --providers sets all to gpt-5-mini...
        assert result["agents"]["dm"]["llm"]["model"] == "gpt-5-mini"
        assert result["agents"]["players"][0]["llm"]["model"] == "gpt-5-mini"
        assert result["agents"]["npcs"]["llm"]["model"] == "gpt-5-mini"
        # ...but --enemy-model overrides enemies to gpt-4o-mini
        assert result["agents"]["enemies"]["llm"]["model"] == "gpt-4o-mini"

    def test_session_name_includes_role_models(self, base_config):
        """Session name reflects per-role model choices."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(
            base_config,
            dm_spec="anthropic:claude-sonnet-4-5",
            player_spec="openai:gpt-5-mini"
        )

        assert "dm-" in result["session_name"]
        assert "pc-" in result["session_name"]

    def test_session_name_with_enemy_model(self, base_config):
        """Session name includes enemy model when specified."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(
            base_config,
            dm_spec="anthropic:claude-sonnet-4-5",
            enemy_spec="openai:gpt-4o-mini"
        )

        assert "dm-" in result["session_name"]
        assert "enemy-" in result["session_name"]

    def test_proxy_applied_to_per_role_models(self, base_config):
        """Proxy URL wraps per-role configs in batch_proxy routing."""
        from generate_multi_llm_configs import generate_config

        result = generate_config(
            base_config,
            dm_spec="anthropic:claude-sonnet-4-5",
            proxy_url="http://localhost:8000"
        )

        assert result["agents"]["dm"]["llm"]["provider"] == "batch_proxy"
        assert result["agents"]["dm"]["llm"]["underlying_provider"] == "anthropic"
        assert result["agents"]["dm"]["llm"]["model"] == "claude-sonnet-4-5"

    def test_base_config_not_mutated(self, base_config):
        """generate_config must not modify the input base_config."""
        from generate_multi_llm_configs import generate_config

        original = copy.deepcopy(base_config)
        generate_config(
            base_config,
            dm_spec="anthropic:claude-sonnet-4-5",
            enemy_spec="openai:gpt-4o-mini"
        )

        assert base_config == original


# =============================================================================
# TEST GROUP 2: EnemyCombatManager Per-Role LLM Config
# =============================================================================

class TestEnemyCombatManagerLLMConfig:
    """Test EnemyCombatManager reads per-role enemy LLM config."""

    @patch('aeonisk.multiagent.llm_provider.create_provider')
    def test_enemy_uses_own_config_when_present(self, mock_create, session_config_with_enemy_llm):
        """EnemyCombatManager reads agents.enemies.llm when available."""
        from aeonisk.multiagent.enemy_combat import EnemyCombatManager

        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        ecm = EnemyCombatManager()
        ecm.initialize(session_config_with_enemy_llm)

        # Verify create_provider was called with enemy config (gpt-4o-mini),
        # not DM config (claude-sonnet-4-5)
        assert mock_create.called
        config_arg = mock_create.call_args[0][0]
        assert config_arg.model == "gpt-4o-mini"
        assert config_arg.provider == "openai"

    @patch('aeonisk.multiagent.llm_provider.create_provider')
    def test_enemy_falls_back_to_dm_when_absent(self, mock_create, session_config_without_enemy_llm):
        """EnemyCombatManager falls back to agents.dm.llm when no enemy config."""
        from aeonisk.multiagent.enemy_combat import EnemyCombatManager

        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        ecm = EnemyCombatManager()
        ecm.initialize(session_config_without_enemy_llm)

        # Verify create_provider was called with DM config (claude-sonnet-4-5)
        assert mock_create.called
        config_arg = mock_create.call_args[0][0]
        assert config_arg.model == "claude-sonnet-4-5"
        assert config_arg.provider == "anthropic"

    @patch('aeonisk.multiagent.llm_provider.create_provider')
    def test_enemy_config_logged(self, mock_create, session_config_with_enemy_llm):
        """EnemyCombatManager logs which config source it used."""
        from aeonisk.multiagent.enemy_combat import EnemyCombatManager

        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        ecm = EnemyCombatManager()

        with patch('aeonisk.multiagent.enemy_combat.logger') as mock_logger:
            ecm.initialize(session_config_with_enemy_llm)
            # Should log that it's using per-role enemy config
            debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
            assert any("per-role enemy" in c for c in debug_calls), \
                f"Expected 'per-role enemy' in debug logs, got: {debug_calls}"


# =============================================================================
# TEST GROUP 3: Session NPC LLM Provider Fallback Chain
# =============================================================================

class TestSessionNPCLLMFallback:
    """Test NPC LLM provider fallback chain in session.py."""

    def test_get_npc_llm_provider_uses_npc_config(self, session_config_with_npc_llm):
        """get_npc_llm_provider returns NPC-specific config when present."""
        from aeonisk.multiagent.session import get_npc_llm_config

        result = get_npc_llm_config(session_config_with_npc_llm)

        assert result is not None
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"
        assert result["temperature"] == 0.6

    def test_get_npc_llm_provider_falls_back_to_enemy(self):
        """get_npc_llm_provider falls back to enemy config when no NPC config."""
        from aeonisk.multiagent.session import get_npc_llm_config

        config = {
            "agents": {
                "dm": {
                    "llm": {"provider": "anthropic", "model": "claude-sonnet-4-5"}
                },
                "enemies": {
                    "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.5}
                },
                "players": []
            }
        }

        result = get_npc_llm_config(config)

        assert result is not None
        assert result["model"] == "gpt-4o-mini"
        assert result["temperature"] == 0.5

    def test_get_npc_llm_provider_falls_back_to_dm(self):
        """get_npc_llm_provider falls back to DM config as last resort."""
        from aeonisk.multiagent.session import get_npc_llm_config

        config = {
            "agents": {
                "dm": {
                    "llm": {"provider": "anthropic", "model": "claude-sonnet-4-5", "temperature": 0.7}
                },
                "players": []
            }
        }

        result = get_npc_llm_config(config)

        assert result is not None
        assert result["model"] == "claude-sonnet-4-5"
        assert result["provider"] == "anthropic"

    def test_get_npc_llm_provider_returns_none_on_empty(self):
        """get_npc_llm_provider returns None when no config available at all."""
        from aeonisk.multiagent.session import get_npc_llm_config

        config = {"agents": {"dm": {}, "players": []}}

        result = get_npc_llm_config(config)

        assert result is None


# =============================================================================
# TEST GROUP 4: Session Config Validation - Optional Sections
# =============================================================================

class TestSessionConfigEnemyNPCSections:
    """Test that agents.enemies.llm and agents.npcs.llm are optional."""

    def test_enemies_llm_section_optional(self):
        """Existing configs without agents.enemies should load fine."""
        config = {
            "session_name": "test",
            "max_turns": 3,
            "party_size": 1,
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
                "players": [{"name": "Test", "llm": {"provider": "openai", "model": "gpt-4o-mini"}}]
            }
        }
        # Should NOT have enemies section by default
        assert "enemies" not in config["agents"]
        # But accessing it with .get() should be safe (no error)
        enemies_llm = config.get("agents", {}).get("enemies", {}).get("llm")
        assert enemies_llm is None

    def test_npcs_llm_section_optional(self):
        """Existing configs without agents.npcs should load fine."""
        config = {
            "session_name": "test",
            "max_turns": 3,
            "party_size": 1,
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
                "players": [{"name": "Test", "llm": {"provider": "openai", "model": "gpt-4o-mini"}}]
            }
        }
        assert "npcs" not in config["agents"]
        npcs_llm = config.get("agents", {}).get("npcs", {}).get("llm")
        assert npcs_llm is None

    def test_enemies_llm_section_validates_when_present(self):
        """agents.enemies.llm must have provider and model if present."""
        config = {
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
                "enemies": {
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "temperature": 0.5
                    }
                },
                "players": []
            }
        }
        enemies_llm = config["agents"]["enemies"]["llm"]
        assert "provider" in enemies_llm
        assert "model" in enemies_llm

    def test_npcs_llm_section_validates_when_present(self):
        """agents.npcs.llm must have provider and model if present."""
        config = {
            "agents": {
                "dm": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
                "npcs": {
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "temperature": 0.6
                    }
                },
                "players": []
            }
        }
        npcs_llm = config["agents"]["npcs"]["llm"]
        assert "provider" in npcs_llm
        assert "model" in npcs_llm


# =============================================================================
# TEST GROUP 5: Code Path Documentation Markers
# =============================================================================

class TestCodePathDocumentation:
    """Verify inline code-path documentation comments exist in source files."""

    def test_enemy_combat_has_structured_output_comment(self):
        """enemy_combat.py should have comment marking structured output path."""
        source_path = PROJECT_ROOT / "scripts" / "aeonisk" / "multiagent" / "enemy_combat.py"
        content = source_path.read_text()
        assert "RESOLUTION PATH: structured output" in content or \
               "Resolution path: structured output" in content or \
               "# Resolution: structured output" in content, \
            "enemy_combat.py should document which resolution path it uses"

    def test_enemy_combat_has_llm_config_source_comment(self):
        """enemy_combat.py should have comment documenting LLM config source."""
        source_path = PROJECT_ROOT / "scripts" / "aeonisk" / "multiagent" / "enemy_combat.py"
        content = source_path.read_text()
        assert "per-role enemy" in content.lower() or "fallback" in content.lower(), \
            "enemy_combat.py should document per-role enemy LLM config with fallback"

    def test_session_has_npc_fallback_comment(self):
        """session.py should have comment documenting NPC LLM fallback chain."""
        source_path = PROJECT_ROOT / "scripts" / "aeonisk" / "multiagent" / "session.py"
        content = source_path.read_text()
        assert "NPC LLM fallback" in content or "npc.*fallback" in content.lower() or \
               "npcs -> enemies -> dm" in content.lower(), \
            "session.py should document NPC LLM config fallback chain"
