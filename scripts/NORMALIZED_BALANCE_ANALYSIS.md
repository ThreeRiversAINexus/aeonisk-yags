# Normalized Balance Analysis Report

## Overview

This document summarizes the attribute-normalized balance analysis of 587 archived game sessions containing 1,488 skill checks. The analysis adjusts success rates by player ability levels (attribute × skill) to provide a more accurate assessment of game difficulty and balance.

## Key Tools

### `analyze_balance_normalized.py`
Comprehensive normalized analysis including:
- Success rates by ability level buckets
- Attribute usage patterns
- Skill-specific performance with ability breakdowns
- Difficulty calibration analysis (expected vs. observed success)
- Void and Soulcredit economy tracking

### `quick_archive_stats.py`
Quick session overview with basic normalized success rates.
Usage: `python3 scripts/quick_archive_stats.py [sample_size]`

## Critical Findings

### 1. **Major DC Calibration Issue: "Negative" Ability Players**

**Problem:** Players with negative ability scores (unskilled or low stats) show **65.7% success rate** when the mathematical expectation is **5%** (only nat 20 succeeds).

**Data:**
```
Ability Range: negative (ability -5 to -1)
Expected:  5.0% success (need d20 >= 20)
Observed: 65.7% success (379/577 rolls)
Delta:    +60.7% ⚠️
```

**Interpretation:**
- The DM is likely adjusting DC on the fly based on narrative context
- System may be using lower DCs than the standard DC 18 assumption
- Alternative: DM may be granting success on "interesting failures" or partial successes

**Recommendation:**
- Document actual DC distributions in new sessions
- Consider if DC 18 is appropriate baseline (may need DC 12-15 for standard tasks)
- Alternatively, accept that DM narrative adjustments are intentional design

### 2. **Balanced Progression for Moderate-High Ability**

**Observation:** Success rates align well with mathematical expectations for ability 11+:

```
11-20 (moderate):  Expected 90.0%, Observed 93.6% (+3.6%) ✓
21-30 (high):      Expected 100%, Observed 100% (0.0%)   ✓
31+ (expert):      Expected 100%, Observed 100% (0.0%)   ✓
```

**Interpretation:** The system works as intended once characters have moderate investment (ability ~15).

### 3. **Attribute Usage Patterns**

**Most Used Attributes:**
1. **None (24.2%)** - Enemy actions or non-roll events
2. **Perception (21.1%)** - Investigation/awareness dominant playstyle
3. **Empathy (18.9%)** - Social interaction frequent
4. **Charisma (14.4%)** - Persuasion/intimidation common

**Success Rates by Attribute:**
- **Strength (96.3%)** - High success, low usage (power actions work when attempted)
- **Agility (89.8%)** - High success, moderate usage (mobility/stealth reliable)
- **Charisma (43.3%)** - **LOW** success despite high usage ⚠️

**Key Insight:** Charisma-based actions have lowest success rate (43.3%) despite being the 4th most used attribute. This suggests:
- Social challenges are intentionally difficult
- Players attempt persuasion/deception frequently but fail often
- May need mechanical support (retry mechanics, partial successes)

### 4. **Skill-Specific Patterns**

#### High-Success Skills (>90% overall):
- **Guns (97.6%)** - Combat-focused, high ability values
- **Brawl (97.1%)** - Melee combat reliable
- **Awareness (93.0%)** - Perception checks mostly succeed
- **Guile (89.6%)** - Deception/stealth moderately reliable

#### Problematic Skills:
- **Magic Theory (34.6% overall)** - Only succeeds at ability 20+
  - At ability -2: 10% success (1/10)
  - At ability 20+: 100% success (6/6)
  - **Interpretation:** Magic is gated behind skill investment (intentional?)

- **Charm (55.0% overall)** - Charisma-based, wide variance:
  - At ability -4 to 0: 0-17% success
  - At ability 25: 100% success (112/112)
  - **Interpretation:** Social skills have steep learning curve

#### Well-Calibrated Skills:
- **Systems (76.8%)** - Tech/hacking balanced across ability ranges
- **Corporate Influence (84.0%)** - Faction-based actions mostly succeed

### 5. **Unskilled Penalty is Brutal**

**Data:**
```
0 (unskilled): 11.6% success (5/43 rolls)
```

Characters attempting actions with skill_val=0 (and thus -5 unskilled penalty) have extremely low success rates, as intended by YAGS rules. This creates strong incentive for skill specialization.

## Recommendations

### For Game Balance:

1. **Document Actual DCs**
   - Add DC logging to new sessions to understand true difficulty distribution
   - Current assumption of DC 18 baseline may be incorrect
   - Archive data suggests effective DC is closer to 12-15 for routine tasks

2. **Charisma/Social Action Support**
   - Consider mechanical support for failed Charm/persuasion attempts
   - Implement partial success mechanics ("you don't convince them, but they hesitate")
   - Alternative: This may be intentional difficulty to reflect setting's corporate dystopia

3. **Magic Theory Accessibility**
   - Current data shows magic is effectively gated behind ability 20+ investment
   - If this is intentional (magic is rare/hard), document in design docs
   - If not, consider lower-DC magic tasks for beginners

4. **Validate "Negative Ability" Behavior**
   - Investigate why negative ability rolls succeed 65% vs. expected 5%
   - Options:
     - DMs adjusting DC narratively (feature, not bug)
     - Base DC is lower than 18 (update assumptions)
     - Success includes partial/interesting failures (design intent)

### For Data Collection:

1. **Enhanced Logging in New Sessions**
   - Log actual DC values (not just success/failure)
   - Track DC adjustments by DM (if any)
   - Log partial success vs. full success vs. failure

2. **Void/Soulcredit Data**
   - Archive sessions don't include void/SC economy data
   - Run analysis on recent sessions (multiagent_output/) for economy balance

## Statistical Validation

**Sample Size:** 1,488 skill checks across 587 sessions
**Confidence:** High (n > 1000)

**Limitations:**
- Archive data lacks combat_action logging (combat balance not analyzable)
- Void/Soulcredit economy data missing from archive
- Actual DC values not logged (using DC 18 assumption)
- DM narrative adjustments not captured in structured data

## Conclusion

The normalized analysis reveals:
- ✅ System works well for moderate-high ability characters (ability 11+)
- ⚠️ Major discrepancy for low-ability characters (65% vs. 5% expected)
- ⚠️ Charisma-based actions have low success despite high usage
- ✅ Combat skills show high reliability (Guns, Brawl >95%)
- ⚠️ Magic and social skills have steep learning curves (intentional?)

**Next Steps:**
1. Run full analysis on recent sessions (multiagent_output/) for Void/SC economy
2. Log actual DC values in new sessions to validate DC 18 assumption
3. Consider mechanical support for Charisma-based partial successes
4. Document whether low-ability success rate is feature (narrative adjustments) or bug (incorrect DCs)
