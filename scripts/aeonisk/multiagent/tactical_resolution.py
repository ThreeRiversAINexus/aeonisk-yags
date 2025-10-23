"""
Tactical Resolution Phase Manager

Handles declare/resolve cycle with proper action invalidation.
Tracks state changes during resolution phase to handle scenarios where
earlier actors claim resources (tokens), eliminate targets, or change
battlefield conditions that invalidate later actors' declared actions.

Critical Rule: Declaration is INTENTION, Resolution is REALITY.

Example Scenario:
    Declaration Phase (ascending init - 12, 18, 22, 28):
    - Enemy B (12): "Claim Cover token"
    - Player A (18): "Claim Cover token"
    - Enemy A (22): "Attack Player A"
    - Echo (28): "Attack Enemy A"

    Resolution Phase (descending init - 28, 22, 18, 12):
    1. Echo (28): Attacks Enemy A → Enemy A killed
    2. Enemy A (22): DEAD - action invalidated
    3. Player A (18): Claims Cover token → SUCCESS
    4. Enemy B (12): Tries to claim Cover → TAKEN - action fails

Author: Three Rivers AI Nexus
Date: 2025-10-22
"""

import logging
from typing import Dict, Set, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# RESOLUTION STATE TRACKING
# =============================================================================

@dataclass
class ResolutionState:
    """
    Tracks state changes during resolution phase.

    As actions resolve in descending initiative order, this tracks:
    - Which tactical tokens have been claimed
    - Which combatants have been defeated
    - Which positions have changed
    - Other state mutations that affect later actions
    """

    # Tactical token tracking
    claimed_tokens: Dict[str, str] = field(default_factory=dict)  # {token_name: claimant_id}

    # Defeated combatants
    defeated: Set[str] = field(default_factory=set)  # Set of agent_ids

    # Position changes (for opportunity attacks, breakaway, etc.)
    position_changes: Dict[str, str] = field(default_factory=dict)  # {agent_id: new_position}

    # Action results (for logging/narration)
    action_results: List[Dict[str, Any]] = field(default_factory=list)

    def claim_token(self, token_name: str, claimant_id: str) -> bool:
        """
        Attempt to claim a tactical token.

        Args:
            token_name: Name of token to claim
            claimant_id: Agent attempting to claim

        Returns:
            True if successfully claimed, False if already taken
        """
        if token_name in self.claimed_tokens:
            logger.debug(f"{claimant_id} tried to claim {token_name}, but already claimed by {self.claimed_tokens[token_name]}")
            return False

        self.claimed_tokens[token_name] = claimant_id
        logger.debug(f"{claimant_id} claimed {token_name}")
        return True

    def mark_defeated(self, agent_id: str):
        """Mark combatant as defeated."""
        self.defeated.add(agent_id)
        logger.debug(f"{agent_id} marked as defeated")

    def is_defeated(self, agent_id: str) -> bool:
        """Check if combatant has been defeated during resolution."""
        return agent_id in self.defeated

    def record_position_change(self, agent_id: str, new_position: str):
        """Record position change during resolution."""
        self.position_changes[agent_id] = new_position

    def add_result(self, result: Dict[str, Any]):
        """Add action result to log."""
        self.action_results.append(result)

    def get_token_holder(self, token_name: str) -> Optional[str]:
        """Get who currently holds a token, if anyone."""
        return self.claimed_tokens.get(token_name)


# =============================================================================
# ACTION PREREQUISITE CHECKING
# =============================================================================

