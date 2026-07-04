"""Shared launch-time config handling for session entry points.

Used by bulk_session_runner.py, aeonisk.multiagent.main, and
prompt_eval_harness.py so all entry points resolve session configs the
same way.

Precedence contract: the session config JSON is authoritative. CLI flags
only take effect when explicitly passed (non-None here), and any explicit
override that CHANGES an existing config value is returned as a report
line the caller must log. Flags that were not passed never touch config
values — a flag's *default* must never overwrite a config choice.

Beneath the config sit two more layers callers should be aware of:
- BatchProxyProvider defaults (llm_batch_provider.py): proxy_strategy
  'auto', proxy_priority 'normal' when the config omits them.
- Environment fallbacks (unified_llm_client.py): LLM_PROXY_MODE,
  USE_LLM_PROXY, LLM_PROXY_URL. effective_routing_report() surfaces
  these when set.
"""

import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

LOG_LEVEL_CHOICES = ["TRACE", "DEBUG", "LLM", "INFO", "WARNING", "ERROR"]

PROXY_STRATEGY_CHOICES = ("auto", "direct", "batch")

_PROXY_ENV_VARS = ("LLM_PROXY_MODE", "USE_LLM_PROXY", "LLM_PROXY_URL")


def iter_agent_llm_configs(config: Dict) -> Iterator[Tuple[str, Dict]]:
    """Yield (agent_label, llm_dict) for DM, players, and enemy agents.

    Covers both the current 'enemies' and legacy 'enemy_agents' shapes.
    Creates the llm dict on DM/players if missing so injection can fill it.
    """
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return

    if isinstance(agents.get("dm"), dict):
        yield "dm", agents["dm"].setdefault("llm", {})

    for player in agents.get("players", []):
        if isinstance(player, dict) and "character_ref" not in player:
            label = player.get("name", "player")
            yield label, player.setdefault("llm", {})

    for key in ("enemies", "enemy_agents"):
        enemy_config = agents.get(key)
        if isinstance(enemy_config, dict) and isinstance(
                enemy_config.get("llm"), dict):
            yield key, enemy_config["llm"]


def _set_reporting(llm: Dict, label: str, field: str, value: Any,
                   origin: str, changes: List[str]) -> None:
    """Set llm[field] = value, appending a report line if that changes an
    existing value."""
    old = llm.get(field)
    if old is not None and old != value:
        changes.append(f"{label}: {field} {old!r} → {value!r} ({origin})")
    llm[field] = value


def apply_proxy_overrides(
    config: Dict,
    proxy_url: Optional[str] = None,
    strategy: Optional[str] = None,
    priority: Optional[str] = None,
) -> List[str]:
    """Apply explicitly-passed proxy CLI flags to every agent LLM config.

    Mutates config in place. Returns report lines for every value an
    explicit flag CHANGED (callers should log these at WARNING). Filling
    a previously-absent field is not reported — effective_routing_report
    shows the final state.

    - proxy_url: switches each agent to the batch_proxy provider
      (preserving the original provider as underlying_provider) and sets
      use_proxy/proxy_url. Does NOT touch proxy_strategy/proxy_priority.
    - strategy / priority: set the respective field, but only on agents
      that are (or are being) routed through the proxy. Without
      proxy_url, plain-provider agents are left alone.
    - All None: no-op.
    """
    changes: List[str] = []
    if proxy_url is None and strategy is None and priority is None:
        return changes

    for label, llm in iter_agent_llm_configs(config):
        proxied = llm.get("provider") == "batch_proxy" or llm.get("use_proxy")

        if proxy_url is not None:
            if not proxied:
                llm["underlying_provider"] = llm.get("provider", "openai")
                changes.append(
                    f"{label}: provider {llm.get('provider', 'openai')!r} "
                    f"→ 'batch_proxy' (--proxy)")
            else:
                llm.setdefault(
                    "underlying_provider", llm.get("provider", "openai"))
            llm["provider"] = "batch_proxy"
            llm["use_proxy"] = True
            _set_reporting(llm, label, "proxy_url", proxy_url,
                           "--proxy", changes)
            proxied = True

        if not proxied:
            continue

        if strategy is not None:
            _set_reporting(llm, label, "proxy_strategy", strategy,
                           "--strategy", changes)
        if priority is not None:
            _set_reporting(llm, label, "proxy_priority", priority,
                           "--priority", changes)

    return changes


