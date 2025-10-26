"""
PettingZoo AEC environment wrapper for Aeonisk multi-agent sessions.

Provides a standardized multi-agent RL interface for the Aeonisk YAGS system.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
import numpy as np
from gymnasium import spaces
from pettingzoo import AECEnv
from pettingzoo.utils import agent_selector, wrappers

from .session import SelfPlayingSession
from .success_metrics import SessionSuccessTracker

logger = logging.getLogger(__name__)


class AeoniskEnv(AECEnv):
    """
    PettingZoo AEC (Agent Environment Cycle) environment for Aeonisk.

    This wraps a SelfPlayingSession to provide a standardized multi-agent RL interface.
    Agents take turns acting, with rewards based on mission success and clock progress.

    Observation Space:
        Dict space containing:
        - character_stats: Box with health, void, soulcredit
        - clocks: Box with clock progress ratios
        - enemy_count: Discrete number of active enemies
        - round_number: Current round

    Action Space:
        Discrete space mapping to action types:
        0: Attack (combat)
        1: Defend/Support
        2: Investigate/Interact
        3: Move/Tactical
        4: Special/Void ability

    Rewards:
        - +10 for mission success (all clocks complete)
        - +1 per clock completed
        - -10 for mission failure (TPK or timeout)
        - -1 per character death
        - +0.1 per successful action
    """

    metadata = {
        'render_modes': ['human', 'ansi'],
        'name': 'aeonisk_v0',
        'is_parallelizable': False,
    }

    def __init__(
        self,
        config_path: str,
        max_rounds: int = 20,
        random_seed: Optional[int] = None,
        render_mode: Optional[str] = None
    ):
        """
        Initialize the Aeonisk environment.

        Args:
            config_path: Path to session configuration JSON
            max_rounds: Maximum rounds before episode ends
            random_seed: Random seed for reproducibility
            render_mode: Rendering mode ('human' or 'ansi')
        """
        super().__init__()

        self.config_path = config_path
        self.max_rounds = max_rounds
        self.random_seed = random_seed
        self.render_mode = render_mode

        # Session state
        self.session: Optional[SelfPlayingSession] = None
        self.success_tracker: Optional[SessionSuccessTracker] = None
        self._session_running = False

        # Agent tracking
        self.possible_agents: List[str] = []  # Will be populated from config
        self.agents: List[str] = []
        self._agent_selector = None

        # Spaces (will be initialized in reset())
        self._observation_spaces: Dict[str, spaces.Space] = {}
        self._action_spaces: Dict[str, spaces.Space] = {}

        # Episode state
        self._cumulative_rewards: Dict[str, float] = {}
        self._current_round = 0
        self._episode_ended = False

        # Action mapping
        self.action_mapping = {
            0: "ATTACK",
            1: "DEFEND",
            2: "INVESTIGATE",
            3: "MOVE",
            4: "SPECIAL"
        }

        # Initialize from config to get agent list
        self._initialize_from_config()

    def _initialize_from_config(self):
        """Initialize agent list and spaces from config."""
        import json
        from pathlib import Path

        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        with open(config_file) as f:
            config = json.load(f)

        # Extract player agent names
        self.possible_agents = [
            agent['name']
            for agent in config.get('agents', {}).get('players', [])
        ]

        # Define observation and action spaces for each agent
        # Observation: character stats + clock states + context
        max_clocks = 10  # Maximum number of clocks we expect
        obs_space = spaces.Dict({
            'character_stats': spaces.Box(
                low=np.array([0, 0, -10, 0]),  # health, void, soulcredit, round
                high=np.array([20, 10, 100, self.max_rounds]),
                dtype=np.float32
            ),
            'clocks': spaces.Box(
                low=0.0,
                high=2.0,  # Clocks can overflow
                shape=(max_clocks,),
                dtype=np.float32
            ),
            'enemy_count': spaces.Discrete(50),  # Max 50 enemies
            'party_health': spaces.Box(
                low=0.0,
                high=1.0,  # Ratio of party health
                shape=(1,),
                dtype=np.float32
            )
        })

        # Action: discrete action types
        action_space = spaces.Discrete(len(self.action_mapping))

        # Assign to all agents
        for agent in self.possible_agents:
            self._observation_spaces[agent] = obs_space
            self._action_spaces[agent] = action_space

    @property
    def observation_space(self) -> spaces.Space:
        """Get observation space for current agent."""
        return self._observation_spaces.get(self.agent_selection, spaces.Space())

    @property
    def action_space(self) -> spaces.Space:
        """Get action space for current agent."""
        return self._action_spaces.get(self.agent_selection, spaces.Space())

    def observation_space_func(self, agent: str) -> spaces.Space:
        """Get observation space for specific agent."""
        return self._observation_spaces.get(agent, spaces.Space())

    def action_space_func(self, agent: str) -> spaces.Space:
        """Get action space for specific agent."""
        return self._action_spaces.get(agent, spaces.Space())

    def observe(self, agent: str) -> Dict[str, Any]:
        """
        Return observation for a specific agent.

        Args:
            agent: Agent name

        Returns:
            Observation dict with character stats, clocks, enemy count, etc.
        """
        if not self.session or not self._session_running:
            # Return default observation if session not started
            return self._get_default_observation()

        # Get character state from session
        char_state = self._get_character_state(agent)
        clock_states = self._get_clock_states()
        enemy_count = self._get_enemy_count()
        party_health = self._get_party_health_ratio()

        # Build observation
        obs = {
            'character_stats': np.array([
                char_state.get('health', 10),
                char_state.get('void', 0),
                char_state.get('soulcredit', 0),
                self._current_round
            ], dtype=np.float32),
            'clocks': clock_states,
            'enemy_count': enemy_count,
            'party_health': np.array([party_health], dtype=np.float32)
        }

        return obs

    def _get_default_observation(self) -> Dict[str, Any]:
        """Return default observation when session not active."""
        return {
            'character_stats': np.zeros(4, dtype=np.float32),
            'clocks': np.zeros(10, dtype=np.float32),
            'enemy_count': 0,
            'party_health': np.array([1.0], dtype=np.float32)
        }

    def _get_character_state(self, agent_name: str) -> Dict[str, Any]:
        """Get character state from session."""
        if not self.session or not hasattr(self.session, 'shared_state'):
            return {'health': 10, 'void': 0, 'soulcredit': 0}

        # Try to get from mechanics engine
        mechanics = self.session.shared_state.get_mechanics_engine()
        if mechanics and hasattr(mechanics, 'character_states'):
            char_state = mechanics.character_states.get(agent_name, {})
            return {
                'health': char_state.get('health', 10),
                'void': char_state.get('void', 0),
                'soulcredit': char_state.get('soulcredit', 0)
            }

        return {'health': 10, 'void': 0, 'soulcredit': 0}

    def _get_clock_states(self) -> np.ndarray:
        """Get clock progress as array."""
        if not self.session or not hasattr(self.session, 'shared_state'):
            return np.zeros(10, dtype=np.float32)

        mechanics = self.session.shared_state.get_mechanics_engine()
        if mechanics and hasattr(mechanics, 'scene_clocks'):
            clocks = mechanics.scene_clocks
            clock_progress = [
                c.progress_ratio for c in clocks.values()
            ]
            # Pad to 10 elements
            clock_progress = clock_progress[:10]  # Trim if too many
            clock_progress += [0.0] * (10 - len(clock_progress))  # Pad if too few
            return np.array(clock_progress, dtype=np.float32)

        return np.zeros(10, dtype=np.float32)

    def _get_enemy_count(self) -> int:
        """Get number of active enemies."""
        if not self.session or not hasattr(self.session, 'shared_state'):
            return 0

        enemy_combat = self.session.shared_state.enemy_combat
        if enemy_combat and hasattr(enemy_combat, 'active_enemies'):
            return len(enemy_combat.active_enemies)

        return 0

    def _get_party_health_ratio(self) -> float:
        """Get party health as ratio of max health."""
        if not self.session or not hasattr(self.session, 'shared_state'):
            return 1.0

        mechanics = self.session.shared_state.get_mechanics_engine()
        if mechanics and hasattr(mechanics, 'character_states'):
            total_health = 0
            max_health = 0
            for char_state in mechanics.character_states.values():
                total_health += char_state.get('health', 0)
                max_health += char_state.get('max_health', 10)

            return total_health / max_health if max_health > 0 else 0.0

        return 1.0

    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Reset the environment for a new episode.

        Args:
            seed: Random seed
            options: Additional options

        Returns:
            Initial observation for first agent
        """
        if seed is not None:
            self.random_seed = seed

        # Clean up previous session
        if self.session and self._session_running:
            self._stop_session()

        # Initialize new session
        self.session = SelfPlayingSession(
            config_path=self.config_path,
            random_seed=self.random_seed
        )

        # Initialize success tracker
        self.success_tracker = SessionSuccessTracker(
            self.session.session_id,
            self.random_seed
        )

        # Reset episode state
        self.agents = self.possible_agents.copy()
        self._agent_selector = agent_selector(self.agents)
        self.agent_selection = self._agent_selector.next()

        self._cumulative_rewards = {agent: 0.0 for agent in self.agents}
        self.rewards = {agent: 0.0 for agent in self.agents}
        self.terminations = {agent: False for agent in self.agents}
        self.truncations = {agent: False for agent in self.agents}
        self.infos = {agent: {} for agent in self.agents}

        self._current_round = 0
        self._episode_ended = False
        self._session_running = True

        # Start session (async - we'll run steps synchronously)
        # Note: For now, we treat actions as high-level hints
        # The actual LLM agents still make decisions

        return self.observe(self.agent_selection)

    def step(self, action: int):
        """
        Execute one step of the environment.

        Args:
            action: Discrete action from current agent
        """
        if self._episode_ended:
            return

        agent = self.agent_selection

        # Map action to action type hint
        action_type = self.action_mapping.get(action, "ATTACK")

        # For now, we don't directly control LLM agents' actions
        # Instead, we advance the session by one round
        # This is a limitation - full integration would require modifying
        # the agent prompts to accept action hints

        # Advance round (simplified - real implementation would run session loop)
        self._current_round += 1
        self.success_tracker.increment_round()

        # Update success tracker with clock states
        if self.session and hasattr(self.session, 'shared_state'):
            mechanics = self.session.shared_state.get_mechanics_engine()
            if mechanics and hasattr(mechanics, 'scene_clocks'):
                mission_complete = self.success_tracker.update_clocks(mechanics.scene_clocks)

                if mission_complete:
                    # Mission success!
                    for a in self.agents:
                        self.rewards[a] = 10.0
                        self.terminations[a] = True
                    self._episode_ended = True

        # Check termination conditions
        if self._current_round >= self.max_rounds:
            # Timeout - mission failed
            for a in self.agents:
                self.rewards[a] = -10.0 if not self.terminations[a] else self.rewards[a]
                self.truncations[a] = True
            self._episode_ended = True

        # Check if all characters dead (TPK)
        party_health = self._get_party_health_ratio()
        if party_health == 0.0:
            for a in self.agents:
                self.rewards[a] = -10.0
                self.terminations[a] = True
            self._episode_ended = True

        # Update cumulative rewards
        self._cumulative_rewards[agent] += self.rewards[agent]

        # Move to next agent
        if not self._episode_ended:
            self.agent_selection = self._agent_selector.next()

    def _stop_session(self):
        """Stop the current session."""
        if self.session:
            self.session.running = False
            self._session_running = False

    def render(self):
        """Render the environment."""
        if self.render_mode == 'human' or self.render_mode == 'ansi':
            output = [
                f"\n=== Aeonisk Environment (Round {self._current_round}) ===",
                f"Active Agent: {self.agent_selection}",
                f"Clocks: {self._get_clock_states()[:5]}...",
                f"Enemies: {self._get_enemy_count()}",
                f"Party Health: {self._get_party_health_ratio():.1%}",
                "="*50
            ]
            print("\n".join(output))

    def close(self):
        """Clean up the environment."""
        if self._session_running:
            self._stop_session()


# Wrapper for PettingZoo compatibility checks
def env(**kwargs):
    """Create wrapped environment for PettingZoo API."""
    env = AeoniskEnv(**kwargs)
    env = wrappers.OrderEnforcingWrapper(env)
    return env