class ActionValidator:
    """
    Validates whether a declared action can still execute.

    During resolution phase, earlier actions may invalidate later actions:
    - Target was killed
    - Target moved out of range
    - Tactical token was claimed by someone else
    - Required resource no longer available
    """

    @staticmethod
    def can_attack(
        attacker_id: str,
        target_id: str,
        resolution_state: ResolutionState
    ) -> tuple[bool, Optional[str]]:
        """
        Check if attack can proceed.

        Returns:
            (can_proceed, failure_reason)
        """
        # Check if attacker is defeated
        if resolution_state.is_defeated(attacker_id):
            return False, "attacker_defeated"

        # Check if target is defeated
        if resolution_state.is_defeated(target_id):
            return False, "target_defeated"

        # Attack can proceed
        return True, None

    @staticmethod
    def can_claim_token(
        claimant_id: str,
        token_name: str,
        resolution_state: ResolutionState
    ) -> tuple[bool, Optional[str]]:
        """
        Check if token claim can proceed.

        Returns:
            (can_proceed, failure_reason)
        """
        # Check if claimant is defeated
        if resolution_state.is_defeated(claimant_id):
            return False, "claimant_defeated"

        # Check if token already claimed
        holder = resolution_state.get_token_holder(token_name)
        if holder and holder != claimant_id:
            return False, f"token_taken_by_{holder}"

        # Claim can proceed
        return True, None

    @staticmethod
    def can_move(
        mover_id: str,
        resolution_state: ResolutionState
    ) -> tuple[bool, Optional[str]]:
        """
        Check if movement can proceed.

        Returns:
            (can_proceed, failure_reason)
        """
        # Check if mover is defeated
        if resolution_state.is_defeated(mover_id):
            return False, "mover_defeated"

        # Movement can proceed
        return True, None


# =============================================================================
# INVALIDATION MESSAGES
# =============================================================================

def generate_invalidation_message(
    agent_name: str,
    action_type: str,
    failure_reason: str,
    target_name: Optional[str] = None
) -> str:
    """
    Generate narrative message for invalidated action.

    Args:
        agent_name: Name of agent whose action failed
        action_type: Type of action (attack, claim_token, etc.)
        failure_reason: Why it failed
        target_name: Target of action (if applicable)

    Returns:
        Narrative message explaining invalidation
    """
    if failure_reason == "attacker_defeated":
        return f"❌ {agent_name} cannot act - already defeated earlier in the round"

    elif failure_reason == "target_defeated":
        return f"❌ {agent_name}'s attack fails - {target_name} was already defeated by a faster actor"

    elif failure_reason.startswith("token_taken_by_"):
        holder = failure_reason.replace("token_taken_by_", "")
        return f"❌ {agent_name} cannot claim token - {holder} claimed it first (higher initiative)"

    elif failure_reason == "claimant_defeated":
        return f"❌ {agent_name} cannot claim token - defeated before action resolved"

    elif failure_reason == "mover_defeated":
        return f"❌ {agent_name} cannot move - defeated before action resolved"

    else:
        return f"❌ {agent_name}'s {action_type} action failed: {failure_reason}"


# =============================================================================
# DECLARE/RESOLVE CYCLE DOCUMENTATION
# =============================================================================

DECLARE_RESOLVE_EXPLANATION = """
## CRITICAL: Declare/Resolve Cycle

**Declaration Phase (ascending initiative - slowest first):**
- You declare your INTENDED action
- No rolls made, no effects resolved
- Other combatants declare after you (if they're faster)

**Resolution Phase (descending initiative - fastest first):**
- Faster actors resolve FIRST
- Your declared action may FAIL if:
  - Target was killed by a faster actor
  - Tactical token was claimed by a faster actor
  - Battlefield conditions changed

**Example:**
```
You (initiative 12) declare: "Claim Cover token"
Player A (initiative 18) declares: "Claim Cover token"

Resolution:
→ Player A (18) acts FIRST and claims Cover token
→ You (12) act SECOND - token already taken, action FAILS
```

**Tactical Implications:**
- Higher initiative = more reliable actions
- Declare backup plans in reasoning
- Accept uncertainty - declarations are intentions, not guarantees
- Coordinate with allies via shared intel
"""


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    'ResolutionState',
    'ActionValidator',
    'generate_invalidation_message',
    'DECLARE_RESOLVE_EXPLANATION'
]
