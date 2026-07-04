#!/usr/bin/env python3
"""
Prompt Evaluation Harness

Replays DM resolution LLM calls from existing sessions with a swapped prompt module,
enabling prompt iteration in minutes instead of hours.

Pipeline: JSONL sessions → extract DM llm_call events → swap one YAML module
in system prompt → replay via LLM → parse response → score & compare → report

Usage:
    # Scan what cases are available
    python scripts/prompt_eval_harness.py \
        --swap-module prompts/dm/dm_resolution_combat_v3.yaml --scan-only

    # Replay against a single model
    python scripts/prompt_eval_harness.py \
        --swap-module prompts/dm/dm_resolution_combat_v3.yaml \
        --models gpt-5-mini --max-cases 10

    # Full evaluation with proxy
    python scripts/prompt_eval_harness.py \
        --swap-module prompts/dm/dm_resolution_combat_v3.yaml \
        --models gpt-5-mini deepseek-ai/DeepSeek-V3.2 \
        --action-type combat --intent-filter suppress \
        --scorers suppression_table damage_comparison \
        --proxy http://localhost:8000 --batch \
        --output results/v3_eval.jsonl --report results/v3_report.txt

    # Self-judging iteration
    python scripts/prompt_eval_harness.py \
        --swap-module prompts/dm/dm_resolution_combat_v3.yaml \
        --self-judge --goal-file goals/suppress_goals.yaml \
        --judge-model claude-sonnet-4-5 --max-iterations 5
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import hashlib
import copy
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Tuple, Set

import yaml
from dotenv import load_dotenv

# Add project path for imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
MULTIAGENT_DIR = SCRIPT_DIR / "aeonisk" / "multiagent"
sys.path.insert(0, str(SCRIPT_DIR))

# Load environment variables (.env in scripts/aeonisk/ first, then project root)
_dotenv_path = SCRIPT_DIR / "aeonisk" / ".env"
if _dotenv_path.exists():
    load_dotenv(_dotenv_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

# Default session directories for the lethality experiment
DEFAULT_SESSION_DIRS = [
    Path.home() / "Coding" / "aeonisk-v1" / "lethal_intent_mismatch" / "control",
    Path.home() / "Coding" / "aeonisk-v1" / "lethal_intent_mismatch" / "treatment_v1",
    Path.home() / "Coding" / "aeonisk-yags" / "multiagent_output" / "lethality_experiment" / "treatment_v2",
]

DM_PROMPTS_DIR = MULTIAGENT_DIR / "prompts" / "claude" / "en" / "dm"

def parse_model_spec(spec: str) -> Tuple[str, str]:
    """
    Parse a provider:model specification string.

    Format: "provider:model" (e.g., "openai:gpt-5-mini", "deepinfra:deepseek-ai/DeepSeek-V3.2")

    Returns:
        (provider, model) tuple
    """
    if ":" not in spec:
        raise ValueError(
            f"Invalid model spec '{spec}'. Use 'provider:model' format "
            f"(e.g., 'openai:gpt-5-mini', 'anthropic:claude-sonnet-4-5', "
            f"'deepinfra:deepseek-ai/DeepSeek-V3.2', 'grok:grok-4-latest')"
        )
    provider, model = spec.split(":", 1)
    if not provider or not model:
        raise ValueError(f"Invalid model spec '{spec}'. Both provider and model are required.")
    return provider, model


def _write_module_yaml(path: Path, module_name: str, content: str, description: str = "", version: str = "auto"):
    """Write a prompt module YAML with clean |- block scalar for the content field."""
    with open(path, "w") as f:
        f.write(f"version: {version}\n")
        f.write(f"module: {module_name}\n")
        if description:
            f.write(f"description: {description}\n")
        f.write("content: |-\n")
        for line in content.split("\n"):
            f.write(f"  {line}\n" if line else "\n")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    """A single DM resolution call extracted from a session for replay."""
    case_id: str              # unique ID: session_<hash>_<line>
    session_file: str         # source JSONL path
    condition: str            # control / treatment_v1 / treatment_v2 / unknown
    round_num: Optional[int]  # game round
    original_model: str       # model used in original session
    system_prompt: str        # full system prompt from original call
    user_prompt: str          # full user prompt from original call
    response_text: str        # original LLM response text
    action_type: Optional[str]    # combat, investigate, etc. (parsed from user prompt)
    player_action_text: Optional[str]  # raw player action description
    margin: Optional[int]     # roll margin (parsed from response)
    detected_modules: List[str] = field(default_factory=list)  # modules found in system prompt
    line_number: int = 0      # line number in JSONL file
    event_id: Optional[str] = None    # UUID from source llm_call event (stable across extractions)

    # From DM user prompt (regex extraction from WEAPON CONTEXT section)
    weapon_name: Optional[str] = None         # "Assault Rifle", "Shock Baton"
    weapon_damage_type: Optional[str] = None  # "wound", "stun" (lowercased)
    declared_target: Optional[str] = None     # "tgt_ic6o"

    # From player llm_call (event correlation — same round)
    player_intent: Optional[str] = None       # "Lay down suppressing fire to pin the thugs"

    # From original DM response (parsed via MechanicalExtractor)
    original_base_damage: Optional[int] = None
    original_damage_type: Optional[str] = None
    original_conditions: List[str] = field(default_factory=list)


@dataclass
class ReplayResult:
    """Result from replaying a single case with a specific model."""
    case_id: str
    condition: str
    round_num: Optional[int]
    action_type: Optional[str]
    original_model: str
    eval_model: str
    margin: Optional[int]
    original: Dict[str, Any]   # extracted mechanical fields from original
    replay: Dict[str, Any]     # extracted mechanical fields from replay
    scores: Dict[str, Any]     # scorer outputs
    latency_ms: float = 0.0
    error: Optional[str] = None
    player_action_text: Optional[str] = None
    # Optional full prompts for fine-tuning dataset
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    replay_response: Optional[str] = None


# ---------------------------------------------------------------------------
# ModuleSwapper
# ---------------------------------------------------------------------------

class ModuleSwapper:
    """Loads DM YAML modules and swaps them in system prompts."""

    def __init__(self, dm_prompts_dir: Optional[Path] = None):
        self.dm_prompts_dir = dm_prompts_dir or DM_PROMPTS_DIR
        self._modules: Dict[str, str] = {}  # module_name → content
        self._load_all_modules()

    def _load_all_modules(self):
        """Load content from all DM YAML modules."""
        if not self.dm_prompts_dir.exists():
            logger.warning(f"DM prompts directory not found: {self.dm_prompts_dir}")
            return
        for yaml_path in sorted(self.dm_prompts_dir.glob("*.yaml")):
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                module_name = data.get("module", yaml_path.stem)
                content = data.get("content", "")
                if content:
                    self._modules[module_name] = content
            except Exception as e:
                logger.warning(f"Failed to load {yaml_path}: {e}")
        logger.info(f"Loaded {len(self._modules)} DM prompt modules")

    @property
    def module_names(self) -> List[str]:
        return list(self._modules.keys())

    def detect_modules(self, system_prompt: str) -> List[str]:
        """Detect which modules are present in a system prompt via substring match."""
        found = []
        for name, content in self._modules.items():
            # Use first 200 chars as fingerprint (enough to be unique, handles minor trailing diffs)
            fingerprint = content[:200]
            if fingerprint in system_prompt:
                found.append(name)
        return found

    def load_replacement(self, yaml_path: str) -> Tuple[str, str]:
        """
        Load a replacement YAML module.

        Returns:
            (module_name, content) from the YAML file.
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Replacement module not found: {yaml_path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        module_name = data.get("module", path.stem)
        content = data.get("content", "")
        if not content:
            raise ValueError(f"Replacement module {yaml_path} has no 'content' field")
        return module_name, content

    def swap_module(self, system_prompt: str, module_name: str, new_content: str) -> str:
        """
        Replace a module's content in the system prompt.

        Finds the old module content as a substring and replaces it.
        Falls back to variant modules (e.g., _with_suppression ↔ base).
        Returns the modified system prompt, or raises ValueError if not found.
        """
        if module_name not in self._modules:
            raise ValueError(f"Module '{module_name}' not found. Available: {self.module_names}")

        old_content = self._modules[module_name]
        if old_content in system_prompt:
            return system_prompt.replace(old_content, new_content)

        # Try variant detection
        for variant_name in self._get_variants(module_name):
            if variant_name in self._modules:
                variant_content = self._modules[variant_name]
                if variant_content in system_prompt:
                    logger.debug(f"Swapping via variant '{variant_name}'")
                    return system_prompt.replace(variant_content, new_content)

        raise ValueError(
            f"Module '{module_name}' content not found in system prompt. "
            f"Detected modules: {self.detect_modules(system_prompt)}"
        )

    def _get_variants(self, module_name: str) -> List[str]:
        """Get variant module names to try if exact match fails."""
        variants = []
        # dm_resolution_combat ↔ dm_resolution_combat_with_suppression
        if module_name == "dm_resolution_combat":
            variants.append("dm_resolution_combat_with_suppression")
        elif module_name == "dm_resolution_combat_with_suppression":
            variants.append("dm_resolution_combat")
        return variants


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_weapon_context(round_events: List[dict]) -> Dict[str, Optional[str]]:
    """
    Extract weapon context from structured JSONL events, filtering to PC-only.

    Uses structured fields to identify PC events:
    - combat_action: attacker.id must start with "player_"
    - action_resolution: phase must be "adjudicate" (or absent for legacy compat)

    Enemy (enemy_*) and NPC (npc_*) events are excluded to prevent weapon
    metadata contamination (e.g. enemy wound pistol overwriting PC stun baton).

    Returns:
        Dict with keys: weapon_name, weapon_damage_type, declared_target
    """
    result: Dict[str, Optional[str]] = {
        "weapon_name": None,
        "weapon_damage_type": None,
        "declared_target": None,
    }

    for event in round_events:
        et = event.get("event_type")

        if et == "combat_action":
            # Filter: PC attackers only (attacker.id starts with "player_")
            attacker = event.get("attacker")
            if not isinstance(attacker, dict):
                continue
            attacker_id = attacker.get("id", "")
            if not attacker_id.startswith("player_"):
                continue

            if not result["weapon_name"] and event.get("weapon"):
                result["weapon_name"] = event["weapon"]
            damage = event.get("damage") or {}
            if not result["weapon_damage_type"] and damage.get("damage_type"):
                result["weapon_damage_type"] = damage["damage_type"].lower()

        elif et == "action_resolution":
            # Filter: PC phase only (adjudicate or absent for legacy)
            phase = event.get("phase")
            if phase is not None and phase != "adjudicate":
                continue

            context = event.get("context") or {}
            if not result["declared_target"] and context.get("target"):
                result["declared_target"] = context["target"]
            if not result["weapon_damage_type"]:
                for de in context.get("damage_effects") or []:
                    if isinstance(de, dict) and de.get("damage_type"):
                        result["weapon_damage_type"] = de["damage_type"].lower()
                        break

    return result


def _extract_original_outcome(response_text: str) -> Dict[str, Any]:
    """
    Extract base_damage, damage_type, and condition names from original DM response.

    Returns:
        Dict with keys: original_base_damage, original_damage_type, original_conditions
    """
    parsed = MechanicalExtractor.parse_response(response_text)
    effects = parsed.get("effects", {})

    damage_list = effects.get("damage", [])
    if isinstance(damage_list, dict):
        damage_list = [damage_list]

    total_base_damage = 0
    damage_type = None
    for d in damage_list:
        if isinstance(d, dict):
            total_base_damage += d.get("base_damage") or 0
            if d.get("damage_type"):
                damage_type = d["damage_type"]

    conditions_list = effects.get("conditions", [])
    if isinstance(conditions_list, dict):
        conditions_list = [conditions_list]
    condition_names = [
        c.get("name", "") for c in conditions_list
        if isinstance(c, dict) and c.get("name")
    ]

    return {
        "original_base_damage": total_base_damage,
        "original_damage_type": damage_type,
        "original_conditions": condition_names,
    }


def _extract_character_name(user_prompt: str) -> Optional[str]:
    """Extract character name from DM user prompt's structured 'Character:' line.

    The DM prompt always includes ``Character: {name} ({faction})`` as a
    structured section header.  This is a template field, not freeform text.
    """
    match = re.search(r'^Character:\s+(.+?)\s*\(', user_prompt, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def _find_player_intent(
    round_events: List[dict],
    character_name: Optional[str] = None,
    player_action_text: Optional[str] = None,
) -> Optional[str]:
    """
    Find player intent from action_declaration events in the same round.

    Primary: join by ``character_name`` (deterministic, from DM prompt's
    structured ``Character:`` line → ``action_declaration.character_name``).

    Fallback 1: text-match ``player_action_text`` against
    ``action_declaration.action.description``.

    Fallback 2: first declaration in round (single-PC rounds).

    Fallback 3 (legacy): parse player ``llm_call`` responses for intent.
    """
    # Build {character_name: intent} and [(description, intent)] from declarations
    name_to_intent: Dict[str, str] = {}
    declarations: List[Tuple[Optional[str], str]] = []
    for event in round_events:
        if event.get("event_type") != "action_declaration":
            continue
        action = event.get("action")
        if not isinstance(action, dict):
            continue
        intent = action.get("intent")
        if not intent:
            continue
        char = event.get("character_name")
        if char:
            name_to_intent[char] = intent
        desc = action.get("description")
        declarations.append((desc, intent))

    # Primary: deterministic join by character name
    if character_name and character_name in name_to_intent:
        return name_to_intent[character_name]

    # Fallback 1: text-match action description
    if declarations and player_action_text:
        action_lower = player_action_text.lower()[:120]
        for desc, intent in declarations:
            if not desc:
                continue
            desc_lower = desc.lower()
            if action_lower in desc_lower or desc_lower[:120] in action_lower:
                return intent

    # Fallback 2: single declaration in round
    if declarations:
        return declarations[0][1]

    # Legacy fallback: player llm_call responses (older sessions without action_declaration)
    for event in round_events:
        if event.get("event_type") != "llm_call":
            continue
        if event.get("agent_type") != "player":
            continue
        response_text = event.get("response", "")
        if not response_text:
            continue
        try:
            response_data = json.loads(response_text)
            intent = response_data.get("intent")
            if intent:
                return intent
        except (json.JSONDecodeError, TypeError):
            continue

    return None


# ---------------------------------------------------------------------------
# Extract + Classify helper
# ---------------------------------------------------------------------------

def _extract_and_classify(
    session_extractor,
    eval_subset: Dict[str, Any],
    module_swapper,
    classifier_config: Optional[Dict[str, Any]] = None,
    parent_classifier_config: Optional[Dict[str, Any]] = None,
    proxy_url: Optional[str] = None,
    proxy_strategy: Optional[str] = None,
    _preloaded_cache: Optional[Dict[str, Any]] = None,
) -> Tuple[List, Dict[str, str]]:
    """
    Extract eval cases and optionally classify + filter by intent label.

    When a classifier config is present (classifier_config or parent_classifier_config):
    - Extracts broadly (action_type + weapon_damage_type only, no keywords, no max_cases)
    - Classifies all extracted cases via IntentClassifier
    - Filters by keep/drop labels
    - Applies max_cases AFTER filtering

    When no classifier config is present (backward compat):
    - Extracts with all eval_subset filters including keywords and max_cases

    Args:
        session_extractor: SessionExtractor instance
        eval_subset: eval_subset dict from goal file or regression config
        module_swapper: ModuleSwapper instance
        classifier_config: Classifier config (may be partial — regression overrides)
        parent_classifier_config: Parent classifier config (model/prompt/cache inherited)
        proxy_url: Optional proxy URL for classifier LLM calls
        proxy_strategy: Optional proxy strategy
        _preloaded_cache: Optional pre-populated cache dict (for shared cache across calls)

    Returns:
        (filtered_cases, all_intent_labels) — labels dict maps event_id → label
    """
    has_classifier = classifier_config is not None or parent_classifier_config is not None

    if has_classifier:
        # Merge configs: regression overrides parent's keep/drop; inherits model/prompt/cache
        effective_config = {}
        if parent_classifier_config:
            effective_config.update(parent_classifier_config)
        if classifier_config:
            effective_config.update(classifier_config)

        # Extract broadly — no keywords, no max_cases
        cases = session_extractor.extract_cases(
            action_type_filter=eval_subset.get("action_type"),
            weapon_damage_type=eval_subset.get("weapon_damage_type"),
            module_swapper=module_swapper,
            # Deliberately omit: intent_keywords, exclude_keywords, max_cases
        )

        if not cases:
            return [], {}

        # Classify all cases
        classifier = IntentClassifier(
            config=effective_config,
            proxy_url=proxy_url,
            proxy_strategy=proxy_strategy,
        )

        # Inject preloaded cache if provided (shared cache optimization)
        if _preloaded_cache is not None:
            classifier._cache.update(_preloaded_cache)

        labels = classifier.classify(cases)

        # Filter by keep/drop labels
        kept, review = classifier.filter_cases(cases, labels)

        if not kept and review:
            # All cases ended up as unclear/review — likely all LLM calls failed
            from collections import Counter
            label_counts = Counter(labels.values())
            unclear_count = label_counts.get("unclear", 0)
            if unclear_count == len(labels):
                print(
                    f"\n  All {len(labels)} classifications returned 'unclear' — "
                    f"likely all LLM calls failed. Check proxy/API.",
                    file=sys.stderr,
                )

        # Apply max_cases AFTER filtering
        max_cases = eval_subset.get("max_cases")
        if max_cases and len(kept) > max_cases:
            kept = kept[:max_cases]

        return kept, labels
    else:
        # Backward compat: use all eval_subset filters including keywords and max_cases
        cases = session_extractor.extract_cases(
            action_type_filter=eval_subset.get("action_type"),
            intent_keywords=eval_subset.get("intent_keywords"),
            exclude_keywords=eval_subset.get("exclude_keywords"),
            weapon_damage_type=eval_subset.get("weapon_damage_type"),
            max_cases=eval_subset.get("max_cases"),
            module_swapper=module_swapper,
        )
        return cases, {}


# ---------------------------------------------------------------------------
# SessionExtractor
# ---------------------------------------------------------------------------

class SessionExtractor:
    """Extracts DM resolution LLM calls from JSONL session files."""

    def __init__(self, session_dirs: Optional[List[Path]] = None):
        self.session_dirs = session_dirs or DEFAULT_SESSION_DIRS

    def find_session_files(self) -> List[Path]:
        """Find all JSONL session files in configured directories."""
        files = []
        for d in self.session_dirs:
            if not d.exists():
                logger.warning(f"Session directory not found: {d}")
                continue
            # Look for JSONL files recursively
            for jsonl_path in sorted(d.rglob("*.jsonl")):
                files.append(jsonl_path)
        logger.info(f"Found {len(files)} session files across {len(self.session_dirs)} directories")
        return files

    def infer_condition(self, path: Path) -> str:
        """Infer experiment condition from file path."""
        path_str = str(path)
        if "control" in path_str:
            return "control"
        elif "treatment_v1" in path_str:
            return "treatment_v1"
        elif "treatment_v2" in path_str:
            return "treatment_v2"
        return "unknown"

    def extract_cases(
        self,
        files: Optional[List[Path]] = None,
        action_type_filter: Optional[str] = None,
        intent_filter: Optional[str] = None,
        intent_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        weapon_damage_type: Optional[str] = None,
        original_model_filter: Optional[str] = None,
        module_filter: Optional[str] = None,
        margin_range: Optional[Tuple[int, int]] = None,
        max_cases: Optional[int] = None,
        module_swapper: Optional[ModuleSwapper] = None,
    ) -> List[EvalCase]:
        """
        Extract DM resolution cases from session files.

        Filters (all active filters are ANDed together):
            action_type_filter: Only cases where action type matches (e.g., 'combat')
            intent_filter: Single keyword match on player action text (backward compat)
            intent_keywords: OR match against player_action_text AND player_intent
            exclude_keywords: Exclude cases where any keyword matches player_action_text
                              or player_intent (case-insensitive substring). ANDed with
                              other filters.
            weapon_damage_type: Exact match on extracted weapon damage type (e.g., 'wound')
            original_model_filter: Only cases from a specific original model
            module_filter: Only cases where a specific module was detected
            margin_range: Only cases with margin in [min, max] range
            max_cases: Stop after this many cases
        """
        # Normalize intent_filter → intent_keywords for backward compat
        effective_keywords = intent_keywords
        if effective_keywords is None and intent_filter:
            effective_keywords = [intent_filter]

        if files is None:
            files = self.find_session_files()

        cases = []
        for jsonl_path in files:
            condition = self.infer_condition(jsonl_path)
            try:
                file_cases = self._extract_from_file(
                    jsonl_path, condition,
                    action_type_filter, effective_keywords, exclude_keywords,
                    weapon_damage_type,
                    original_model_filter, module_filter, margin_range, module_swapper,
                )
                cases.extend(file_cases)
            except Exception as e:
                logger.warning(f"Error extracting from {jsonl_path}: {e}")

            if max_cases and len(cases) >= max_cases:
                cases = cases[:max_cases]
                break

        logger.info(f"Extracted {len(cases)} eval cases")
        return cases

    def _extract_from_file(
        self,
        jsonl_path: Path,
        condition: str,
        action_type_filter: Optional[str],
        intent_keywords: Optional[List[str]],
        exclude_keywords: Optional[List[str]],
        weapon_damage_type: Optional[str],
        original_model_filter: Optional[str],
        module_filter: Optional[str],
        margin_range: Optional[Tuple[int, int]],
        module_swapper: Optional[ModuleSwapper],
    ) -> List[EvalCase]:
        """
        Extract eval cases from a single JSONL file using two-pass extraction.

        Pass 1: Index all events by round, collect DM llm_calls separately.
        Pass 2: For each DM llm_call, look up correlated events from the same round.
        """
        session_hash = hashlib.md5(str(jsonl_path).encode()).hexdigest()[:8]

        # --- Pass 1: Read all events, index by round ---
        events_by_round: Dict[int, List[dict]] = {}
        dm_llm_calls: List[Tuple[int, dict]] = []  # (line_num, event)

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                round_num = event.get("round")
                if round_num is not None:
                    events_by_round.setdefault(round_num, []).append(event)

                # Identify DM llm_call resolution events
                if (event.get("event_type") == "llm_call"
                        and event.get("agent_type") == "dm"):
                    response_text = event.get("response", "")
                    if '"narration"' in response_text and '"effects"' in response_text:
                        dm_llm_calls.append((line_num, event))

        # --- Pass 2: Process each DM llm_call with correlated events ---
        cases = []

        for line_num, event in dm_llm_calls:
            response_text = event.get("response", "")

            # Extract system and user prompts
            prompt_messages = event.get("prompt", [])
            system_prompt = ""
            user_prompt = ""
            for msg in prompt_messages:
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                elif msg.get("role") == "user":
                    user_prompt = msg.get("content", "")

            if not system_prompt or not user_prompt:
                continue

            # Parse response for fields we need
            parsed_response = MechanicalExtractor.parse_response(response_text)
            margin = parsed_response.get("margin")
            action_type = self._infer_action_type(user_prompt)
            player_action_text = self._extract_player_action(user_prompt)

            # Look up correlated events from the same round
            round_num = event.get("round")
            round_events = events_by_round.get(round_num, []) if round_num is not None else []

            # Extract weapon context from structured JSONL events (PC-only)
            weapon_ctx = _extract_weapon_context(round_events)

            # Extract original outcome from DM response
            outcome = _extract_original_outcome(response_text)

            # Correlate with player intent via character name join
            character_name = _extract_character_name(user_prompt)
            player_intent = _find_player_intent(
                round_events,
                character_name=character_name,
                player_action_text=player_action_text,
            )

            # --- Apply filters ---
            if action_type_filter and action_type != action_type_filter:
                continue

            # Intent keywords: OR match against player_action_text AND player_intent
            if intent_keywords:
                matched = False
                search_texts = []
                if player_action_text:
                    search_texts.append(player_action_text.lower())
                if player_intent:
                    search_texts.append(player_intent.lower())
                if not search_texts:
                    continue  # No text to match against
                for kw in intent_keywords:
                    kw_lower = kw.lower()
                    if any(kw_lower in text for text in search_texts):
                        matched = True
                        break
                if not matched:
                    continue

            # Exclude keywords: if ANY exclude keyword matches, skip this case
            if exclude_keywords:
                search_texts = []
                if player_action_text:
                    search_texts.append(player_action_text.lower())
                if player_intent:
                    search_texts.append(player_intent.lower())
                excluded = False
                for kw in exclude_keywords:
                    kw_lower = kw.lower()
                    if any(kw_lower in text for text in search_texts):
                        excluded = True
                        break
                if excluded:
                    continue

            # Weapon damage type filter
            if weapon_damage_type:
                if weapon_ctx["weapon_damage_type"] != weapon_damage_type.lower():
                    continue

            if original_model_filter:
                model = event.get("model", "")
                if original_model_filter not in model:
                    continue
            if margin_range and margin is not None:
                if not (margin_range[0] <= margin <= margin_range[1]):
                    continue

            # Detect modules
            detected_modules = []
            if module_swapper:
                detected_modules = module_swapper.detect_modules(system_prompt)
            if module_filter and module_filter not in detected_modules:
                continue

            case_id = f"session_{session_hash}_{line_num}"
            case = EvalCase(
                case_id=case_id,
                session_file=str(jsonl_path),
                condition=condition,
                round_num=round_num,
                original_model=event.get("model", "unknown"),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_text=response_text,
                action_type=action_type,
                player_action_text=player_action_text,
                margin=margin,
                detected_modules=detected_modules,
                line_number=line_num,
                event_id=event.get("event_id"),
                weapon_name=weapon_ctx["weapon_name"],
                weapon_damage_type=weapon_ctx["weapon_damage_type"],
                declared_target=weapon_ctx["declared_target"],
                player_intent=player_intent,
                original_base_damage=outcome["original_base_damage"],
                original_damage_type=outcome["original_damage_type"],
                original_conditions=outcome["original_conditions"],
            )
            cases.append(case)

        return cases

    def _infer_action_type(self, user_prompt: str) -> Optional[str]:
        """Infer action type from user prompt content."""
        lower = user_prompt.lower()
        # Look for action_type markers in the user prompt
        action_type_match = re.search(r'action[_\s]?type["\s:]*["\']?(\w+)', lower)
        if action_type_match:
            return action_type_match.group(1)
        # Heuristic fallback
        if any(kw in lower for kw in ["combat", "attack", "fire", "shoot", "strike", "suppressive"]):
            return "combat"
        if any(kw in lower for kw in ["investigate", "search", "examine", "scan"]):
            return "investigate"
        if any(kw in lower for kw in ["social", "persuade", "negotiate", "charm"]):
            return "social"
        if any(kw in lower for kw in ["ritual", "attune", "purif"]):
            return "ritual"
        return None

    def _extract_player_action(self, user_prompt: str) -> Optional[str]:
        """Extract the player's action description from user prompt."""
        # Look for action description patterns (most specific first)
        patterns = [
            r'action_description["\s:]+["\'](.+?)["\']',
            r'player\s+action[:\s]+(.+?)(?:\n|$)',
            r'declared\s+action[:\s]+["\']?(.+?)(?:["\']?\s*$|\n)',
            r'(?:action|intent)[:\s]+(.+?)(?:\n|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, user_prompt, re.IGNORECASE | re.MULTILINE)
            if match:
                text = match.group(1).strip()
                # Skip matches that are clearly action_type not action description
                if text.lower() in ("combat", "investigate", "social", "ritual", "support", "movement", "perception"):
                    continue
                return text[:500]
        return None


# ---------------------------------------------------------------------------
# MechanicalExtractor
# ---------------------------------------------------------------------------

class MechanicalExtractor:
    """Parses ActionResolution JSON from raw LLM response strings."""

    @staticmethod
    def parse_response(response_text: str) -> Dict[str, Any]:
        """
        Parse an ActionResolution JSON from raw response text.

        Handles:
        - Raw JSON
        - Markdown-fenced JSON (```json...```)
        - Partial/malformed JSON (best effort)
        """
        text = response_text.strip()

        # Strip markdown code fences
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # Try to find JSON object
        # Sometimes there's text before/after the JSON
        brace_start = text.find('{')
        if brace_start == -1:
            return {}

        # Find matching closing brace
        depth = 0
        brace_end = -1
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break

        if brace_end == -1:
            # Try parsing from first brace to end
            json_str = text[brace_start:]
        else:
            json_str = text[brace_start:brace_end + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Try fixing common JSON issues
            try:
                # Remove trailing commas
                fixed = re.sub(r',\s*([}\]])', r'\1', json_str)
                data = json.loads(fixed)
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse response JSON: {json_str[:200]}...")
                return {}

        return data

    @staticmethod
    def extract_mechanical_fields(parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract mechanical fields from a parsed ActionResolution.

        Returns a flat dict with key mechanical values for scoring.
        """
        result = {
            "narration_length": len(parsed.get("narration", "")),
            "success_tier": parsed.get("success_tier"),
            "margin": parsed.get("margin"),
        }

        effects = parsed.get("effects", {})

        # Damage
        damage_list = effects.get("damage", [])
        if isinstance(damage_list, dict):
            damage_list = [damage_list]
        result["damage_count"] = len(damage_list)
        result["total_base_damage"] = sum((d.get("base_damage") or 0) for d in damage_list if isinstance(d, dict))
        result["total_dealt"] = sum((d.get("dealt") or 0) for d in damage_list if isinstance(d, dict))
        result["total_soak"] = sum((d.get("soak") or 0) for d in damage_list if isinstance(d, dict))
        result["damage_types"] = list(set((d.get("damage_type") or "unknown") for d in damage_list if isinstance(d, dict)))

        # Conditions
        conditions = effects.get("conditions", [])
        if isinstance(conditions, dict):
            conditions = [conditions]
        result["condition_count"] = len(conditions)
        result["conditions"] = [
            {"name": c.get("name", ""), "penalty": c.get("penalty", 0)}
            for c in conditions if isinstance(c, dict)
        ]

        # Void changes
        void_changes = effects.get("void_changes", [])
        if isinstance(void_changes, dict):
            void_changes = [void_changes]
        result["total_void_change"] = sum((v.get("amount") or 0) for v in void_changes if isinstance(v, dict))

        # Soulcredit changes
        sc_changes = effects.get("soulcredit_changes", [])
        if isinstance(sc_changes, dict):
            sc_changes = [sc_changes]
        result["total_soulcredit"] = sum((s.get("amount") or 0) for s in sc_changes if isinstance(s, dict))

        # Clock updates
        clock_updates = effects.get("clock_updates", [])
        if isinstance(clock_updates, dict):
            clock_updates = [clock_updates]
        result["clock_update_count"] = len(clock_updates)

        return result


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------

class BaseScorer:
    """Base class for evaluation scorers."""
    name: str = "base"

    def score(self, original: Dict[str, Any], replay: Dict[str, Any], case: EvalCase) -> Dict[str, Any]:
        raise NotImplementedError


class DamageComparisonScorer(BaseScorer):
    """Compare original vs replay base_damage."""
    name = "damage_comparison"

    def score(self, original: Dict, replay: Dict, case: EvalCase) -> Dict[str, Any]:
        orig_bd = original.get("total_base_damage", 0)
        replay_bd = replay.get("total_base_damage", 0)
        return {
            "original_base_damage": orig_bd,
            "replay_base_damage": replay_bd,
            "delta": replay_bd - orig_bd,
            "zero_damage": replay_bd == 0,
        }


class DamageRangeScorer(BaseScorer):
    """
    Check base_damage against margin-based expected ranges.

    Configurable: pass custom ranges via __init__(ranges=...) for lethal/stun
    regression checks. Without custom ranges, uses suppression defaults.

    Range format (from goal file YAML):
        ranges:
          - margin: [0, 5]
            expected: [0, 6]
          - margin: [6, 10]
            expected: [2, 12]
    """
    name = "suppression_table"

    # Default: expected suppress damage by margin range
    SUPPRESS_RANGES = {
        # (min_margin, max_margin): (min_bd, max_bd)
        (0, 5): (0, 0),
        (6, 10): (0, 2),
        (11, 15): (0, 3),
        (16, 20): (0, 5),
        (21, 99): (0, 5),
    }

    def __init__(self, ranges: Optional[List[Dict]] = None, name: Optional[str] = None):
        """
        Args:
            ranges: Optional list of dicts with 'margin' and 'expected' keys.
                    Each: {"margin": [min, max], "expected": [min_bd, max_bd]}
                    If None, uses hardcoded SUPPRESS_RANGES.
            name: Override the scorer name (used for score dict keys).
        """
        if name:
            self.name = name
        if ranges:
            self._ranges = {}
            for r in ranges:
                m = r["margin"]
                e = r["expected"]
                self._ranges[(m[0], m[1])] = (e[0], e[1])
        else:
            self._ranges = self.SUPPRESS_RANGES

    def score(self, original: Dict, replay: Dict, case: EvalCase) -> Dict[str, Any]:
        replay_bd = replay.get("total_base_damage", 0)
        margin = replay.get("margin") or case.margin or 0

        # Determine expected range
        expected_min, expected_max = 0, 99
        for (m_min, m_max), (bd_min, bd_max) in self._ranges.items():
            if m_min <= abs(margin) <= m_max:
                expected_min, expected_max = bd_min, bd_max
                break

        in_range = expected_min <= replay_bd <= expected_max

        # Check conditions
        has_condition = replay.get("condition_count", 0) > 0
        condition_names = [c.get("name", "") for c in replay.get("conditions", [])]

        return {
            "base_damage": replay_bd,
            "margin": margin,
            "expected_range": [expected_min, expected_max],
            "in_range": in_range,
            "has_condition": has_condition,
            "condition_names": condition_names,
        }


# Backward compatibility alias
SuppressionTableScorer = DamageRangeScorer


class SoulcreditScorer(BaseScorer):
    """Compare original vs replay soulcredit totals."""
    name = "soulcredit"

    def score(self, original: Dict, replay: Dict, case: EvalCase) -> Dict[str, Any]:
        orig_sc = original.get("total_soulcredit", 0)
        replay_sc = replay.get("total_soulcredit", 0)
        return {
            "original_soulcredit": orig_sc,
            "replay_soulcredit": replay_sc,
            "delta": replay_sc - orig_sc,
        }


SCORER_REGISTRY = {
    "damage_comparison": DamageComparisonScorer,
    "damage_range": DamageRangeScorer,
    "suppression_table": DamageRangeScorer,  # backward compat alias
    "soulcredit": SoulcreditScorer,
}


# ---------------------------------------------------------------------------
# ReplayEngine
# ---------------------------------------------------------------------------

class ReplayEngine:
    """Replays eval cases against LLMs with concurrent execution."""

    def __init__(
        self,
        workers: int = 4,
        request_delay: float = 0.5,
        proxy_url: Optional[str] = None,
        proxy_strategy: Optional[str] = None,
        verbose: bool = False,
    ):
        self.workers = workers
        self.request_delay = request_delay
        self.proxy_url = proxy_url
        self.proxy_strategy = proxy_strategy
        self.verbose = verbose
        self._clients: Dict[str, Any] = {}  # provider → UnifiedAIClient
        # Shared semaphore gates total concurrent API requests across all
        # replay_batch calls, preventing socket exhaustion when multiple
        # batches (main + regressions) run in parallel.
        self._semaphore = threading.Semaphore(workers)

    def _get_client(self, provider: str):
        """Get or create a UnifiedAIClient for the given provider."""
        if provider not in self._clients:
            from aeonisk.multiagent.unified_llm_client import UnifiedAIClient
            kwargs = {"provider": provider}
            if self.proxy_url:
                kwargs["use_proxy"] = True
                kwargs["proxy_url"] = self.proxy_url
                kwargs["no_fallback"] = True  # Never fall back to direct API keys
                if self.proxy_strategy:
                    kwargs["proxy_strategy"] = self.proxy_strategy
            self._clients[provider] = UnifiedAIClient(**kwargs)
        return self._clients[provider]

    # Errors that indicate an empty/whitespace response worth retrying
    _EMPTY_RESPONSE_PATTERNS = [
        "empty/whitespace",
        "empty/whitespace-only content",
    ]

    def _is_empty_content_error(self, error: Exception) -> bool:
        """Check if an exception is an empty-content error worth retrying."""
        msg = str(error).lower()
        return any(p in msg for p in self._EMPTY_RESPONSE_PATTERNS)

    def replay_case(
        self,
        case: EvalCase,
        modified_system_prompt: str,
        provider: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        max_retries: int = 3,
    ) -> Tuple[str, float]:
        """
        Replay a single case and return (response_text, latency_ms).

        Retries up to max_retries times on empty/whitespace responses or
        proxy empty-content errors, with exponential backoff (1s, 2s, 4s).
        """
        client = self._get_client(provider)

        # Auto-fix temperature for models that only support 1.0
        if "gpt-5-mini" in model:
            temperature = 1.0

        messages = [
            {"role": "system", "content": modified_system_prompt},
            {"role": "user", "content": case.user_prompt},
        ]

        if self.verbose:
            print(f"\n--- {case.case_id} → {provider}:{model} ---", file=sys.stderr)
            print(f"  System prompt: {len(modified_system_prompt)} chars", file=sys.stderr)
            print(f"  User prompt:   {len(case.user_prompt)} chars", file=sys.stderr)
            # Show last 200 chars of user prompt (the action being resolved)
            snippet = case.user_prompt[-200:].replace("\n", " ").strip()
            print(f"  User tail:     ...{snippet}", file=sys.stderr)

        start = time.time()

        # Acquire semaphore to limit total concurrent API requests across
        # all parallel replay batches (main eval + regressions)
        with self._semaphore:
            for attempt in range(1, max_retries + 1):
                try:
                    response = client.chat_completion(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    # Check for empty/whitespace response
                    if not response or not response.strip():
                        if attempt < max_retries:
                            delay = 2 ** (attempt - 1)  # 1s, 2s, 4s
                            logger.warning(
                                f"Empty response for {case.case_id} (attempt {attempt}/{max_retries}), "
                                f"retrying in {delay}s..."
                            )
                            time.sleep(delay)
                            continue
                        raise ValueError(
                            f"LLM returned empty/whitespace response after {max_retries} retries"
                        )

                    # Valid response
                    break

                except Exception as e:
                    if self._is_empty_content_error(e) and attempt < max_retries:
                        delay = 2 ** (attempt - 1)
                        logger.warning(
                            f"Empty content error for {case.case_id} (attempt {attempt}/{max_retries}): "
                            f"{e}, retrying in {delay}s..."
                        )
                        time.sleep(delay)
                        continue
                    raise

        latency_ms = (time.time() - start) * 1000

        if self.verbose:
            # Show response snippet
            resp_snippet = response[:300].replace("\n", " ").strip()
            print(f"  Response:      {len(response)} chars, {latency_ms:.0f}ms", file=sys.stderr)
            print(f"  Response head: {resp_snippet}...", file=sys.stderr)

        if self.request_delay > 0:
            time.sleep(self.request_delay)

        return response, latency_ms

    def replay_batch(
        self,
        cases: List[EvalCase],
        modified_prompts: Dict[str, str],  # case_id → modified system prompt
        model_specs: List[Tuple[str, str]],  # [(provider, model), ...]
        scorers: List[BaseScorer],
        save_prompts: bool = False,
        completed_keys: Optional[Set[Tuple[str, str]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        on_result: Optional[Callable[[ReplayResult], None]] = None,
        label: str = "",
    ) -> List[ReplayResult]:
        """
        Replay all cases against all models with concurrent execution.

        Args:
            cases: List of eval cases
            modified_prompts: case_id → modified system prompt
            model_specs: List of (provider, model) tuples to replay against
            scorers: Scoring strategies
            save_prompts: Include full prompts in results (for fine-tuning)
            completed_keys: Set of (case_id, model_label) already done (for resume)
            temperature: LLM temperature
            max_tokens: LLM max tokens
            on_result: Optional callback invoked with each result as it completes
            label: Label prefix for progress output (e.g., "main", "reg:lethal")

        Returns:
            List of ReplayResult
        """
        if completed_keys is None:
            completed_keys = set()

        # Build work items: (case, provider, model) tuples
        work_items = []
        for case in cases:
            for provider, model in model_specs:
                model_label = f"{provider}:{model}"
                key = (case.case_id, model_label)
                if key in completed_keys:
                    continue
                work_items.append((case, provider, model))

        total = len(work_items)
        if total == 0:
            logger.info("No work items to replay (all completed or filtered)")
            return []

        logger.info(f"Replaying {total} cases ({len(cases)} cases × {len(model_specs)} models, {len(completed_keys)} already done)")

        results = []
        completed = 0

        def _replay_one(case: EvalCase, provider: str, model: str) -> ReplayResult:
            """Worker function for a single replay."""
            model_label = f"{provider}:{model}"
            modified_prompt = modified_prompts.get(case.case_id, case.system_prompt)

            # Parse original response
            orig_parsed = MechanicalExtractor.parse_response(case.response_text)
            orig_fields = MechanicalExtractor.extract_mechanical_fields(orig_parsed)

            try:
                response_text, latency_ms = self.replay_case(
                    case, modified_prompt, provider, model,
                    temperature=temperature, max_tokens=max_tokens,
                )
                replay_parsed = MechanicalExtractor.parse_response(response_text)
                replay_fields = MechanicalExtractor.extract_mechanical_fields(replay_parsed)

                # Score
                score_results = {}
                for scorer in scorers:
                    score_results[scorer.name] = scorer.score(orig_fields, replay_fields, case)

                result = ReplayResult(
                    case_id=case.case_id,
                    condition=case.condition,
                    round_num=case.round_num,
                    action_type=case.action_type,
                    original_model=case.original_model,
                    eval_model=model_label,
                    margin=case.margin,
                    original=orig_fields,
                    replay=replay_fields,
                    scores=score_results,
                    latency_ms=latency_ms,
                    player_action_text=case.player_action_text,
                )
                if save_prompts:
                    result.system_prompt = modified_prompt
                    result.user_prompt = case.user_prompt
                    result.replay_response = response_text

                return result

            except Exception as e:
                logger.error(f"Replay failed for {case.case_id} with {model_label}: {e}")
                return ReplayResult(
                    case_id=case.case_id,
                    condition=case.condition,
                    round_num=case.round_num,
                    action_type=case.action_type,
                    original_model=case.original_model,
                    eval_model=model_label,
                    margin=case.margin,
                    original=orig_fields,
                    replay={},
                    scores={},
                    error=str(e),
                    player_action_text=case.player_action_text,
                )

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_item = {
                executor.submit(_replay_one, case, provider, model): (case, provider, model)
                for case, provider, model in work_items
            }

            for future in as_completed(future_to_item):
                result = future.result()
                results.append(result)
                if on_result:
                    on_result(result)
                completed += 1

                # Progress
                status = "OK" if not result.error else f"ERR: {result.error[:60]}"
                if completed % 10 == 0 or completed == total:
                    prefix = f"{label} " if label else ""
                    print(f"  [{prefix}{completed}/{total}] {status}", file=sys.stderr)

        return results


# ---------------------------------------------------------------------------
# ResultStore
# ---------------------------------------------------------------------------

class ResultStore:
    """Stores and loads results as JSONL, streaming each result to disk."""

    def __init__(self, output_path: Optional[str] = None):
        self.output_path = output_path
        self._file = None
        self._count = 0

    def open(self, append: bool = False):
        """Create parent dirs and open output file for streaming writes."""
        if not self.output_path:
            return
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        self._file = open(self.output_path, mode)
        self._count = 0

    def close(self):
        """Flush and close the output file."""
        if self._file:
            self._file.close()
            self._file = None
            if self._count:
                logger.info(f"Saved {self._count} results to {self.output_path}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def _result_to_dict(r: ReplayResult) -> Dict[str, Any]:
        data = {
            "case_id": r.case_id,
            "condition": r.condition,
            "round": r.round_num,
            "action_type": r.action_type,
            "original_model": r.original_model,
            "eval_model": r.eval_model,
            "margin": r.margin,
            "original": r.original,
            "replay": r.replay,
            "scores": r.scores,
            "latency_ms": r.latency_ms,
        }
        if r.player_action_text is not None:
            data["player_action_text"] = r.player_action_text
        if r.error:
            data["error"] = r.error
        if r.system_prompt is not None:
            data["system_prompt"] = r.system_prompt
        if r.user_prompt is not None:
            data["user_prompt"] = r.user_prompt
        if r.replay_response is not None:
            data["replay_response"] = r.replay_response
        return data

    def append_result(self, result: ReplayResult):
        """Write a single result to the output file immediately."""
        if not self._file:
            return
        self._file.write(json.dumps(self._result_to_dict(result)) + "\n")
        self._file.flush()
        self._count += 1

    def load_completed_keys(self) -> Set[Tuple[str, str]]:
        """Load (case_id, model) pairs from existing output file."""
        keys = set()
        if not self.output_path or not Path(self.output_path).exists():
            return keys
        with open(self.output_path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    keys.add((data["case_id"], data["eval_model"]))
                except (json.JSONDecodeError, KeyError):
                    continue
        return keys

    def save_results(self, results: List[ReplayResult], append: bool = False):
        """Batch-save results to JSONL file (used by self-judge iterations)."""
        if not self.output_path:
            return
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(self.output_path, mode) as f:
            for r in results:
                f.write(json.dumps(self._result_to_dict(r)) + "\n")
        logger.info(f"Saved {len(results)} results to {self.output_path}")


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Generates human-readable summary reports from results."""

    @staticmethod
    def generate(
        results: List[ReplayResult],
        module_name: str,
        scorers: List[BaseScorer],
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate a human-readable report and structured score dict.

        Returns:
            (report_text, score_dict)
        """
        if not results:
            return "No results to report.\n", {}

        # Filter out errors
        valid = [r for r in results if not r.error]
        errors = [r for r in results if r.error]

        lines = []
        lines.append(f"Prompt Eval: {module_name}")
        lines.append(f"{len(valid)} valid results, {len(errors)} errors")
        lines.append("")

        # Group by model
        by_model: Dict[str, List[ReplayResult]] = {}
        for r in valid:
            by_model.setdefault(r.eval_model, []).append(r)

        # Overall score dict for self-judging
        score_dict: Dict[str, Any] = {}

        # Dynamic model column width (minimum 5 for "Model" header)
        mw = max((len(m) for m in by_model), default=5)
        mw = max(mw, 5)

        # Per-scorer reports
        for scorer in scorers:
            lines.append(f"--- {scorer.name} ---")

            if scorer.name == "damage_comparison":
                lines.append(f"{'Model':<{mw}} | {'Avg BD (orig→new)':<20} | {'Δ':>6} | {'Zero dmg':>8} | {'Drift':>5}")
                lines.append("-" * (mw + 54))

                for model, model_results in sorted(by_model.items()):
                    scored = [r for r in model_results if scorer.name in r.scores]
                    if not scored:
                        continue
                    orig_avg = sum(r.scores[scorer.name]["original_base_damage"] for r in scored) / len(scored)
                    new_avg = sum(r.scores[scorer.name]["replay_base_damage"] for r in scored) / len(scored)
                    delta = new_avg - orig_avg
                    zero_pct = sum(1 for r in scored if r.scores[scorer.name]["zero_damage"]) / len(scored) * 100
                    drift_pct = abs(delta) / orig_avg * 100 if orig_avg > 0 else 0
                    lines.append(f"{model:<{mw}} | {orig_avg:>6.1f} → {new_avg:<6.1f}     | {delta:>+6.1f} | {zero_pct:>6.0f}% | {drift_pct:>5.1f}%")

                    score_dict.setdefault(scorer.name, {})[model] = {
                        "avg_base_damage": new_avg,
                        "zero_damage_pct": zero_pct,
                        "delta": delta,
                        "drift_pct": drift_pct,
                    }

            elif scorer.name in ("damage_range", "suppression_table"):
                lines.append(f"{'Model':<{mw}} | {'Avg BD':>6} | {'% in range':>10} | {'% w/ cond':>10}")
                lines.append("-" * (mw + 40))

                for model, model_results in sorted(by_model.items()):
                    scored = [r for r in model_results if scorer.name in r.scores]
                    if not scored:
                        continue
                    avg_bd = sum(r.scores[scorer.name]["base_damage"] for r in scored) / len(scored)
                    in_range_pct = sum(1 for r in scored if r.scores[scorer.name]["in_range"]) / len(scored) * 100
                    has_cond_pct = sum(1 for r in scored if r.scores[scorer.name]["has_condition"]) / len(scored) * 100
                    lines.append(f"{model:<{mw}} | {avg_bd:>6.1f} | {in_range_pct:>8.0f}% | {has_cond_pct:>8.0f}%")

                    score_dict.setdefault(scorer.name, {})[model] = {
                        "avg_base_damage": avg_bd,
                        "in_range_pct": in_range_pct,
                        "has_condition_pct": has_cond_pct,
                    }

            elif scorer.name == "soulcredit":
                lines.append(f"{'Model':<{mw}} | {'Avg SC (orig→new)':<20} | {'Δ':>6}")
                lines.append("-" * (mw + 35))

                for model, model_results in sorted(by_model.items()):
                    scored = [r for r in model_results if scorer.name in r.scores]
                    if not scored:
                        continue
                    orig_avg = sum(r.scores[scorer.name]["original_soulcredit"] for r in scored) / len(scored)
                    new_avg = sum(r.scores[scorer.name]["replay_soulcredit"] for r in scored) / len(scored)
                    delta = new_avg - orig_avg
                    lines.append(f"{model:<{mw}} | {orig_avg:>6.1f} → {new_avg:<6.1f}     | {delta:>+6.1f}")

                    score_dict.setdefault(scorer.name, {})[model] = {
                        "avg_soulcredit": new_avg,
                        "delta": delta,
                    }

            lines.append("")

        if errors:
            lines.append(f"--- Errors ({len(errors)}) ---")
            for r in errors[:5]:
                lines.append(f"  {r.case_id} / {r.eval_model}: {r.error[:100]}")
            if len(errors) > 5:
                lines.append(f"  ... and {len(errors) - 5} more")
            lines.append("")

        report = "\n".join(lines)
        return report, score_dict


# ---------------------------------------------------------------------------
# IntentClassifier
# ---------------------------------------------------------------------------

class IntentClassifier:
    """
    LLM-based intent classifier for eval cases.

    Classifies each case (e.g., suppress vs lethal) using a cheap LLM,
    caches results keyed by event_id for reuse across runs.

    Configured via goal file `classifier` section:
        classifier:
          model: openai:gpt-5-mini
          keep: [suppress]
          drop: [lethal]
          cache_file: evals/labels/suppress_labels.json
          prompt: |
            Classify this player action...
            {action_text}
            {intent_text}
    """

    def __init__(
        self,
        config: Dict[str, Any],
        proxy_url: Optional[str] = None,
        proxy_strategy: Optional[str] = None,
    ):
        self.config = config
        model_spec = config.get("model", "openai:gpt-5-mini")
        self.provider, self.model = parse_model_spec(model_spec)
        self.keep_labels: Set[str] = set(config.get("keep", []))
        self.drop_labels: Set[str] = set(config.get("drop", []))
        self.cache_file = config.get("cache_file")
        self.prompt_template = config.get("prompt", self._default_prompt())
        self.proxy_url = proxy_url
        self.proxy_strategy = proxy_strategy
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    @staticmethod
    def _default_prompt() -> str:
        return (
            "Classify the TACTICAL METHOD described in the player's action.\n"
            "\n"
            "Categories:\n"
            "- suppress: Covering fire, suppressive fire, pinning fire, warning shots, "
            "firing to deny movement or force into cover. Area denial, NOT aimed at a specific target.\n"
            "- lethal: Aimed shots, firing at a target, shooting to wound/kill/neutralize/eliminate.\n"
            "- stun: Non-lethal takedown — shock baton, taser, knock out, subdue.\n"
            "- unclear: Cannot determine method from the action description.\n"
            "\n"
            "IMPORTANT: Classify based on the ACTION DESCRIPTION (what they're physically doing), "
            "not the strategic intent. Suppressive fire with goal 'neutralize threats' = suppress. "
            "Aimed shots with goal 'protect allies' = lethal.\n"
            "\n"
            "Player action: {action_text}\n"
            "Player intent (strategic goal, secondary): {intent_text}\n"
            "\n"
            "Respond with exactly one word: suppress, lethal, stun, or unclear"
        )

    def _load_cache(self):
        """Load cached labels from disk."""
        if not self.cache_file or not Path(self.cache_file).exists():
            return
        try:
            with open(self.cache_file, "r") as f:
                self._cache = json.load(f)
            logger.info(f"Loaded {len(self._cache)} cached labels from {self.cache_file}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load label cache {self.cache_file}: {e}")

    def _save_cache(self):
        """Save cached labels to disk."""
        if not self.cache_file:
            return
        Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self._cache, f, indent=2)
        logger.info(f"Saved {len(self._cache)} labels to {self.cache_file}")

    def _get_client(self):
        from aeonisk.multiagent.unified_llm_client import UnifiedAIClient
        kwargs = {"provider": self.provider}
        if self.proxy_url:
            kwargs["use_proxy"] = True
            kwargs["proxy_url"] = self.proxy_url
            kwargs["no_fallback"] = True
            if self.proxy_strategy:
                kwargs["proxy_strategy"] = self.proxy_strategy
        return UnifiedAIClient(**kwargs)

    # Sentinel for "LLM call failed" vs "LLM returned unclear"
    _ERROR_LABEL = "__error__"

    def _classify_one(self, case: EvalCase, client) -> Tuple[str, Optional[str]]:
        """
        Classify a single case via LLM.

        Returns:
            (label, error_msg) — error_msg is None on success, str on failure.
            On failure, label is _ERROR_LABEL (distinct from "unclear" which is a valid LLM response).
        """
        prompt = self.prompt_template.format(
            action_text=case.player_action_text or "(no action text)",
            intent_text=case.player_intent or "(no intent)",
        )
        try:
            response = client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=1.0,  # GPT-5 models only accept 1.0
                max_tokens=1000,  # GPT-5 uses reasoning tokens from this budget
            )
            label = response.strip().lower().rstrip(".")
            # Normalize: take just the first word
            label = label.split()[0] if label.split() else "unclear"
            return label, None
        except Exception as e:
            return self._ERROR_LABEL, str(e)

    def classify(
        self,
        cases: List[EvalCase],
        workers: int = 10,
    ) -> Dict[str, str]:
        """
        Classify cases, using cache where available.

        Returns:
            Dict mapping event_id → label
        """
        results: Dict[str, str] = {}
        to_classify: List[EvalCase] = []

        for case in cases:
            eid = case.event_id
            if not eid:
                # Fallback to case_id if event_id missing
                eid = case.case_id
            if eid in self._cache:
                results[eid] = self._cache[eid]["label"]
            else:
                to_classify.append(case)

        if not to_classify:
            logger.info(f"All {len(cases)} cases found in cache")
            return results

        cache_hits = len(results)
        total = len(to_classify)
        logger.info(
            f"Classifying {total} cases "
            f"({cache_hits} cache hits, model={self.provider}:{self.model})"
        )
        print(
            f"  Classifying {total} cases "
            f"({cache_hits} cached) with {self.provider}:{self.model}...",
            file=sys.stderr,
        )

        client = self._get_client()

        error_count = 0
        error_reasons: Dict[str, int] = {}  # error message → count
        completed = 0
        lock = threading.Lock()

        def _do_one(case: EvalCase) -> Tuple[str, str, EvalCase, Optional[str]]:
            label, error = self._classify_one(case, client)
            eid = case.event_id or case.case_id
            return eid, label, case, error

        with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_do_one, c) for c in to_classify]
                for future in as_completed(futures):
                    eid, label, case, error = future.result()

                    if error:
                        with lock:
                            error_count += 1
                            # Bucket errors by first 80 chars (deduplicate similar messages)
                            short_err = error[:80]
                            error_reasons[short_err] = error_reasons.get(short_err, 0) + 1

                        # On error, store "unclear" as the label (not __error__)
                        label = "unclear"

                    results[eid] = label
                    self._cache[eid] = {
                        "label": label,
                        "action_text": (case.player_action_text or "")[:200],
                        "intent": (case.player_intent or "")[:200],
                        "case_id": case.case_id,
                        "margin": case.margin,
                        "classified_by": f"{self.provider}:{self.model}" if not error else "error",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    # Progress indicator
                    with lock:
                        completed += 1
                        if completed % 50 == 0 or completed == total:
                            print(
                                f"  ... {completed}/{total} classified"
                                f" ({error_count} errors)",
                                file=sys.stderr,
                            )
        # --- Classification summary ---
        from collections import Counter
        label_counts = Counter(
            results[case.event_id or case.case_id]
            for case in to_classify
        )

        print(f"\n  Classification complete: {total} cases", file=sys.stderr)
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            action = ""
            if label in self.keep_labels:
                action = " (KEEP)"
            elif label in self.drop_labels:
                action = " (DROP)"
            print(f"    {label}: {count} ({pct:.0f}%){action}", file=sys.stderr)

        if error_count > 0:
            error_pct = error_count / total * 100
            print(
                f"\n  ERRORS: {error_count}/{total} ({error_pct:.0f}%) classifications failed",
                file=sys.stderr,
            )
            for reason, count in sorted(error_reasons.items(), key=lambda x: -x[1]):
                print(f"    [{count}x] {reason}", file=sys.stderr)

            if error_pct > 80:
                print(
                    f"\n  WARNING: >80% failure rate — check proxy health "
                    f"(curl {self.proxy_url}/health) and API key",
                    file=sys.stderr,
                )

        # Only save to cache if there were some successes
        if error_count < total:
            self._save_cache()

        return results

    def filter_cases(
        self,
        cases: List[EvalCase],
        labels: Dict[str, str],
    ) -> Tuple[List[EvalCase], List[EvalCase]]:
        """
        Filter cases by classification label.

        Returns:
            (kept_cases, review_cases) — kept are auto-included,
            review are unclear/unrecognized labels needing human review.
        """
        kept = []
        review = []
        dropped = 0

        for case in cases:
            eid = case.event_id or case.case_id
            label = labels.get(eid, "unclear")
            if label in self.keep_labels:
                kept.append(case)
            elif label in self.drop_labels:
                dropped += 1
            else:
                review.append(case)

        print(
            f"  Classifier: {len(kept)} kept, {dropped} dropped, "
            f"{len(review)} need review",
            file=sys.stderr,
        )
        return kept, review


# ---------------------------------------------------------------------------
# SelfJudge
# ---------------------------------------------------------------------------

class SelfJudge:
    """Automatic prompt iteration loop using an LLM judge to rewrite modules."""

    def __init__(
        self,
        goal_file: str,
        judge_model: str = "anthropic:claude-sonnet-4-5",
        max_iterations: int = 5,
        confirm_each: bool = False,
        proxy_url: Optional[str] = None,
        proxy_strategy: Optional[str] = None,
    ):
        self.goal = self._load_goal(goal_file)
        self.judge_provider, self.judge_model = parse_model_spec(judge_model)
        self.max_iterations = self.goal.get("max_iterations", max_iterations)
        self.confirm_each = confirm_each
        self.proxy_url = proxy_url
        self.proxy_strategy = proxy_strategy

    def _load_goal(self, goal_file: str) -> Dict[str, Any]:
        with open(goal_file, "r") as f:
            return yaml.safe_load(f)

    def check_targets(self, score_dict: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if all target metrics are met.

        Returns:
            (all_met, details) where details maps target_name → {target, actual, met}
        """
        targets = self.goal.get("targets", {})
        details = {}
        all_met = True

        for scorer_name, scorer_targets in targets.items():
            for metric_name, target_value in scorer_targets.items():
                # The max_ prefix is a comparison directive, not part of the
                # score key. Strip it to find the actual scorer metric key.
                score_key = metric_name
                if metric_name.startswith("max_"):
                    score_key = metric_name[4:]  # strip "max_"

                # Find actual value across all models (use worst-case / average)
                actual_values = []
                if scorer_name in score_dict:
                    for model_scores in score_dict[scorer_name].values():
                        if score_key in model_scores:
                            actual_values.append(model_scores[score_key])

                if not actual_values:
                    details[f"{scorer_name}.{metric_name}"] = {
                        "target": target_value,
                        "actual": None,
                        "met": False,
                    }
                    all_met = False
                    continue

                # For "max_*" targets, check all values are below
                # For "min_*" or "*_pct" targets, check average meets threshold
                if metric_name.startswith("max_"):
                    actual = max(actual_values)
                    met = actual <= target_value
                else:
                    actual = sum(actual_values) / len(actual_values)
                    met = actual >= target_value

                details[f"{scorer_name}.{metric_name}"] = {
                    "target": target_value,
                    "actual": round(actual, 1),
                    "met": met,
                }
                if not met:
                    all_met = False

        return all_met, details

    def _prepare_regression(
        self,
        reg_name: str,
        reg_config: Dict,
        module_name: str,
        current_content: str,
        module_swapper: ModuleSwapper,
        session_extractor: SessionExtractor,
    ) -> Optional[Dict[str, Any]]:
        """
        Prepare a single regression for replay: extract cases, build scorers, swap prompts.

        Returns:
            Prepared regression dict with cases/scorers/prompts, or None if no cases.
        """
        reg_subset = reg_config.get("eval_subset", {})
        reg_targets = reg_config.get("targets", {})
        reg_scorers_config = reg_config.get("scorers", {})
        description = reg_config.get("description", "")

        reg_cases, _ = _extract_and_classify(
            session_extractor, reg_subset, module_swapper,
            classifier_config=reg_config.get("classifier"),
            parent_classifier_config=self.goal.get("classifier"),
            proxy_url=self.proxy_url,
            proxy_strategy=self.proxy_strategy,
        )

        if not reg_cases:
            logger.warning(f"Regression '{reg_name}': no cases found, skipping")
            return None

        reg_scorers = []
        for scorer_name in list(reg_targets.keys()):
            if scorer_name in reg_scorers_config:
                cfg = reg_scorers_config[scorer_name]
                if scorer_name in ("damage_range", "suppression_table"):
                    scorer = DamageRangeScorer(
                        ranges=cfg.get("ranges"), name=scorer_name
                    )
                else:
                    scorer_cls = SCORER_REGISTRY.get(scorer_name)
                    if scorer_cls:
                        scorer = scorer_cls()
                    else:
                        continue
            else:
                scorer_cls = SCORER_REGISTRY.get(scorer_name)
                if scorer_cls:
                    scorer = scorer_cls()
                else:
                    continue
            reg_scorers.append(scorer)

        if not reg_scorers:
            return None

        reg_prompts = {}
        for case in reg_cases:
            try:
                reg_prompts[case.case_id] = module_swapper.swap_module(
                    case.system_prompt, module_name, current_content
                )
            except ValueError:
                reg_prompts[case.case_id] = case.system_prompt

        return {
            "name": reg_name,
            "description": description,
            "cases": reg_cases,
            "scorers": reg_scorers,
            "prompts": reg_prompts,
            "targets": reg_targets,
        }

    @staticmethod
    def _score_regression(
        reg: Dict[str, Any],
        replay_results: List[ReplayResult],
        module_name: str,
    ) -> Dict[str, Any]:
        """Score a single regression's replay results against its targets."""
        _, reg_score_dict = ReportGenerator.generate(
            replay_results, module_name, reg["scorers"]
        )

        reg_details = {}
        all_met = True
        for scorer_name, scorer_targets in reg["targets"].items():
            for metric_name, target_value in scorer_targets.items():
                score_key = metric_name
                if metric_name.startswith("max_"):
                    score_key = metric_name[4:]

                actual_values = []
                if scorer_name in reg_score_dict:
                    for model_scores in reg_score_dict[scorer_name].values():
                        if score_key in model_scores:
                            actual_values.append(model_scores[score_key])

                if not actual_values:
                    reg_details[f"{scorer_name}.{metric_name}"] = {
                        "target": target_value,
                        "actual": None,
                        "met": False,
                    }
                    all_met = False
                    continue

                if metric_name.startswith("max_"):
                    actual = max(actual_values)
                    met = actual <= target_value
                else:
                    actual = sum(actual_values) / len(actual_values)
                    met = actual >= target_value

                reg_details[f"{scorer_name}.{metric_name}"] = {
                    "target": target_value,
                    "actual": round(actual, 1),
                    "met": met,
                }
                if not met:
                    all_met = False

        status = "PASS" if all_met else "FAIL"
        print(f"  Regression '{reg['name']}': {status} ({len(reg['cases'])} cases)", file=sys.stderr)
        for metric, info in reg_details.items():
            met_str = "PASS" if info["met"] else "FAIL"
            print(f"    {metric}: {info['actual']} (target {info['target']}) → {met_str}", file=sys.stderr)

        return {
            "description": reg["description"],
            "all_met": all_met,
            "details": reg_details,
        }

    def _run_regressions(
        self,
        module_name: str,
        current_content: str,
        module_swapper: ModuleSwapper,
        session_extractor: SessionExtractor,
        replay_engine: ReplayEngine,
        model_specs: List[Tuple[str, str]],
        output_dir: Optional[str] = None,
        iteration: Optional[int] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        Run regression checks defined in the goal file's `regressions` section.
        All regression replays run concurrently.

        Returns:
            Dict mapping regression name → {description, all_met, details}
        """
        regressions = self.goal.get("regressions", {})
        if not regressions:
            return {}

        # Phase 1: Prepare all regressions (extract cases, build prompts — fast)
        prepared = {}
        for reg_name, reg_config in regressions.items():
            reg = self._prepare_regression(
                reg_name, reg_config, module_name, current_content,
                module_swapper, session_extractor,
            )
            if reg:
                prepared[reg_name] = reg

        if not prepared:
            return {
                name: {"description": cfg.get("description", ""), "all_met": True, "details": {}}
                for name, cfg in regressions.items()
            }

        # Phase 2: Replay all regressions concurrently
        futures = {}
        with ThreadPoolExecutor(max_workers=len(prepared)) as pool:
            for reg_name, reg in prepared.items():
                futures[reg_name] = pool.submit(
                    replay_engine.replay_batch,
                    reg["cases"], reg["prompts"], model_specs, reg["scorers"],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    label=f"reg:{reg_name}",
                )
            replay_results = {name: f.result() for name, f in futures.items()}

        # Phase 2.5: Save regression replay data to disk
        if output_dir and iteration is not None:
            for reg_name, reg_results in replay_results.items():
                if reg_results:
                    reg_path = Path(output_dir) / f"iteration_{iteration}_regression_{reg_name}_results.jsonl"
                    ResultStore(str(reg_path)).save_results(reg_results)

        # Phase 3: Score all regressions
        results = {}
        for reg_name in regressions:
            if reg_name in prepared:
                results[reg_name] = self._score_regression(
                    prepared[reg_name], replay_results[reg_name], module_name,
                )
            else:
                results[reg_name] = {
                    "description": regressions[reg_name].get("description", ""),
                    "all_met": True,
                    "details": {},
                }

        return results

    def build_judge_prompt(
        self,
        current_module_content: str,
        score_dict: Dict[str, Any],
        target_details: Dict[str, Any],
        failed_examples: List[ReplayResult],
        retry_context: Optional[str] = None,
        iteration_history: Optional[List[Dict[str, Any]]] = None,
        success_examples: Optional[List[ReplayResult]] = None,
        regression_results: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the prompt for the judge LLM to rewrite the module."""
        lines = [
            "You are a prompt engineer optimizing a DM resolution prompt module for a tabletop RPG system.",
            "",
            "## Current Prompt Module",
            "```yaml",
            f"content: |-",
        ]
        for line in current_module_content.split("\n"):
            lines.append(f"  {line}")
        lines.append("```")
        lines.append("")

        # Iteration history table (between module and scoring results)
        if iteration_history:
            lines.append(f"## Iteration History ({len(iteration_history)} previous iterations)")
            lines.append("")

            # Build column names from target metric details
            metric_names = []
            if iteration_history:
                first_details = iteration_history[0].get("details", {})
                metric_names = list(first_details.keys())

            # Table header
            header = "| Iter | Score% | Met |"
            separator = "|------|--------|-----|"
            for name in metric_names:
                short = name.split(".")[-1]
                header += f" {short} |"
                separator += "-" * (len(short) + 2) + "|"
            lines.append(header)
            lines.append(separator)

            # Table rows
            for entry in iteration_history:
                row = f"| {entry['iteration']} | {entry['score_pct']:.0f}% | {entry['targets_met']}/{entry['targets_total']} |"
                details = entry.get("details", {})
                for name in metric_names:
                    d = details.get(name, {})
                    actual = d.get("actual", "?")
                    status = "PASS" if d.get("met") else "FAIL"
                    row += f" {actual} {status} |"
                lines.append(row)

            lines.append("")

            # Last transition summary
            if len(iteration_history) >= 2:
                prev = iteration_history[-2]
                curr = iteration_history[-1]
                transitions = []
                for name in metric_names:
                    prev_actual = prev.get("details", {}).get(name, {}).get("actual")
                    curr_actual = curr.get("details", {}).get(name, {}).get("actual")
                    if prev_actual is not None and curr_actual is not None:
                        short = name.split(".")[-1]
                        if isinstance(prev_actual, (int, float)) and isinstance(curr_actual, (int, float)):
                            # max_* metrics: lower is better; others: higher is better
                            if short.startswith("max_"):
                                direction = "improved" if curr_actual <= prev_actual else "regressed"
                            else:
                                direction = "improved" if curr_actual >= prev_actual else "regressed"
                            transitions.append(f"{short}: {prev_actual}\u2192{curr_actual} ({direction})")
                if transitions:
                    lines.append(f"Last transition: {'; '.join(transitions)}")
                    lines.append("")

        # Scoring results
        lines.append("## Scoring Results vs Targets")
        lines.append("")
        for metric, info in target_details.items():
            status = "PASS" if info["met"] else "FAIL"
            lines.append(f"- **{metric}**: actual={info['actual']}, target={info['target']} \u2192 {status}")
        lines.append("")

        # Score breakdown
        lines.append("## Detailed Scores by Model")
        lines.append(f"```json\n{json.dumps(score_dict, indent=2)}\n```")
        lines.append("")

        # Success examples (anchor for what "good" looks like)
        if success_examples:
            show = success_examples[:3]
            lines.append(f"## Successful Examples ({len(show)} shown)")
            for i, r in enumerate(show):
                lines.append(f"\n### Success {i+1} ({r.case_id})")
                if r.player_action_text:
                    lines.append(f"- **Player action:** \"{r.player_action_text}\"")
                lines.append(f"- **Action type:** {r.action_type}")
                lines.append(f"- **Margin:** {r.margin}")
                lines.append(f"- **base_damage:** {r.replay.get('total_base_damage', '?')}")
                lines.append(f"- **Conditions:** {r.replay.get('conditions', [])}")
                for sname, sresult in r.scores.items():
                    lines.append(f"- **{sname}:** {json.dumps(sresult)}")
            lines.append("")

        # Failed examples (with player action and original comparison)
        if failed_examples:
            lines.append(f"## Failed Examples ({len(failed_examples)} shown)")
            for i, r in enumerate(failed_examples[:5]):
                lines.append(f"\n### Example {i+1}")
                if r.player_action_text:
                    lines.append(f"- **Player action:** \"{r.player_action_text}\"")
                lines.append(f"- **Action type:** {r.action_type}")
                lines.append(f"- **Margin:** {r.margin}")
                # Original vs replay comparison
                orig_bd = r.original.get("total_base_damage", "?")
                replay_bd = r.replay.get("total_base_damage", "?")
                lines.append(f"- **Original base_damage:** {orig_bd} \u2192 **Replay base_damage:** {replay_bd}")
                orig_conds = r.original.get("conditions", [])
                replay_conds = r.replay.get("conditions", [])
                lines.append(f"- **Original conditions:** {orig_conds} \u2192 **Replay conditions:** {replay_conds}")
                if r.replay_response:
                    narration = MechanicalExtractor.parse_response(r.replay_response).get("narration", "")
                    if narration:
                        lines.append(f"- **Narration excerpt:** {narration[:200]}...")
                for sname, sresult in r.scores.items():
                    lines.append(f"- **{sname}:** {json.dumps(sresult)}")
            lines.append("")

        # Regression check results
        if regression_results:
            lines.append("## Regression Check Results")
            lines.append("")
            for reg_name, reg_data in regression_results.items():
                status = "PASS" if reg_data.get("all_met") else "FAIL"
                desc = reg_data.get("description", "")
                lines.append(f"### {reg_name} ({status})")
                if desc:
                    lines.append(f"  {desc}")
                for metric, info in reg_data.get("details", {}).items():
                    met = "PASS" if info.get("met") else "FAIL"
                    actual = info.get("actual", "?")
                    target = info.get("target", "?")
                    # Direction hint for max_* metrics
                    if metric.split(".")[-1].startswith("max_"):
                        lines.append(f"  {metric}: {actual} <= {target} target  {met}")
                    else:
                        lines.append(f"  {metric}: {actual}% >= {target}% target  {met}")
                if not reg_data.get("all_met"):
                    lines.append(
                        f"  → Your rewrite may have harmed {reg_name}. "
                        f"Only suppressive fire should be low-damage."
                    )
                lines.append("")

        # Goal description
        goal_desc = self.goal.get("description", "")
        if goal_desc:
            lines.append(f"## Goal Description")
            lines.append(goal_desc)
            lines.append("")

        if retry_context:
            lines.append("## IMPORTANT: Previous Attempt Failed")
            lines.append(retry_context)
            lines.append("")

        lines.append("## Instruction")
        lines.append(
            "Rewrite the prompt module content to better achieve the targets above. "
            "Return ONLY the rewritten content (what goes inside the `content: |-` field). "
            "Do NOT include YAML frontmatter (version, module, description, etc.). "
            "Keep the same section structure and formatting style."
        )

        return "\n".join(lines)

    def call_judge(self, prompt: str) -> str:
        """Call the judge model to rewrite the module."""
        from aeonisk.multiagent.unified_llm_client import UnifiedAIClient
        kwargs = {"provider": self.judge_provider}
        if self.proxy_url:
            kwargs["use_proxy"] = True
            kwargs["proxy_url"] = self.proxy_url
            if self.proxy_strategy:
                kwargs["proxy_strategy"] = self.proxy_strategy
        client = UnifiedAIClient(**kwargs)

        response = client.chat_completion(
            messages=[
                {"role": "system", "content": "You are a prompt engineering expert. Respond only with the rewritten prompt content."},
                {"role": "user", "content": prompt},
            ],
            model=self.judge_model,
            temperature=0.7,
            max_tokens=8000,
        )
        # Strip any markdown fencing the judge might add
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:yaml|text)?\s*\n?', '', text)
            text = re.sub(r'\n?\s*```$', '', text)
        return text.strip()

    def run(
        self,
        initial_module_path: str,
        module_swapper: ModuleSwapper,
        session_extractor: SessionExtractor,
        replay_engine: ReplayEngine,
        scorers: List[BaseScorer],
        model_specs: List[Tuple[str, str]],
        output_dir: str,
        save_prompts: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> str:
        """
        Run the self-judging iteration loop.

        Returns:
            Path to the best module YAML file.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Load initial module
        module_name, current_content = module_swapper.load_replacement(initial_module_path)

        # Extract cases using goal filters (classifier-first when configured)
        eval_subset = self.goal.get("eval_subset", {})
        classifier_config = self.goal.get("classifier")
        cases, intent_labels = _extract_and_classify(
            session_extractor, eval_subset, module_swapper,
            classifier_config=classifier_config,
            proxy_url=self.proxy_url,
            proxy_strategy=self.proxy_strategy,
        )

        if not cases:
            print("No eval cases found matching goal filters. Aborting.", file=sys.stderr)
            return initial_module_path

        best_content = current_content
        best_score_value = -float("inf")
        best_iteration = 0
        convergence = []
        min_improvement = self.goal.get("convergence", {}).get("min_improvement", 2)

        for iteration in range(1, self.max_iterations + 1):
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Self-Judge Iteration {iteration}/{self.max_iterations}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

            # Build modified prompts for all cases
            modified_prompts = {}
            for case in cases:
                try:
                    modified_prompts[case.case_id] = module_swapper.swap_module(
                        case.system_prompt, module_name, current_content
                    )
                except ValueError:
                    # Module not found in this case's prompt - use original
                    modified_prompts[case.case_id] = case.system_prompt

            # Run main replay and regressions concurrently — both are
            # independent API replay batches, no need to serialize
            with ThreadPoolExecutor(max_workers=2) as pool:
                main_future = pool.submit(
                    replay_engine.replay_batch,
                    cases, modified_prompts, model_specs, scorers,
                    save_prompts=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    label="main",
                )
                reg_future = pool.submit(
                    self._run_regressions,
                    module_name, current_content, module_swapper,
                    session_extractor, replay_engine, model_specs,
                    output_dir=str(output_path),
                    iteration=iteration,
                    temperature=temperature, max_tokens=max_tokens,
                )

                results = main_future.result()
                regression_results = reg_future.result()

            # Score & report
            report, score_dict = ReportGenerator.generate(results, module_name, scorers)
            print(report, file=sys.stderr)

            # Save iteration artifacts
            iter_module_path = output_path / f"iteration_{iteration}_module.yaml"
            iter_results_path = output_path / f"iteration_{iteration}_results.jsonl"
            iter_report_path = output_path / f"iteration_{iteration}_report.txt"

            # Save module YAML
            _write_module_yaml(iter_module_path, module_name, current_content,
                               description=f"Self-judge iteration {iteration}")

            ResultStore(str(iter_results_path)).save_results(results)
            with open(iter_report_path, "w") as f:
                f.write(report)

            # Check targets
            all_met, target_details = self.check_targets(score_dict)

            # Compute aggregate score (average of "met" percentage)
            met_count = sum(1 for d in target_details.values() if d["met"])
            score_value = met_count / max(len(target_details), 1) * 100

            convergence.append({
                "iteration": iteration,
                "score_pct": score_value,
                "targets_met": met_count,
                "targets_total": len(target_details),
                "details": target_details,
            })

            # Track best and rollback on regression
            if score_value > best_score_value:
                best_score_value = score_value
                best_content = current_content
                best_iteration = iteration
            elif score_value < best_score_value:
                print(f"  Score regressed ({score_value:.0f}% < best {best_score_value:.0f}% from iter {best_iteration}). Rolling back.", file=sys.stderr)
                current_content = best_content

            if all_met:
                print(f"\nAll targets met at iteration {iteration}!", file=sys.stderr)
                break

            # Check convergence (must stall vs both best AND previous)
            if len(convergence) >= 2:
                improvement_vs_best = convergence[-1]["score_pct"] - best_score_value
                improvement_vs_prev = convergence[-1]["score_pct"] - convergence[-2]["score_pct"]
                if improvement_vs_best <= 0 and abs(improvement_vs_prev) < min_improvement and iteration > 2:
                    print(f"\nConverged (vs best: {improvement_vs_best:+.1f}%, vs prev: {improvement_vs_prev:+.1f}%). Stopping.", file=sys.stderr)
                    break

            # Confirm with user if requested
            if self.confirm_each:
                print(f"\nIteration {iteration} complete. Continue? [y/n] ", end="", file=sys.stderr)
                answer = input().strip().lower()
                if answer != "y":
                    print("Stopped by user.", file=sys.stderr)
                    break

            # Get failed and success examples for judge prompt
            failed = [r for r in results if r.scores and not all(
                s.get("in_range", True) for s in r.scores.values() if isinstance(s, dict)
            )]
            success = [r for r in results if r.scores and all(
                s.get("in_range", True) for s in r.scores.values() if isinstance(s, dict)
            )]

            # Call judge to rewrite (with rollback + retry)
            max_retries = 2
            for retry in range(max_retries + 1):
                retry_context = None
                if retry > 0:
                    retry_context = (
                        f"Your previous rewrite (attempt {retry}) made scores worse or didn't improve enough. "
                        f"Try a fundamentally different approach to the prompt structure."
                    )

                judge_prompt = self.build_judge_prompt(
                    current_content, score_dict, target_details, failed,
                    retry_context=retry_context,
                    iteration_history=convergence,
                    success_examples=success,
                    regression_results=regression_results,
                )

                print(f"  Calling judge model ({self.judge_provider}:{self.judge_model})...", file=sys.stderr)
                new_content = self.call_judge(judge_prompt)

                if not new_content or len(new_content) < 100:
                    print(f"  Judge returned empty/short response, retrying...", file=sys.stderr)
                    continue

                current_content = new_content
                break

        # Save best module
        best_path = output_path / "final_module.yaml"
        _write_module_yaml(best_path, module_name, best_content,
                           description="Best-scoring module from self-judge iteration")

        # Save convergence
        convergence_path = output_path / "convergence.json"
        with open(convergence_path, "w") as f:
            json.dump(convergence, f, indent=2)

        print(f"\nBest module saved to: {best_path}", file=sys.stderr)
        print(f"Convergence data: {convergence_path}", file=sys.stderr)

        # Phase 2: Validation on full dataset (if configured)
        validation_config = self.goal.get("validation", {})
        if validation_config.get("use_all_cases"):
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Phase 2: Validation (full dataset)", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

            # Use same eval_subset but with no max_cases for full validation
            val_subset = dict(self.goal.get("eval_subset", {}))
            val_subset["max_cases"] = None  # No limit — use ALL matching cases
            validation_cases, _ = _extract_and_classify(
                session_extractor, val_subset, module_swapper,
                classifier_config=classifier_config,
                proxy_url=self.proxy_url,
                proxy_strategy=self.proxy_strategy,
            )

            if validation_cases:
                # Build modified prompts with best content
                validation_prompts = {}
                for case in validation_cases:
                    try:
                        validation_prompts[case.case_id] = module_swapper.swap_module(
                            case.system_prompt, module_name, best_content
                        )
                    except ValueError:
                        validation_prompts[case.case_id] = case.system_prompt

                validation_results = replay_engine.replay_batch(
                    validation_cases, validation_prompts, model_specs, scorers,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    label="validation",
                )

                # Save validation artifacts
                validation_results_path = output_path / "validation_results.jsonl"
                ResultStore(str(validation_results_path)).save_results(validation_results)

                validation_report, validation_scores = ReportGenerator.generate(
                    validation_results, module_name, scorers
                )
                validation_report_path = output_path / "validation_report.txt"
                with open(validation_report_path, "w") as f:
                    f.write(validation_report)

                print(f"\n--- Validation (full dataset: {len(validation_cases)} cases) ---", file=sys.stderr)
                print(validation_report, file=sys.stderr)

                _, validation_details = self.check_targets(validation_scores)
                for metric, info in validation_details.items():
                    status = "PASS" if info["met"] else "FAIL"
                    print(f"  {metric}: {info['actual']} (target {info['target']}) \u2192 {status}", file=sys.stderr)
            else:
                print("  No validation cases found.", file=sys.stderr)

        return str(best_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_proxy_strategy(args) -> Optional[str]:
    """Resolve the proxy strategy from explicit flags.

    Precedence: --strategy > --batch > --direct. When --proxy is set with
    no strategy flag, defaults to 'direct' — the harness is interactive,
    so it must never silently fall back to the batch queue. Returns None
    when no proxy is in play.
    """
    if getattr(args, "strategy", None):
        return args.strategy
    if getattr(args, "batch", False):
        return "batch"
    if getattr(args, "direct", False):
        return "direct"
    return "direct" if getattr(args, "proxy", None) else None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Prompt Evaluation Harness - replay DM resolution calls with swapped prompt modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan available cases
  %(prog)s --swap-module path/to/module.yaml --scan-only

  # Quick eval against one model
  %(prog)s --swap-module path/to/module.yaml --models openai:gpt-5-mini --max-cases 20

  # Full eval with proxy
  %(prog)s --swap-module path/to/module.yaml \\
    --models openai:gpt-5-mini deepinfra:deepseek-ai/DeepSeek-V3.2 \\
    --action-type combat --intent-filter suppress \\
    --scorers suppression_table damage_comparison \\
    --proxy http://localhost:8000 --batch

  # Self-judging iteration
  %(prog)s --swap-module path/to/module.yaml \\
    --self-judge --goal-file goals/suppress_goals.yaml \\
    --judge-model anthropic:claude-sonnet-4-5 --max-iterations 5
""",
    )

    # Required
    parser.add_argument(
        "--swap-module", required=True,
        help="Path to replacement YAML module (must have 'module' and 'content' fields)",
    )

    # Session data
    parser.add_argument(
        "--sessions", nargs="+", type=str, default=None,
        help="Override session data directories (default: lethality experiment dirs)",
    )

    # Models
    parser.add_argument(
        "--models", nargs="+", default=["openai:gpt-5-mini"],
        help="Models as provider:model (e.g., openai:gpt-5-mini deepinfra:deepseek-ai/DeepSeek-V3.2 grok:grok-4-latest)",
    )

    # Workers & rate limiting
    parser.add_argument("--workers", type=int, default=4, help="Concurrent replay threads (default: 4)")
    parser.add_argument(
        "--request-delay", type=float, default=None,
        help="Seconds between requests per worker (default: 0.5 direct, 0.0 proxy)",
    )

    # Proxy
    parser.add_argument("--proxy", type=str, default=None, help="Proxy URL (e.g., http://localhost:8000)")
    parser.add_argument(
        "--strategy", type=str, default=None, choices=["auto", "direct", "batch"],
        help="Proxy routing strategy. Default when --proxy is set: direct "
             "(never silently falls back to the batch queue).")
    parser.add_argument("--batch", action="store_true", help="Alias for --strategy batch (50%% cost savings)")
    parser.add_argument("--direct", action="store_true", help="Alias for --strategy direct (immediate)")

    # Filters
    parser.add_argument("--action-type", type=str, default=None, help="Filter by action type (combat, investigate, ...)")
    parser.add_argument("--intent-filter", type=str, default=None, help="Single keyword match on player action text (backward compat)")
    parser.add_argument(
        "--intent-keywords", nargs="+", default=None,
        help="Multi-keyword OR match on player action text AND player intent (e.g., suppress \"covering fire\" \"pin down\")",
    )
    parser.add_argument(
        "--exclude-keywords", nargs="+", default=None,
        help="Exclude cases where any keyword matches player action text or intent (e.g., suppress \"covering fire\")",
    )
    parser.add_argument("--weapon-damage-type", type=str, default=None, help="Filter by weapon damage type (wound, stun)")
    parser.add_argument("--original-model", type=str, default=None, help="Filter by original model")
    parser.add_argument("--module-filter", type=str, default=None, help="Only cases where module was detected")
    parser.add_argument(
        "--margin-range", type=str, default=None,
        help="Filter by margin range, e.g. '11-99'",
    )
    parser.add_argument("--max-cases", type=int, default=None, help="Limit number of cases")

    # Scoring
    parser.add_argument(
        "--scorers", nargs="+", default=["damage_comparison"],
        choices=list(SCORER_REGISTRY.keys()),
        help="Scoring strategies (default: damage_comparison)",
    )

    # Output
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Output directory (default: results/eval_<timestamp>/). Contains metadata.json, swap_module.yaml, results.jsonl, report.txt",
    )

    # Modes
    parser.add_argument("--scan-only", action="store_true", help="Count/list cases without calling LLMs")
    parser.add_argument("--dry-run", action="store_true", help="Show modified prompts without calling LLMs")
    parser.add_argument("--resume", action="store_true", help="Skip completed cases in output file")
    parser.add_argument("--save-prompts", action="store_true", help="Include full prompts in output (for fine-tuning)")

    # LLM params
    parser.add_argument("--temperature", type=float, default=0.7, help="LLM temperature (default: 0.7)")
    parser.add_argument("--max-tokens", type=int, default=4000, help="LLM max tokens (default: 4000)")

    # Self-judging
    parser.add_argument("--self-judge", action="store_true", help="Enable self-judging iteration loop")
    parser.add_argument("--goal-file", type=str, default=None, help="YAML file defining target metrics")
    parser.add_argument("--judge-model", type=str, default="anthropic:claude-sonnet-4-5", help="Judge model as provider:model (default: anthropic:claude-sonnet-4-5)")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max self-judge iterations")
    parser.add_argument("--confirm-each-iteration", action="store_true", help="Pause between self-judge iterations")

    # Intent classification
    parser.add_argument(
        "--classify-intent", action="store_true",
        help="Enable LLM intent classification (uses goal file 'classifier' section or defaults)",
    )

    # Verbosity
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    return parser.parse_args(argv)


def _create_output_dir(
    args: argparse.Namespace,
    module_name: str,
    module_content: str,
    model_specs: List[Tuple[str, str]],
) -> Path:
    """
    Create a timestamped output directory with metadata and the swap module.

    Structure:
        <output_dir>/eval_<timestamp>_<uuid>/
            metadata.json       # Run config
            swap_module.yaml    # The exact prompt module used
            results.jsonl       # (created later by ResultStore)
            report.txt          # (created later)

    If --resume and the output_dir already exists as a timestamped eval dir
    (contains metadata.json), reuse it instead of creating a new one.
    """
    base_dir = Path(args.output_dir or "evals/results")

    # Resume: if output_dir points to an existing eval dir, reuse it
    if args.resume and base_dir.exists() and (base_dir / "metadata.json").exists():
        return base_dir

    # Create timestamped subdirectory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_uuid = str(uuid.uuid4())[:8]
    output_dir = base_dir / f"eval_{timestamp}_{run_uuid}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write metadata
    metadata = {
        "swap_module": args.swap_module,
        "module_name": module_name,
        "models": [f"{p}:{m}" for p, m in model_specs],
        "action_type": args.action_type,
        "intent_filter": args.intent_filter,
        "intent_keywords": args.intent_keywords,
        "weapon_damage_type": args.weapon_damage_type,
        "original_model": args.original_model,
        "margin_range": args.margin_range,
        "max_cases": args.max_cases,
        "scorers": args.scorers,
        "workers": args.workers,
        "proxy": args.proxy,
        "proxy_strategy": resolve_proxy_strategy(args),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "save_prompts": args.save_prompts,
        "sessions": args.sessions,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Copy original prompt YAML (preserves filename as baseline reference)
    import shutil
    original_name = Path(args.swap_module).name
    shutil.copy2(args.swap_module, output_dir / original_name)

    return output_dir


def main(argv=None):
    args = parse_args(argv)

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # Suppress noisy warnings from unified_llm_client (e.g., gpt-5-mini temperature override)
    if not args.verbose:
        logging.getLogger("aeonisk.multiagent.unified_llm_client").setLevel(logging.ERROR)

    # Init components
    module_swapper = ModuleSwapper()
    module_name, new_content = module_swapper.load_replacement(args.swap_module)
    print(f"Module: {module_name} ({len(new_content)} chars)", file=sys.stderr)

    # Parse model specs (provider:model format)
    model_specs = []
    for spec in args.models:
        model_specs.append(parse_model_spec(spec))

    session_dirs = [Path(p) for p in args.sessions] if args.sessions else None
    extractor = SessionExtractor(session_dirs)

    # Parse margin range
    margin_range = None
    if args.margin_range:
        parts = args.margin_range.split("-")
        if len(parts) == 2:
            margin_range = (int(parts[0]), int(parts[1]))

    # --- Load classifier config from goal file if available ---
    classifier = None
    intent_labels: Dict[str, str] = {}
    classifier_config = None

    if args.goal_file:
        with open(args.goal_file, "r") as f:
            goal_data = yaml.safe_load(f)
        classifier_config = goal_data.get("classifier")

    # Determine proxy strategy for classifier
    proxy_strategy_for_cls = resolve_proxy_strategy(args)
    if args.proxy:
        print(f"Proxy: {args.proxy} (strategy: {proxy_strategy_for_cls})")

    # --- Extract cases (classifier-first when active) ---
    use_classifier = (args.classify_intent or classifier_config) and not args.self_judge

    if use_classifier and classifier_config:
        # Classifier-first path: extract broadly, classify, filter
        eval_subset = {
            "action_type": args.action_type,
            "weapon_damage_type": args.weapon_damage_type,
            "max_cases": args.max_cases,
        }
        cases, intent_labels = _extract_and_classify(
            extractor, eval_subset, module_swapper,
            classifier_config=classifier_config,
            proxy_url=args.proxy,
            proxy_strategy=proxy_strategy_for_cls,
        )
        # Create classifier instance for scan-only label display
        classifier = IntentClassifier(
            config=classifier_config,
            proxy_url=args.proxy,
            proxy_strategy=proxy_strategy_for_cls,
        )
    else:
        # No classifier: extract with all CLI filters
        cases = extractor.extract_cases(
            action_type_filter=args.action_type,
            intent_filter=args.intent_filter,
            intent_keywords=args.intent_keywords,
            exclude_keywords=args.exclude_keywords,
            weapon_damage_type=args.weapon_damage_type,
            original_model_filter=args.original_model,
            module_filter=args.module_filter,
            margin_range=margin_range,
            max_cases=args.max_cases,
            module_swapper=module_swapper,
        )

        # Classify without filtering if --classify-intent but no goal file config
        if args.classify_intent and not args.self_judge:
            config = classifier_config or {}
            classifier = IntentClassifier(
                config=config,
                proxy_url=args.proxy,
                proxy_strategy=proxy_strategy_for_cls,
            )
            intent_labels = classifier.classify(cases)

    if not cases:
        print("No eval cases found. Check filters and session directories.", file=sys.stderr)
        return 1

    # --- Scan only ---
    if args.scan_only:
        print(f"\nFound {len(cases)} eval cases\n")

        # Verbose: per-case keyword audit
        if args.verbose:
            active_keywords = args.intent_keywords or []
            print(f"--- Case Audit ({len(cases)} cases) ---\n")
            for c in cases:
                action_text = (c.player_action_text or "").lower()
                intent_text = (c.player_intent or "").lower()
                matches = []
                for kw in active_keywords:
                    kw_lower = kw.lower()
                    if kw_lower in action_text:
                        # Find context around the match
                        idx = action_text.index(kw_lower)
                        start = max(0, idx - 30)
                        end = min(len(action_text), idx + len(kw_lower) + 30)
                        ctx = action_text[start:end].replace("\n", " ")
                        matches.append(f"action: \"...{ctx}...\"")
                    if kw_lower in intent_text:
                        matches.append(f"intent: \"{intent_text[:100]}\"")

                print(f"  {c.case_id}  margin={c.margin}")
                if matches:
                    for m in matches:
                        print(f"    matched → {m}")
                else:
                    print(f"    matched → (no keyword match detail available)")
                # Show truncated action for review
                action_snippet = (c.player_action_text or "")[:120].replace("\n", " ")
                print(f"    action:  {action_snippet}")
                if c.player_intent:
                    print(f"    intent:  {c.player_intent[:120]}")
                # Show classifier label if available
                eid = c.event_id or c.case_id
                if eid in intent_labels:
                    label = intent_labels[eid]
                    marker = ""
                    if classifier:
                        if label in classifier.keep_labels:
                            marker = " (KEEP)"
                        elif label in classifier.drop_labels:
                            marker = " (DROP)"
                        else:
                            marker = " (REVIEW)"
                    print(f"    label:   {label}{marker}")
                print()

        # Group by condition
        by_condition: Dict[str, int] = {}
        by_action: Dict[str, int] = {}
        by_model: Dict[str, int] = {}
        for c in cases:
            by_condition[c.condition] = by_condition.get(c.condition, 0) + 1
            by_action[c.action_type or "unknown"] = by_action.get(c.action_type or "unknown", 0) + 1
            by_model[c.original_model] = by_model.get(c.original_model, 0) + 1

        print("By condition:")
        for k, v in sorted(by_condition.items()):
            print(f"  {k}: {v}")
        print("\nBy action type:")
        for k, v in sorted(by_action.items()):
            print(f"  {k}: {v}")
        print("\nBy original model:")
        for k, v in sorted(by_model.items()):
            print(f"  {k}: {v}")

        # Module detection
        module_counts: Dict[str, int] = {}
        for c in cases:
            for m in c.detected_modules:
                module_counts[m] = module_counts.get(m, 0) + 1
        if module_counts:
            print("\nDetected modules:")
            for k, v in sorted(module_counts.items(), key=lambda x: -x[1]):
                print(f"  {k}: {v}")

        # Swap compatibility
        swappable = 0
        for c in cases:
            try:
                module_swapper.swap_module(c.system_prompt, module_name, new_content)
                swappable += 1
            except ValueError:
                pass
        print(f"\nSwappable for '{module_name}': {swappable}/{len(cases)}")

        # Classifier summary for scan-only
        if classifier and intent_labels:
            from collections import Counter
            label_counts = Counter(intent_labels.values())
            print(f"\nClassifier ({classifier.provider}:{classifier.model}):")
            for label, count in sorted(label_counts.items()):
                action = ""
                if label in classifier.keep_labels:
                    action = " → KEEP"
                elif label in classifier.drop_labels:
                    action = " → DROP"
                else:
                    action = " → REVIEW"
                print(f"  {label}: {count}{action}")
            print(f"  Would keep {sum(1 for l in intent_labels.values() if l in classifier.keep_labels)}/{len(cases)} cases for eval")

        return 0

    # --- Dry run ---
    if args.dry_run:
        show_count = min(args.max_cases or 3, 3, len(cases))
        print(f"\nDry run: showing {show_count} modified prompts\n")
        for case in cases[:show_count]:
            try:
                modified = module_swapper.swap_module(case.system_prompt, module_name, new_content)
            except ValueError as e:
                print(f"[{case.case_id}] Cannot swap: {e}")
                continue

            print(f"=== Case: {case.case_id} ===")
            print(f"  Condition: {case.condition}")
            print(f"  Action type: {case.action_type}")
            print(f"  Margin: {case.margin}")
            print(f"  Original model: {case.original_model}")
            print(f"  System prompt length: {len(modified)} chars")
            print(f"  User prompt length: {len(case.user_prompt)} chars")
            # Show a snippet around the swapped region
            idx = modified.find(new_content[:100])
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(modified), idx + len(new_content) + 50)
                print(f"  Swapped region (chars {idx}-{idx+len(new_content)}):")
                print(f"    ...{modified[start:start+200]}...")
            print()
        return 0

    # --- Apply intent classifier filtering (only for non-classifier-first path) ---
    if classifier and intent_labels and not use_classifier:
        kept, review = classifier.filter_cases(cases, intent_labels)
        if review:
            print(f"\n  Cases needing review ({len(review)}):", file=sys.stderr)
            for c in review:
                eid = c.event_id or c.case_id
                label = intent_labels.get(eid, "?")
                action = (c.player_action_text or "")[:100].replace("\n", " ")
                print(f"    {c.case_id} [{label}]: {action}", file=sys.stderr)
            print(file=sys.stderr)
        cases = kept
        if not cases:
            print("No cases remaining after classification. Aborting.", file=sys.stderr)
            return 1

    # --- Common setup for eval modes ---

    # Determine proxy strategy
    proxy_strategy = resolve_proxy_strategy(args)

    request_delay = args.request_delay
    if request_delay is None:
        request_delay = 0.0 if args.proxy else 0.5

    replay_engine = ReplayEngine(
        workers=args.workers,
        request_delay=request_delay,
        proxy_url=args.proxy,
        proxy_strategy=proxy_strategy,
        verbose=args.verbose,
    )

    scorers = [SCORER_REGISTRY[name]() for name in args.scorers]

    # Create timestamped output directory (like bulk_session_runner)
    output_dir = _create_output_dir(args, module_name, new_content, model_specs)
    results_path = str(output_dir / "results.jsonl")
    report_path = str(output_dir / "report.txt")

    print(f"Output directory: {output_dir}", file=sys.stderr)

    # --- Self-judge mode ---
    if args.self_judge:
        if not args.goal_file:
            print("--self-judge requires --goal-file", file=sys.stderr)
            return 1

        judge = SelfJudge(
            goal_file=args.goal_file,
            judge_model=args.judge_model,
            max_iterations=args.max_iterations,
            confirm_each=args.confirm_each_iteration,
            proxy_url=args.proxy,
            proxy_strategy=proxy_strategy,
        )

        best_path = judge.run(
            initial_module_path=args.swap_module,
            module_swapper=module_swapper,
            session_extractor=extractor,
            replay_engine=replay_engine,
            scorers=scorers,
            model_specs=model_specs,
            output_dir=str(output_dir),
            save_prompts=args.save_prompts,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

        print(f"\nBest module: {best_path}")
        return 0

    # --- Normal eval mode ---

    result_store = ResultStore(results_path)

    # Resume support
    completed_keys = set()
    if args.resume:
        completed_keys = result_store.load_completed_keys()
        if completed_keys:
            print(f"Resuming: {len(completed_keys)} results already completed", file=sys.stderr)

    # Build modified prompts — skip cases where module can't be swapped
    modified_prompts = {}
    skipped = 0
    swappable_cases = []
    for case in cases:
        try:
            modified_prompts[case.case_id] = module_swapper.swap_module(
                case.system_prompt, module_name, new_content
            )
            swappable_cases.append(case)
        except ValueError:
            skipped += 1

    if skipped:
        print(f"Skipped {skipped}/{len(cases)} cases (module not found in prompt — old/incompatible sessions)", file=sys.stderr)
    cases = swappable_cases
    if not cases:
        print("No swappable cases remaining. Check --sessions directories.", file=sys.stderr)
        return 1

    # Open output file for streaming writes (results saved as they complete)
    result_store.open(append=args.resume)

    # Replay — results stream to disk via on_result callback
    results = replay_engine.replay_batch(
        cases, modified_prompts, model_specs, scorers,
        save_prompts=args.save_prompts,
        completed_keys=completed_keys,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        on_result=result_store.append_result,
    )

    result_store.close()

    # Report
    all_results = results
    if args.resume and completed_keys:
        # Reload all for full report (includes both previous + new results)
        all_stored = []
        with open(results_path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    all_stored.append(ReplayResult(
                        case_id=data["case_id"],
                        condition=data.get("condition", ""),
                        round_num=data.get("round"),
                        action_type=data.get("action_type"),
                        original_model=data.get("original_model", ""),
                        eval_model=data["eval_model"],
                        margin=data.get("margin"),
                        original=data.get("original", {}),
                        replay=data.get("replay", {}),
                        scores=data.get("scores", {}),
                        error=data.get("error"),
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
        all_results = all_stored

    report, _ = ReportGenerator.generate(all_results, module_name, scorers)
    print(f"\n{report}")

    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to: {report_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
