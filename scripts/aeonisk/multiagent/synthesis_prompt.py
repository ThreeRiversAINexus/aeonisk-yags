"""The outcome-first synthesis prompt, loaded from YAML rather than baked in (#159).

Both halves of this call used to be string literals in `dm.py` — the system
prompt inline at the call site, the user prompt a 2,291-character f-string. That
put the worst prompt in the system beyond the reach of every tool built to
improve it: `prompt_eval_harness.py` swaps YAML modules through `ModuleSwapper`,
so a prompt in Python cannot be swapped, varied, A/B tested or iterated on.

Rendering is `str.format`, which means the template body must contain no braces
of its own. That is asserted in `tests/unit/test_synthesis_prompt_module.py`
alongside the byte-identity check, because a stray brace would not fail loudly —
it would raise mid-session on the one call that turns mechanics into story.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import yaml

MODULE_PATH = (Path(__file__).parent / "prompts" / "claude" / "en" / "dm"
               / "dm_outcome_synthesis.yaml")

#: What the user prompt renders when there is no prior round. Kept here rather
#: than inline so the "opening round" case is visible to anyone reading the
#: module, and so #158's variants can change it in one place.
NO_PRIOR_ROUND = "(opening round)"


@lru_cache(maxsize=8)
def load_module(path: Optional[str] = None) -> Dict[str, Any]:
    """A synthesis prompt module, cached per path.

    Keyed by path rather than cached as a singleton so an eval harness can
    render a variant in the same process without evicting or poisoning the
    module the live session uses — the two must not be able to see each other's
    prompt.
    """
    with open(path or MODULE_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def system_prompt(module: Optional[Dict[str, Any]] = None) -> str:
    """The narrator's role instruction.

    One sentence today. The ~21.7k characters of JSON schema that reach the
    model alongside it are appended by the structured-output layer, which
    already enforces that schema — see #158.
    """
    return (module or load_module())["system_prompt"]


def user_prompt(
    round_num: int,
    safe_payload: Sequence[Dict[str, Any]],
    previous_ending: Optional[str],
    safe_lifecycle: Dict[str, Any],
    module: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the round's synthesis request.

    `previous_ending` is, despite its name, the entire previous round's
    narration. It is preserved exactly as it was so this extraction stays a
    pure move; #158 is where it gets trimmed.

    Pass `module` to render a variant. The default is the module the live
    session uses, so a harness cannot change what a session sends by forgetting
    an argument — the override has to be deliberate.
    """
    return (module or load_module())["user_prompt"].format(
        round_num=round_num,
        outcomes_json=json.dumps(list(safe_payload), indent=2),
        previous_ending=previous_ending or NO_PRIOR_ROUND,
        lifecycle_json=json.dumps(safe_lifecycle, indent=2, default=str),
    )