def effective_routing_report(config: Dict) -> List[str]:
    """One line per agent describing how its LLM calls will actually route.

    Strategy is annotated with its source: the config value, or the
    provider default 'auto' when absent (BatchProxyProvider fills it).
    Appends warnings for proxy-related environment variables, which
    unified_llm_client consults beneath the config layer.
    """
    lines: List[str] = []
    for label, llm in iter_agent_llm_configs(config):
        provider = llm.get("provider", "?")
        model = llm.get("model", "?")
        if provider == "batch_proxy" or llm.get("use_proxy"):
            strategy = llm.get("proxy_strategy")
            strategy_desc = (
                f"strategy={strategy} (config)" if strategy
                else "strategy=auto (absent → provider default)")
            underlying = llm.get("underlying_provider", "openai")
            url = llm.get("proxy_url", "http://localhost:8000 (default)")
            lines.append(
                f"  {label}: {provider}→{underlying} model={model} "
                f"{strategy_desc} url={url}")
        else:
            lines.append(f"  {label}: {provider} model={model} (no proxy)")

    env_set = [f"{var}={os.environ[var]}" for var in _PROXY_ENV_VARS
               if os.environ.get(var)]
    if env_set:
        lines.append(
            f"  NOTE: proxy env fallbacks active beneath config: "
            f"{', '.join(env_set)}")
    return lines


def _prefix(path: Optional[str]) -> str:
    if not path:
        return ""
    return f"{os.path.basename(str(path))}: "


def validate_session_config(config: Dict,
                            path: Optional[str] = None) -> List[str]:
    """Validate a session config, returning error strings (empty = valid).

    Runtime mirror of the checks in
    tests/unit/test_session_config_validation.py; the tests drive their
    assertions through this function so the two cannot drift.
    """
    p = _prefix(path)
    errors: List[str] = []

    if not isinstance(config, dict):
        return [f"{p}config must be a JSON object"]

    for field in ("session_name", "max_turns", "party_size", "agents"):
        if field not in config:
            errors.append(f"{p}missing required field: {field}")
    agents = config.get("agents")
    if not isinstance(agents, dict):
        if "agents" in config:
            errors.append(f"{p}'agents' must be an object")
        return errors

    if "dm" not in agents:
        errors.append(f"{p}missing agents.dm")
    players = agents.get("players")
    if not isinstance(players, list) or not players:
        errors.append(f"{p}agents.players must be a non-empty list")
        players = []

    # Deprecated patterns
    if isinstance(config.get("scenario"), dict) and \
            "initial_clocks" in config["scenario"]:
        errors.append(
            f"{p}uses deprecated 'scenario.initial_clocks'; "
            f"use root-level 'starting_clocks'")

    # Tactical module dependency
    if config.get("enemy_agents_enabled") and \
            not config.get("tactical_module_enabled"):
        errors.append(
            f"{p}enemy_agents_enabled=true requires "
            f"tactical_module_enabled=true")

    # Vendor system
    freq = config.get("vendor_spawn_frequency")
    if freq is not None and (not isinstance(freq, int) or freq < -1):
        errors.append(f"{p}vendor_spawn_frequency must be an int >= -1")

    errors.extend(_validate_players(players, p))
    errors.extend(_validate_clocks(config, p))
    return errors


