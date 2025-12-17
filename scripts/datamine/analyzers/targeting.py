"""
Targeting analyzer - detect targeting errors, unknown targets, and validation issues.

Metrics:
- Target ID format issues (bracketed, names instead of IDs)
- Unknown/missing defenders
- Environment targets
- Unknown weapons
- LLM validation warnings
"""

from collections import Counter, defaultdict
from typing import Dict, Any, Set, List
import re

from .base import BaseAnalyzer, AnalyzerResult


class TargetingAnalyzer(BaseAnalyzer):
    """
    Analyze targeting patterns and detect errors in combat/action events.

    Processes action_declaration, combat_action, action_resolution, and
    structured_output_metrics to identify:
    - Malformed target IDs (bracketed, names instead of IDs)
    - Unknown/missing targets
    - Weapon naming issues
    - Validation warnings related to targeting
    """

    @property
    def name(self) -> str:
        return "targeting"

    @property
    def event_types(self) -> Set[str]:
        return {
            "action_declaration",
            "combat_action",
            "action_resolution",
            "structured_output_metrics",
        }

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Reset all accumulated state."""
        # Target ID pattern tracking
        self._target_patterns: Counter = Counter()
        self._bracketed_targets: List[Dict[str, Any]] = []
        self._name_as_target: List[Dict[str, Any]] = []
        self._env_targets: List[Dict[str, Any]] = []
        self._unknown_targets: List[Dict[str, Any]] = []

        # Defender tracking from combat_action
        self._defender_patterns: Counter = Counter()
        self._missing_defenders: List[Dict[str, Any]] = []

        # Weapon tracking
        self._weapon_patterns: Counter = Counter()
        self._unknown_weapons: List[Dict[str, Any]] = []

        # Validation warnings
        self._validation_warnings: Counter = Counter()
        self._target_validation_issues: List[Dict[str, Any]] = []

        self._event_count = 0
        self._session_count = 0

    def process_event(self, event: Dict[str, Any]) -> None:
        """Process targeting-related events."""
        event_type = event.get("event_type")

        if event_type == "action_declaration":
            self._process_action_declaration(event)
        elif event_type == "combat_action":
            self._process_combat_action(event)
        elif event_type == "action_resolution":
            self._process_action_resolution(event)
        elif event_type == "structured_output_metrics":
            self._process_validation_metrics(event)

    def _process_action_declaration(self, event: Dict[str, Any]) -> None:
        """Process action_declaration for target patterns."""
        self._event_count += 1

        action = event.get("action", {})
        target = action.get("target", "")
        character = event.get("character_name", "unknown")
        session = event.get("session", "")
        round_num = event.get("round", 0)

        if not target:
            self._target_patterns["no_target"] += 1
            return

        # Check target format
        if target.startswith("tgt_"):
            self._target_patterns["valid_tgt_id"] += 1
        elif target.startswith("[tgt_"):
            # Bracketed target ID - parsing issue
            self._target_patterns["bracketed_tgt_id"] += 1
            if len(self._bracketed_targets) < 50:
                self._bracketed_targets.append({
                    "target": target,
                    "character": character,
                    "session": session[:8] if session else "",
                    "round": round_num,
                })
        elif target.startswith("env_"):
            # Environment target
            self._target_patterns["env_target"] += 1
            if len(self._env_targets) < 50:
                self._env_targets.append({
                    "target": target,
                    "character": character,
                    "session": session[:8] if session else "",
                    "round": round_num,
                })
        elif "PC" in target or "Enemy" in target:
            # Position-based target (Near-PC, Far-Enemy, etc)
            self._target_patterns["position_target"] += 1
        elif re.match(r"^(player_|enemy_|npc_)", target):
            # Valid agent ID format
            self._target_patterns["valid_agent_id"] += 1
        else:
            # Likely a character name used as target
            self._target_patterns["name_as_target"] += 1
            if len(self._name_as_target) < 50:
                self._name_as_target.append({
                    "target": target,
                    "character": character,
                    "session": session[:8] if session else "",
                    "round": round_num,
                })

    def _process_combat_action(self, event: Dict[str, Any]) -> None:
        """Process combat_action for defender and weapon patterns."""
        self._event_count += 1

        # Check defender
        defender = event.get("defender", {})
        defender_id = defender.get("id") if isinstance(defender, dict) else None
        attacker = event.get("attacker", {})
        attacker_name = attacker.get("name", "unknown") if isinstance(attacker, dict) else "unknown"
        session = event.get("session", "")
        round_num = event.get("round", 0)

        if not defender_id:
            self._defender_patterns["missing_defender"] += 1
            if len(self._missing_defenders) < 50:
                self._missing_defenders.append({
                    "attacker": attacker_name,
                    "session": session[:8] if session else "",
                    "round": round_num,
                })
        elif defender_id.startswith("player_"):
            self._defender_patterns["valid_player_id"] += 1
        elif defender_id.startswith("enemy_"):
            self._defender_patterns["valid_enemy_id"] += 1
        elif defender_id.startswith("tgt_"):
            self._defender_patterns["tgt_id"] += 1
        elif defender_id.startswith("npc_"):
            self._defender_patterns["npc_id"] += 1
        else:
            self._defender_patterns["other"] += 1

        # Check weapon
        weapon = event.get("weapon", "")
        if weapon in ("unknown", "Unknown Weapon", None, ""):
            self._weapon_patterns["unknown"] += 1
            if len(self._unknown_weapons) < 50:
                self._unknown_weapons.append({
                    "attacker": attacker_name,
                    "defender": defender.get("name", "unknown") if isinstance(defender, dict) else "unknown",
                    "session": session[:8] if session else "",
                    "round": round_num,
                })
        else:
            self._weapon_patterns["known"] += 1

    def _process_action_resolution(self, event: Dict[str, Any]) -> None:
        """Process action_resolution for target patterns."""
        self._event_count += 1

        # Check damage target
        effects = event.get("effects", {})
        damage = effects.get("damage", {})
        target = damage.get("target") if isinstance(damage, dict) else None

        if target:
            if target.startswith("tgt_"):
                self._target_patterns["resolution_valid_tgt"] += 1
            else:
                self._target_patterns["resolution_other_target"] += 1

    def _process_validation_metrics(self, event: Dict[str, Any]) -> None:
        """Process structured_output_metrics for validation warnings."""
        self._event_count += 1

        warnings = event.get("validation_warnings", [])
        session = event.get("session", "")
        round_num = event.get("round", 0)

        for warning in warnings:
            self._validation_warnings[warning] += 1

            # Check for target-related warnings
            warning_lower = warning.lower()
            if any(kw in warning_lower for kw in ["target", "defender", "invalid", "unknown", "not found"]):
                if len(self._target_validation_issues) < 100:
                    self._target_validation_issues.append({
                        "warning": warning[:100],
                        "session": session[:8] if session else "",
                        "round": round_num,
                    })

    def get_result(self) -> AnalyzerResult:
        """Produce final result with targeting statistics."""
        warnings = []

        # Calculate totals
        total_declarations = sum(self._target_patterns.values())
        total_combat_actions = sum(self._defender_patterns.values())

        # Target ID issues
        bracketed_count = self._target_patterns.get("bracketed_tgt_id", 0)
        name_as_target_count = self._target_patterns.get("name_as_target", 0)
        env_count = self._target_patterns.get("env_target", 0)

        if bracketed_count > 0:
            warnings.append(f"Found {bracketed_count} bracketed target IDs ([tgt_xxx]) - parsing issue")
        if name_as_target_count > 0:
            warnings.append(f"Found {name_as_target_count} character names used as targets instead of IDs")
        if env_count > 0:
            warnings.append(f"Found {env_count} environment targets (env_xxx)")

        # Weapon issues
        unknown_weapon_count = self._weapon_patterns.get("unknown", 0)
        known_weapon_count = self._weapon_patterns.get("known", 0)
        if unknown_weapon_count > 0 and total_combat_actions > 0:
            pct = (unknown_weapon_count / total_combat_actions) * 100
            if pct > 10:
                warnings.append(f"{pct:.1f}% of combat actions have unknown weapons")

        # Missing defenders
        missing_defender_count = self._defender_patterns.get("missing_defender", 0)
        if missing_defender_count > 0:
            warnings.append(f"Found {missing_defender_count} combat actions with missing defender")

        # Target pattern breakdown
        target_breakdown = []
        for pattern, count in self._target_patterns.most_common():
            if count > 0:
                pct = (count / total_declarations * 100) if total_declarations > 0 else 0
                target_breakdown.append({
                    "pattern": pattern,
                    "count": count,
                    "percentage": round(pct, 1),
                })

        # Defender pattern breakdown
        defender_breakdown = []
        for pattern, count in self._defender_patterns.most_common():
            if count > 0:
                pct = (count / total_combat_actions * 100) if total_combat_actions > 0 else 0
                defender_breakdown.append({
                    "pattern": pattern,
                    "count": count,
                    "percentage": round(pct, 1),
                })

        # Validation warning breakdown
        validation_breakdown = []
        for warning, count in self._validation_warnings.most_common(15):
            validation_breakdown.append({
                "warning": warning[:80],
                "count": count,
            })

        return AnalyzerResult(
            analyzer_name=self.name,
            session_count=self._session_count,
            event_count=self._event_count,
            metrics={
                # Summary stats
                "total_declarations": total_declarations,
                "total_combat_actions": total_combat_actions,
                # Target issues
                "bracketed_targets": bracketed_count,
                "name_as_target": name_as_target_count,
                "env_targets": env_count,
                # Weapon issues
                "unknown_weapons": unknown_weapon_count,
                "known_weapons": known_weapon_count,
                # Missing defenders
                "missing_defenders": missing_defender_count,
                # Breakdowns
                "target_patterns": target_breakdown,
                "defender_patterns": defender_breakdown,
                "validation_warnings": validation_breakdown,
                # Sample issues (for debugging)
                "sample_bracketed": self._bracketed_targets[:10],
                "sample_name_as_target": self._name_as_target[:10],
                "sample_env_targets": self._env_targets[:10],
                "sample_unknown_weapons": self._unknown_weapons[:10],
                "sample_validation_issues": self._target_validation_issues[:10],
            },
            warnings=warnings,
        )
