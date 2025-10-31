"""
Builder pattern for creating test sessions with specific configurations.

This helper makes it easy to construct multi-agent sessions with:
- Custom player counts and configurations
- Specific enemy setups
- Scenario overrides
- Mock LLM clients
- Test-friendly logging settings
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class TestSessionBuilder:
    """
    Builder for creating SelfPlayingSession instances for testing.

    Usage:
        builder = TestSessionBuilder()
        session = await builder
            .with_players(2)
            .with_enemies("shadow_creature", count=1)
            .with_mock_llm(mock_client)
            .with_scenario({"theme": "combat_test"})
            .build()
    """

    def __init__(self):
        """Initialize builder with defaults."""
        self._config = {
            "num_players": 2,
            "max_rounds": 5,
            "scenario_theme": "test",
            "player_names": [],
            "enable_enemies": False,
            "max_enemies": 0,
            "llm_provider": "mock",
            "log_dir": None,
            "session_id": None
        }
        self._player_configs: List[Dict[str, Any]] = []
        self._enemy_templates: List[Dict[str, Any]] = []
        self._scenario_override: Optional[Dict[str, Any]] = None
        self._mock_llm_client = None
        self._mechanics_overrides: Dict[str, Any] = {}

    def with_players(self, count: int, names: Optional[List[str]] = None) -> "TestSessionBuilder":
        """
        Configure number of players.

        Args:
            count: Number of players
            names: Optional list of player names (auto-generated if not provided)

        Returns:
            Self for chaining
        """
        self._config["num_players"] = count

        if names:
            self._config["player_names"] = names
        else:
            self._config["player_names"] = [f"TestPlayer{i+1}" for i in range(count)]

        return self

    def with_player_config(self, player_config: Dict[str, Any]) -> "TestSessionBuilder":
        """
        Add a specific player configuration.

        Args:
            player_config: Dict with player details (name, class, level, etc.)

        Returns:
            Self for chaining
        """
        self._player_configs.append(player_config)
        return self

    def with_enemies(self, template: str = "test_enemy", count: int = 1) -> "TestSessionBuilder":
        """
        Enable enemies with a specific template.

        Args:
            template: Enemy template name
            count: Number of enemies

        Returns:
            Self for chaining
        """
        self._config["enable_enemies"] = True
        self._config["max_enemies"] = count

        for i in range(count):
            self._enemy_templates.append({
                "template": template,
                "name": f"{template}_{i+1}",
                "threat_level": 1
            })

        return self

    def with_scenario(self, scenario: Dict[str, Any]) -> "TestSessionBuilder":
        """
        Override scenario configuration.

        Args:
            scenario: Scenario details (theme, description, etc.)

        Returns:
            Self for chaining
        """
        self._scenario_override = scenario
        return self

    def with_mock_llm(self, mock_client) -> "TestSessionBuilder":
        """
        Provide a mock LLM client.

        Args:
            mock_client: MockLLMClient instance

        Returns:
            Self for chaining
        """
        self._mock_llm_client = mock_client
        self._config["llm_provider"] = "mock"
        return self

    def with_log_dir(self, log_dir: Path) -> "TestSessionBuilder":
        """
        Set logging directory.

        Args:
            log_dir: Path to log directory

        Returns:
            Self for chaining
        """
        self._config["log_dir"] = str(log_dir)
        return self

    def with_session_id(self, session_id: str) -> "TestSessionBuilder":
        """
        Set specific session ID.

        Args:
            session_id: Session identifier

        Returns:
            Self for chaining
        """
        self._config["session_id"] = session_id
        return self

    def with_max_rounds(self, max_rounds: int) -> "TestSessionBuilder":
        """
        Set maximum rounds.

        Args:
            max_rounds: Maximum number of rounds

        Returns:
            Self for chaining
        """
        self._config["max_rounds"] = max_rounds
        return self

    def with_mechanics_override(self, key: str, value: Any) -> "TestSessionBuilder":
        """
        Override mechanics engine settings.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            Self for chaining
        """
        self._mechanics_overrides[key] = value
        return self

    def disable_logging(self) -> "TestSessionBuilder":
        """
        Disable JSONL logging for faster tests.

        Returns:
            Self for chaining
        """
        self._mechanics_overrides["enable_logging"] = False
        return self

    async def build(self):
        """
        Build the session instance.

        Returns:
            Configured SelfPlayingSession (or mock for unit tests)

        Note:
            This method would normally import and instantiate the real
            SelfPlayingSession class. For unit tests, you might want to
            return a mock instead.
        """
        # Generate session ID if not provided
        if not self._config["session_id"]:
            self._config["session_id"] = str(uuid.uuid4())

        # For now, return a mock session structure
        # In real implementation, this would create actual session
        session_config = {
            **self._config,
            "player_configs": self._player_configs,
            "enemy_templates": self._enemy_templates,
            "scenario_override": self._scenario_override,
            "mechanics_overrides": self._mechanics_overrides
        }

        # Create mock session object
        mock_session = MagicMock()
        mock_session.config = session_config
        mock_session.session_id = self._config["session_id"]
        mock_session.llm_client = self._mock_llm_client

        return mock_session

    def get_config(self) -> Dict[str, Any]:
        """
        Get the built configuration without creating a session.

        Returns:
            Configuration dict
        """
        return {
            **self._config,
            "player_configs": self._player_configs,
            "enemy_templates": self._enemy_templates,
            "scenario_override": self._scenario_override,
            "mechanics_overrides": self._mechanics_overrides
        }


class CharacterBuilder:
    """
    Builder for creating test character states.

    Usage:
        char = CharacterBuilder()
            .with_name("TestHero")
            .with_class("Witch")
            .with_skill("Occult", 4)
            .with_void(3)
            .build()
    """

    def __init__(self):
        """Initialize with default character."""
        self._char = {
            "name": "TestCharacter",
            "role": "player",
            "character_class": "Witch",
            "level": 1,
            "max_energy": 10,
            "current_energy": 10,
            "max_health": 15,
            "current_health": 15,
            "void": 0,
            "stress": 0,
            "skills": {},
            "bonds": [],
            "inventory": [],
            "conditions": [],
            "background": "A test character"
        }

    def with_name(self, name: str) -> "CharacterBuilder":
        """Set character name."""
        self._char["name"] = name
        return self

    def with_class(self, char_class: str) -> "CharacterBuilder":
        """Set character class."""
        self._char["character_class"] = char_class
        return self

    def with_level(self, level: int) -> "CharacterBuilder":
        """Set character level."""
        self._char["level"] = level
        return self

    def with_health(self, current: int, max_hp: Optional[int] = None) -> "CharacterBuilder":
        """Set health values."""
        self._char["current_health"] = current
        if max_hp:
            self._char["max_health"] = max_hp
        return self

    def with_energy(self, current: int, max_energy: Optional[int] = None) -> "CharacterBuilder":
        """Set energy values."""
        self._char["current_energy"] = current
        if max_energy:
            self._char["max_energy"] = max_energy
        return self

    def with_void(self, void: int) -> "CharacterBuilder":
        """Set void level."""
        self._char["void"] = void
        return self

    def with_stress(self, stress: int) -> "CharacterBuilder":
        """Set stress level."""
        self._char["stress"] = stress
        return self

    def with_skill(self, skill_name: str, level: int) -> "CharacterBuilder":
        """Add a skill."""
        self._char["skills"][skill_name] = level
        return self

    def with_bond(self, target_name: str, level: int) -> "CharacterBuilder":
        """Add a bond."""
        self._char["bonds"].append({"name": target_name, "level": level})
        return self

    def with_item(self, item_name: str) -> "CharacterBuilder":
        """Add an inventory item."""
        self._char["inventory"].append(item_name)
        return self

    def with_condition(self, condition: str) -> "CharacterBuilder":
        """Add a condition."""
        self._char["conditions"].append(condition)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the character dict."""
        return self._char.copy()


def create_minimal_session_config(
    num_players: int = 2,
    enable_enemies: bool = False,
    max_rounds: int = 3
) -> Dict[str, Any]:
    """
    Create a minimal session config for quick testing.

    Args:
        num_players: Number of players
        enable_enemies: Whether to enable enemies
        max_rounds: Maximum rounds

    Returns:
        Session config dict
    """
    return {
        "num_players": num_players,
        "max_rounds": max_rounds,
        "scenario_theme": "test",
        "player_names": [f"TestPlayer{i+1}" for i in range(num_players)],
        "enable_enemies": enable_enemies,
        "max_enemies": 1 if enable_enemies else 0,
        "llm_provider": "mock",
        "session_id": str(uuid.uuid4())
    }