def _validate_players(players: List, p: str) -> List[str]:
    errors: List[str] = []
    weapon_library = _load_weapon_library()

    for idx, player in enumerate(players):
        if not isinstance(player, dict):
            errors.append(f"{p}player {idx} must be an object")
            continue
        if "character_ref" in player:
            continue
        name = player.get("name", f"player {idx}")

        for field in ("name", "faction", "llm"):
            if field not in player:
                errors.append(f"{p}player {idx} ({name}) missing "
                              f"required field '{field}'")
        llm = player.get("llm")
        if isinstance(llm, dict):
            for field in ("provider", "model"):
                if field not in llm:
                    errors.append(f"{p}player {idx} ({name}) llm "
                                  f"missing '{field}'")

        if "void_score" in player:
            errors.append(f"{p}player {idx} ({name}) uses deprecated "
                          f"'void_score'; use 'void'")
        if "void" in player:
            void = player["void"]
            if not isinstance(void, int) or not 0 <= void <= 10:
                errors.append(f"{p}player {idx} ({name}) 'void' must be "
                              f"an int 0-10, got {void!r}")

        personality = player.get("personality")
        if isinstance(personality, dict) and "description" in personality:
            desc = personality["description"]
            if not isinstance(desc, str) or not desc:
                errors.append(f"{p}player {idx} ({name}) "
                              f"personality.description must be a "
                              f"non-empty string")

        if weapon_library is not None:
            refs = []
            for slot, weapon_id in (player.get("equipped_weapons")
                                    or {}).items():
                refs.append((slot, weapon_id))
            for weapon_id in player.get("carried_weapons") or []:
                refs.append(("carried", weapon_id))
            for slot, weapon_id in refs:
                if weapon_id and weapon_id != "fists" and \
                        weapon_id not in weapon_library:
                    errors.append(
                        f"{p}player {idx} ({name}) {slot} weapon "
                        f"'{weapon_id}' not in WEAPON_LIBRARY")
    return errors


def _validate_clocks(config: Dict, p: str) -> List[str]:
    errors: List[str] = []
    clocks = config.get("starting_clocks")
    if clocks is None:
        return errors
    if not isinstance(clocks, list):
        return [f"{p}starting_clocks must be a list"]

    terminal = []
    for idx, clock in enumerate(clocks):
        if not isinstance(clock, dict):
            errors.append(f"{p}clock {idx} must be an object")
            continue
        cname = clock.get("name", f"clock {idx}")
        if "name" not in clock:
            errors.append(f"{p}clock {idx} missing 'name'")

        has_old = "current" in clock and "max" in clock
        has_new = "current_ticks" in clock and "max_ticks" in clock
        if not (has_old or has_new):
            errors.append(f"{p}clock {idx} ({cname}) needs current/max "
                          f"or current_ticks/max_ticks")
        else:
            current = clock["current_ticks"] if has_new else clock["current"]
            maximum = clock["max_ticks"] if has_new else clock["max"]
            if not isinstance(current, int) or not isinstance(maximum, int):
                errors.append(f"{p}clock {idx} ({cname}) tick values "
                              f"must be ints")
            elif not 0 <= current <= maximum:
                errors.append(f"{p}clock {idx} ({cname}) current "
                              f"({current}) must be between 0 and max "
                              f"({maximum})")

        for field in ("advance_meaning", "regress_meaning"):
            value = clock.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{p}clock {idx} ({cname}) missing "
                              f"non-empty '{field}'")

        if clock.get("is_terminal_clock"):
            terminal.append(clock)

    if terminal:
        if len(terminal) > 1:
            errors.append(
                f"{p}{len(terminal)} terminal clocks "
                f"({[c.get('name') for c in terminal]}); a scene "
                f"resolves on exactly one")
        # A scenario that authors an ending must define what each beat does.
        for idx, clock in enumerate(clocks):
            cons = clock.get("filled_consequence", "")
            if not isinstance(cons, str) or not cons.strip():
                errors.append(
                    f"{p}terminal-clock config but clock {idx} "
                    f"('{clock.get('name', 'unnamed')}') has no "
                    f"filled_consequence")
        outcome = terminal[0].get("terminal_outcome", "victory")
        if outcome not in ("victory", "defeat", "draw"):
            errors.append(f"{p}invalid terminal_outcome '{outcome}'")
    return errors


def _load_weapon_library() -> Optional[Dict]:
    try:
        from aeonisk.multiagent.weapons import WEAPON_LIBRARY
        return WEAPON_LIBRARY
    except ImportError:
        try:
            from weapons import WEAPON_LIBRARY  # scripts/ dir on sys.path
            return WEAPON_LIBRARY
        except ImportError:
            return None
