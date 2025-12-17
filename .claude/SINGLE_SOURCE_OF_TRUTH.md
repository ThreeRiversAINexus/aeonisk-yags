# Single Source of Truth - Keeping Pydantic and Prompts Aligned

## The Problem ("sigh")

**Current State:** Attribute lists are hardcoded in 6+ different locations:
1. `mechanics.py` - `ATTRIBUTES` constant
2. `player_action.py` - Pydantic Field descriptions (2 places)
3. `player_action.py` - Validator lists (2 places)
4. `character_validator.py` - Validation list
5. `action_schema.py` - Validation list
6. `player.yaml` - Prompt documentation
7. `action_schema.py` - Prompt prose

**What just happened:**
- Fixed Charisma → Dexterity in Pydantic schemas
- BUT missed it in `player.yaml` (had duplicate "Empathy, Empathy" + no Dexterity!)
- Also missed it in `action_schema.py` (duplicate "Empathy" in 2 places)
- **Result:** LLMs still saw bad attribute lists in some prompts

## Files Fixed (Round 2)

1. **`scripts/aeonisk/multiagent/prompts/claude/en/player.yaml:190`**
   - Was: `Strength, Agility, Endurance, Perception, Intelligence, Empathy, Willpower, Empathy, Size`
   - Now: `Strength, Agility, Endurance, Dexterity, Perception, Intelligence, Empathy, Willpower`

2. **`scripts/aeonisk/multiagent/action_schema.py:353`** (prose description)
   - Was: `(Strength, Agility, Endurance, Perception, Intelligence, Empathy, Willpower, Empathy)`
   - Now: `(Strength, Agility, Endurance, Dexterity, Perception, Intelligence, Empathy, Willpower)`

3. **`scripts/aeonisk/multiagent/action_schema.py:94`** (validation list)
   - Was: `["Strength", "Agility", "Endurance", "Perception", "Intelligence", "Empathy", "Willpower", "Empathy"]`
   - Now: `["Strength", "Agility", "Endurance", "Dexterity", "Perception", "Intelligence", "Empathy", "Willpower"]`

## Current Sources of Truth (All 8 now correct!)

| Location | Purpose | Format |
|----------|---------|--------|
| `mechanics.py:1865` | MechanicsEngine validation | Python list |
| `character_validator.py:31` | Config validation | Python list |
| `action_schema.py:94` | Action validation | Python list |
| `player_action.py:154` | Pydantic validator | Python list |
| `player_action.py:959` | Pydantic validator | Python list |
| `player_action.py:107` | Pydantic Field description (JSON schema) | String |
| `player_action.py:815` | Pydantic Field description (JSON schema) | String |
| `player.yaml:190` | LLM prompt documentation | YAML prose |
| `action_schema.py:353` | LLM prompt documentation | Python f-string |

**All now contain:** `Strength, Agility, Endurance, Dexterity, Perception, Intelligence, Empathy, Willpower`

## Long-Term Solution Options

### Option 1: Single Python Constant (Simplest)

Create a canonical constant and import it everywhere:

```python
# scripts/aeonisk/multiagent/constants.py
YAGS_ATTRIBUTES = [
    "Strength", "Agility", "Endurance", "Dexterity",
    "Perception", "Intelligence", "Empathy", "Willpower"
]
```

**Then:**
- Python validators: `from .constants import YAGS_ATTRIBUTES`
- Pydantic Field descriptions: `description=f"Attribute used: {', '.join(YAGS_ATTRIBUTES)}"`
- Prompt templates: Use Jinja2 to inject `{{ valid_attributes }}`

**Pros:**
- Single source of truth in code
- Type-safe (Python import errors if file missing)
- Easy to update (change 1 list, everything updates)

**Cons:**
- Prompts need template variable substitution
- Slightly more complex prompt loading

### Option 2: Pydantic Enum (Type-Safe)

```python
# scripts/aeonisk/multiagent/schemas/shared_types.py
class Attribute(str, Enum):
    STRENGTH = "Strength"
    AGILITY = "Agility"
    ENDURANCE = "Endurance"
    DEXTERITY = "Dexterity"
    PERCEPTION = "Perception"
    INTELLIGENCE = "Intelligence"
    EMPATHY = "Empathy"
    WILLPOWER = "Willpower"

# In player_action.py
attribute: Attribute = Field(...)
```

**Pros:**
- Type-safe (IDE autocomplete, mypy validation)
- JSON schema auto-generates from enum
- Impossible to typo an attribute name

**Cons:**
- More verbose in code
- Still need to document in prompts separately

### Option 3: Schema-Driven (Most Robust)

Store canonical schema in YAML, generate Python from it:

```yaml
# config/yags_schema.yaml
attributes:
  - name: Strength
    description: Physical power
  - name: Agility
    description: Speed and reflexes
  # ...
```

