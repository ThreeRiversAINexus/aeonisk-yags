"""
Awareness filtering for agent narrations.

Controls which agents can see which action outcomes, enabling stealth,
secrets, and hidden information mechanics.

Philosophy: The DM controls visibility via the `aware_agents` field in
ActionResolution. Empty list = public (everyone sees). Populated list =
only those agents see the narration.
"""

from dataclasses import dataclass, field
from typing import List, Union


@dataclass
class NarrationEntry:
    """
    A narration with awareness metadata.

    Attributes:
        text: The narration text (e.g., "[Echo] Echo slips past the guard")
        aware_agents: List of agent IDs who can see this narration.
                     Empty list = public (all agents see it).
                     Populated = only those agents see it.
    """
    text: str
    aware_agents: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.text


def filter_narrations_for_agent(
    agent_id: str,
    narrations: List[Union[str, NarrationEntry]]
) -> List[Union[str, NarrationEntry]]:
    """
    Filter narrations to only those visible to the specified agent.

    Args:
        agent_id: The agent requesting narrations (e.g., "npc_guard", "enemy_grunt_1")
        narrations: List of narrations (strings or NarrationEntry objects)

    Returns:
        Filtered list containing only narrations the agent can see.

    Visibility rules:
        - Plain strings (backwards compatibility): Always visible (public)
        - NarrationEntry with empty aware_agents: Always visible (public)
        - NarrationEntry with populated aware_agents: Only visible if agent_id in list

    Examples:
        >>> entry = NarrationEntry("[Echo] Stealth success", ["dm", "player_echo"])
        >>> filter_narrations_for_agent("npc_guard", [entry])
        []  # Guard can't see stealth success

        >>> filter_narrations_for_agent("player_echo", [entry])
        [NarrationEntry(...)]  # Echo can see their own action
    """
    filtered = []

    for narration in narrations:
        if isinstance(narration, str):
            # Backwards compatibility: plain strings are public
            filtered.append(narration)
        elif isinstance(narration, NarrationEntry):
            if not narration.aware_agents:
                # Empty list = public, everyone sees
                filtered.append(narration)
            elif agent_id in narration.aware_agents:
                # Agent is in the awareness list
                filtered.append(narration)
            # else: Agent not in awareness list, skip this narration
        else:
            # Unknown type, include for safety (shouldn't happen)
            filtered.append(narration)

    return filtered


def is_agent_aware(agent_id: str, aware_agents: List[str]) -> bool:
    """
    Check if an agent should be aware of an action.

    Args:
        agent_id: The agent to check
        aware_agents: List of aware agent IDs (empty = public)

    Returns:
        True if agent should see the narration, False otherwise.
    """
    if not aware_agents:
        # Empty list = public, everyone is aware
        return True
    return agent_id in aware_agents


def get_hidden_agent_ids(agents: List) -> set:
    """
    Get the set of agent IDs that are currently hidden (Spec 05).

    Checks the is_hidden attribute on each agent. Works with any agent type
    (AIPlayerAgent, EnemyAgent, NPCAgent) as long as they have agent_id
    and is_hidden attributes.

    Args:
        agents: List of agent instances (mixed types allowed)

    Returns:
        Set of agent_id strings for agents where is_hidden is True
    """
    hidden = set()
    for agent in agents:
        agent_id = getattr(agent, 'agent_id', None)
        if agent_id and getattr(agent, 'is_hidden', False):
            hidden.add(agent_id)
    return hidden
