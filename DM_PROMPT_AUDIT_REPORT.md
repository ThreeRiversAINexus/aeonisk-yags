# DM Prompt Audit Report

**Generated:** 2025-11-18 17:30:39

**Total DM Prompt Lines:** 2051

## Summary

- **Files analyzed:** 11
- **Total lines:** 2051
- **Deprecated markers found:** 3
- **Working notes found:** 2
- **Estimated removable lines:** 117 (5% reduction)

## 🔴 High Priority Files

### dm_conversion_check.yaml

- **Lines:** 667
- **Deprecated markers:** 0
- **Working notes:** 1
- **Estimated removable:** 1 lines
- **Risk level:** medium

**Actions:**
  - Remove 1 working notes (Problem:, TODO:, etc.)
  - Consider splitting file (667 lines is very large)

## 🟡 Medium Priority Files

### dm_commands.yaml

- **Lines:** 256
- **Deprecated markers:** 3
- **Working notes:** 1
- **Estimated removable:** 56 lines

**Actions:**
  - Remove 1 working notes (Problem:, TODO:, etc.)
  - Many examples (11) - consider consolidating most common cases

## 🟢 Low Priority Files

These files appear to be in good shape:

- **dm_core.yaml** (257 lines)
- **dm_structured_output.yaml** (220 lines)
- **dm_attunement.yaml** (158 lines)
- **dm_combat.yaml** (127 lines)
- **dm_state_tracking.yaml** (124 lines)
- **dm_transfer.yaml** (95 lines)
- **dm_purchase.yaml** (68 lines)
- **dm_ml_training.yaml** (50 lines)
- **dm_social.yaml** (29 lines)

## Detailed Findings

### dm_conversion_check.yaml

**File Statistics:**
- Lines: 667
- Sections: 0
- Examples: 0
- Bullet points: 0

**Working Notes (1):**
  - Line 421: `Problem:` → **Problem:** Ignores context - failed actions in hostile zone SHOULD spawn respo

---

### dm_core.yaml

**File Statistics:**
- Lines: 257
- Sections: 9
- Examples: 0
- Bullet points: 46

---

### dm_commands.yaml

**File Statistics:**
- Lines: 256
- Sections: 19
- Examples: 11
- Bullet points: 116

**Deprecated Markers (3):**
  - Line 8: `\[SESSION_END:` → - `[SESSION_END: VICTORY]` - Team achieved their objective\n- `[SESSION_END: DEF
  - Line 9: `\[SESSION_END:` → \ - Team failed catastrophically or was captured/killed\n- `[SESSION_END: DRAW]`
  - Line 66: `\[NEW_CLOCK:` → NO marker parsing ([NEW_CLOCK:...] is deprecated and removed as of Nov 2024).\n\

**Working Notes (1):**
  - Line 147: `Problem:` → \n            )\n        ]\n    )\n)\n```\n**Problem:** Enemy agents don't check

---

### dm_structured_output.yaml

**File Statistics:**
- Lines: 220
- Sections: 5
- Examples: 12
- Bullet points: 12

---

### dm_attunement.yaml

**File Statistics:**
- Lines: 158
- Sections: 14
- Examples: 3
- Bullet points: 47

---

### dm_combat.yaml

**File Statistics:**
- Lines: 127
- Sections: 2
- Examples: 0
- Bullet points: 112

---

### dm_state_tracking.yaml

**File Statistics:**
- Lines: 124
- Sections: 6
- Examples: 4
- Bullet points: 69

---

### dm_transfer.yaml

**File Statistics:**
- Lines: 95
- Sections: 8
- Examples: 0
- Bullet points: 41

---

### dm_purchase.yaml

**File Statistics:**
- Lines: 68
- Sections: 7
- Examples: 0
- Bullet points: 25

---

### dm_ml_training.yaml

**File Statistics:**
- Lines: 50
- Sections: 1
- Examples: 1
- Bullet points: 14

---

### dm_social.yaml

**File Statistics:**
- Lines: 29
- Sections: 1
- Examples: 0
- Bullet points: 0

---