Then:
- Python codegen: `generate_constants.py` → `constants.py`
- Prompt templates: Jinja2 loads from same YAML
- Pydantic: Generated enums

**Pros:**
- True single source of truth
- Self-documenting (descriptions in one place)
- Can version schema changes

**Cons:**
- Build step complexity
- Overkill for just 8 attributes

## Recommended Approach: Option 1 + Validation Tests

**Phase 1: Centralize the constant**
```python
# scripts/aeonisk/multiagent/constants.py (NEW FILE)
"""
Canonical game constants - SINGLE SOURCE OF TRUTH.

When modifying attributes, skills, or other game constants:
1. Update this file ONLY
2. Run: python -m pytest tests/unit/test_constants_alignment.py
3. The test will verify all hardcoded lists match this file
"""

YAGS_ATTRIBUTES = [
    "Strength", "Agility", "Endurance", "Dexterity",
    "Perception", "Intelligence", "Empathy", "Willpower"
]

ATTRIBUTES_STRING = ", ".join(YAGS_ATTRIBUTES)  # For descriptions
```

**Phase 2: Replace hardcoded lists**
```python
# mechanics.py
from .constants import YAGS_ATTRIBUTES
class MechanicsEngine:
    ATTRIBUTES = YAGS_ATTRIBUTES  # Now references constant

# player_action.py
from .constants import ATTRIBUTES_STRING
attribute: str = Field(
    description=f"Attribute used: {ATTRIBUTES_STRING}"
)

# Validators
from .constants import YAGS_ATTRIBUTES
@field_validator("attribute")
def validate_attribute(cls, v):
    if v not in YAGS_ATTRIBUTES:
        raise ValueError(f"Attribute must be one of: {YAGS_ATTRIBUTES}")
```

**Phase 3: Add regression test**
```python
# tests/unit/test_constants_alignment.py
import re
from scripts.aeonisk.multiagent.constants import YAGS_ATTRIBUTES

def test_all_attribute_lists_match_canonical():
    """Ensure NO hardcoded attribute lists exist - all must reference constants.py"""

    # Search for hardcoded lists
    violations = []

    # Check player_action.py doesn't have hardcoded lists
    with open("scripts/aeonisk/multiagent/schemas/player_action.py") as f:
        content = f.read()
        if '["Strength", "Agility"' in content:
            violations.append("player_action.py has hardcoded attribute list")

    # Check prompts use template variables
    with open("scripts/aeonisk/multiagent/prompts/claude/en/player.yaml") as f:
        content = f.read()
        if "Strength, Agility, Endurance" in content and "{{" not in content:
            violations.append("player.yaml has hardcoded attributes without template var")

    assert not violations, f"Found hardcoded attributes: {violations}"
```

## Migration Plan

### Immediate (Done ✅)
- [x] Fixed all hardcoded lists to include Dexterity
- [x] Removed duplicate "Empathy" entries
- [x] Removed "Charisma" from all lists
- [x] Removed "Size" from VALID_ATTRIBUTES lists (Size is secondary stat, not core attribute)

### Short-term (Next PR)
1. Create `constants.py` with `YAGS_ATTRIBUTES`
2. Replace all Python list literals with imports
3. Update Pydantic Field descriptions to use f-strings
4. Add `test_constants_alignment.py` to catch regressions

### Medium-term (Future)
1. Migrate prompts to Jinja2 templates
2. Inject `{{ valid_attributes }}` dynamically
3. Consider Pydantic Enum for type safety

## Prevention Strategy

**Git pre-commit hook:**
```bash
#!/bin/bash
# .git/hooks/pre-commit

# Check for hardcoded attribute lists (except in constants.py)
if git diff --cached | grep -E '"Strength".*"Agility".*"Endurance"' | grep -v constants.py; then
    echo "ERROR: Found hardcoded attribute list! Use YAGS_ATTRIBUTES from constants.py"
    exit 1
fi
```

**CI/CD validation:**
```yaml
# .github/workflows/validate-constants.yml
- name: Check attribute alignment
  run: python -m pytest tests/unit/test_constants_alignment.py
```

## Key Insight

The problem isn't technical - it's **organizational**. With 9 different files defining "valid attributes," any change requires updating 9 places. Humans will miss some. The solution is:

1. **One canonical source** (constants.py)
2. **All others reference it** (import, not copy-paste)
3. **Tests enforce it** (regression tests catch drift)

This is a classic DRY (Don't Repeat Yourself) violation. We just need to DRY it up.

## Related Issues

This same problem exists for:
- **Skills** - Hardcoded in multiple places
- **Factions** - Some prompts have outdated faction names
- **Action types** - Different files have different lists

Recommend applying same solution to all game constants.
