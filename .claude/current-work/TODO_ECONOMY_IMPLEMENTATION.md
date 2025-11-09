# Economy & Vending System - Implementation TODO

**Branch:** `economy-and-vending`
**Last Updated:** 2025-01-09
**Status:** Design Complete, Implementation Not Started

---

## Current State

### ✅ Completed

**Design Phase:**
- [x] Complete economy philosophy documented (`.claude/current-work/PURCHASE_VENDING_SYSTEM_DESIGN.md`)
- [x] Hollow Seeds mechanics (3x power, auto-degradation, Codex surveillance)
- [x] Void vs. Soulcredit independence clarified
- [x] Eye of Breach possession + purification recovery mechanics
- [x] Attunement skill + Echo Calibrator system (equalizer item, NOT default starting gear)
- [x] Multi-use energy resource design (consumable/ritual/gear/trade/social)
- [x] 5 vendor types defined (Vending Machine, Human Trader, Black Market, Tempest, Emergency Cache)
- [x] Pre-validation architecture designed (prevent DM hallucination)
- [x] ML research scenarios documented (5 benchmarks for RL research)
- [x] Soulcredit decoupling for reuse across systems

**Test Files Created (Not Yet Passing):**
- [x] `test_purchase_integration.py` - 8 tests for purchase effect processing
- [x] `test_purchase_session_integration.py` - Documents Bug #1 (effects not sent to session)
- [x] `test_purchase_processing.py` - Schema validation tests
- [x] `test_vendor_round_persistence.py` - Vendor persistence across rounds
- [x] `test_energy_economy.py` - Energy conversion/attunement tests
- [x] `test_offering_crafting.py` - Offering system tests
- [x] `test_vendor_persistence.py` - Vendor state tests
- [x] `test_vendor_persistence_integration.py` - Integration tests

**Bug Fixes (Completed Earlier):**
- [x] Bug #1: Effects not sent to session.py (fixed in dm.py:2136)

---

## 🚧 In Progress

**Nothing currently in progress** — Design phase complete, ready to start implementation.

---

## 📋 TODO: Implementation Phases

### Phase 1: Critical Bug Fixes (Immediate - Est. 2-4 hours)

**Priority:** CRITICAL - Blocks all economy features

**Tasks:**
- [ ] **Bug #2:** Rename `energy_inventory` → `energy_purse` across codebase
  - [ ] Update `CharacterState` class (player.py)
  - [ ] Update all references in dm.py, session.py, mechanics.py
  - [ ] Update prompts in `dm_state_tracking.yaml`
  - [ ] Run tests to verify no breakage

- [ ] **Bug #3:** Characters don't receive `starting_energy` from session config
  - [ ] Add `starting_energy` parsing in session.py character initialization
  - [ ] Populate `character.energy_purse` on character creation
  - [ ] Test with `session_config_economic.json`

- [ ] **Bug #4:** Round status doesn't display energy purse
  - [ ] Add energy purse display to round status output (session.py)
  - [ ] Format: `└─ Energy: Drip:3 | Breath:15`
  - [ ] Test in session to verify display

**Verification:**
```bash
# Run session with economic config
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_economic.json

# Check round status output shows:
# - Energy purse (Drip, Breath, Grain, Spark)
# - Vendors present
```

**Tests to Pass:**
- All existing tests should still pass after rename
- New tests in `test_energy_economy.py` should pass

---

### Phase 2: Pre-Validation System (Core Feature - Est. 1 week)

**Priority:** HIGH - Prevents DM hallucination on purchases

**Tasks:**
- [ ] Implement `validate_purchase_request()` in mechanics.py
  - [ ] Check energy purse has sufficient currency
  - [ ] Check vendor exists in scenario
  - [ ] Check item exists in vendor inventory
  - [ ] Return validation result + shortage info

- [ ] Integrate validation into DM prompt flow
  - [ ] Call validation BEFORE DM generates narration
  - [ ] Inject constraints into DM prompt if validation fails
  - [ ] Example: "Quinn has 3 Drip but Blood Offering costs 8 Drip (short by 5)"

- [ ] Implement `process_purchase_effect()` in mechanics.py
  - [ ] Deduct currency from energy_purse
  - [ ] Add items to character inventory
  - [ ] Update vendor inventory (deplete stock)
  - [ ] Log purchase to JSONL

- [ ] Update DM structured output to populate `effects.purchase`
  - [ ] Ensure `PurchaseEffect` schema is used
  - [ ] Verify `serializable_res` includes effects (Bug #1 fix)

**Tests to Pass:**
- `test_purchase_integration.py` (8 tests)
- `test_purchase_session_integration.py`
- `test_purchase_processing.py`

**Verification:**
```bash
# Run economic test session
python3 scripts/run_multiagent_session.py scripts/session_configs/session_config_profit_test.json

# Verify:
# - Players can buy items successfully
# - Insufficient currency shows proper failure narration
# - Energy purse updates correctly
# - Inventory updates correctly
```

---

### Phase 3: Soulcredit Gating by Vendor Type (Polish - Est. 3-5 days)

**Priority:** MEDIUM - Adds social stratification

**Tasks:**
- [ ] Implement Soulcredit thresholds per vendor type
  - [ ] Vending Machine: SC ≥ -2 for access
  - [ ] Human Trader: SC ≥ 0 for normal prices, SC ≥ +3 for negotiation bonus
  - [ ] Black Market: No SC requirement (always accessible)
  - [ ] Tempest Drone: Inverted SC (prefers low SC)
  - [ ] Emergency Cache: No SC requirement (but may be contested)

- [ ] Add SC check to `validate_purchase_request()`
  - [ ] Return SC failure reason if gated
  - [ ] Inject into DM prompt: "This vending machine requires SC ≥ -2, you have SC -5"

- [ ] Update round status to show Soulcredit
  - [ ] Format: `└─ Soulcredit: -2/10 (Monitored)`

- [ ] Add vendor type display to round status
  - [ ] Show active vendors with SC requirements
  - [ ] Example: `Vendors: Black Market Dealer "Vex" (no SC required)`

**Tests to Pass:**
- Create new test: `test_soulcredit_vendor_gating.py`

**Verification:**
```bash
# Test with high-SC character
# - Should access Nexus vending machines

# Test with low-SC character
# - Should be locked out of vending machines
# - Should access Black Market
```

---

### Phase 4: Negotiation & Barter Mechanics (Advanced - Est. 1 week)

**Priority:** LOW - Nice-to-have, not critical path

**Tasks:**
- [ ] Implement purchase intent detection
  - [ ] Simple: "I buy X" → Pre-validate, deterministic
  - [ ] Negotiation: "I offer 5 Drip for 8 Drip item" → DM adjudicates with Charm check
  - [ ] Barter: "I trade intel for Blood Offering" → DM evaluates offer value
  - [ ] Credit: "Can I buy on credit?" → DM checks SC, vendor relationship

- [ ] Add Charm/Guile skill integration
  - [ ] Charm 5+ → -20% vendor prices for Human Traders
  - [ ] Guile 5+ → Black Market trusts you (better inventory access)

- [ ] Implement vendor relationship tracking
  - [ ] Track purchases with each vendor
  - [ ] Repeat customers get better prices
  - [ ] Offending vendor locks them out

**Tests to Pass:**
- Create new test: `test_negotiation_mechanics.py`

**Verification:**
```bash
# Test negotiation scenarios
# - High Charm character negotiates lower price
# - Low Charm character pays full price
# - Barter with non-standard payment (intel, favors)
```

---

### Phase 5: Hollow Seeds & Degradation System (Future Feature - Est. 2 weeks)

**Priority:** LOW - Future expansion, requires full economy foundation

**Tasks:**
- [ ] Implement degradation timers for Raw Seeds
  - [ ] Track `cycles_remaining` for each Raw Seed
  - [ ] Decrement each round/cycle
  - [ ] Auto-convert to Hollow Seeds at 0 cycles

- [ ] Implement Hollow Seeds (3x power multiplier)
  - [ ] Hollow Seeds yield 3x energy when attuned
  - [ ] Using Hollows increases Void (+1 per use)
  - [ ] Hollows accepted by Black Market, rejected by Nexus vendors

- [ ] Implement Codex surveillance
  - [ ] Track degrading Seeds (3+ triggers alert)
  - [ ] Apply SC penalty (-1 to -3 based on severity)
  - [ ] Log to JSONL for ML training data

- [ ] Implement Attunement skill + Echo Calibrator
  - [ ] Attunement skill affects conversion efficiency (5% per skill point)
  - [ ] Echo Calibrator item (40-50% base efficiency)
  - [ ] Ritual Altars (65-90% efficiency, service fees)

- [ ] Add Echo Calibrator as purchasable item
  - [ ] Standard Calibrator: 20 Drip
  - [ ] Professional Calibrator: 50 Drip
  - [ ] Master Class Calibrator: 2 Grain

**Tests to Pass:**
- Create new tests: `test_hollow_degradation.py`, `test_attunement_mechanics.py`

**Verification:**
```bash
# Test degradation cycle
# - Buy Raw Seeds
# - Wait 7 rounds
# - Verify auto-conversion to Hollows
# - Verify Codex surveillance triggers (if 3+ Seeds)

# Test Hollow power
# - Use Hollows for attunement
# - Verify 3x energy yield
# - Verify Void increase
```

---

## 🐛 Known Bugs (Not Yet Fixed)

### Bug #2: `energy_inventory` vs. `energy_purse` Terminology
- **Status:** Not fixed
- **Location:** Codebase-wide
- **Impact:** Naming inconsistency, breaks immersion
- **Fix:** Rename all `energy_inventory` → `energy_purse`

### Bug #3: `starting_energy` Not Applied from Config
- **Status:** Not fixed
- **Location:** session.py character initialization
- **Impact:** Characters start with 0 energy instead of config values
- **Fix:** Parse `starting_energy` from session config, populate `energy_purse`

### Bug #4: Round Status Missing Energy Display
- **Status:** Not fixed
- **Location:** session.py round status output
- **Impact:** Players can't see their currency
- **Fix:** Add energy purse display to round status

---

## 🎯 Next Steps (Prioritized)

1. **Immediate (Today):**
   - [ ] Commit design document
   - [ ] Create this TODO document
   - [ ] Review Phase 1 tasks

2. **This Week:**
   - [ ] Implement Phase 1 (Bug Fixes)
   - [ ] Start Phase 2 (Pre-Validation)

3. **Next Week:**
   - [ ] Complete Phase 2
   - [ ] Start Phase 3 (Soulcredit Gating)

4. **Future (2-4 weeks):**
   - [ ] Phase 4 (Negotiation) - optional
   - [ ] Phase 5 (Hollow Seeds) - major feature

---

## 📊 ML Research Readiness

**Status:** Design complete, scenarios documented, ready for implementation

**Scenarios Ready:**
- ✅ Scenario A: Single-Agent Spark Maximization
- ✅ Scenario B: Multi-Agent Cooperative Optimization
- ✅ Scenario C: Adversarial Evasion (Agent vs. Codex)
- ✅ Scenario D: Strategy Transfer Across Factions
- ✅ Scenario E: Cooperative Resource Pooling

**Requirements for ML Research:**
- ⏳ Phase 2 complete (purchase system working)
- ⏳ Phase 5 complete (Hollow Seeds, degradation, Codex surveillance)
- ⏳ JSONL logging updated (track purchases, Codex alerts, SC changes)

**Estimated Timeline to ML-Ready:**
- Phases 1-2: ~1.5 weeks
- Phase 5: ~2 weeks
- **Total: 3.5-4 weeks to ML research-ready state**

---

## 📝 Notes

**Design Philosophy:**
- Energy as multi-use physical resource (not abstract currency)
- Transactions as spiritual acts (Codex logs everything)
- Scarcity creates drama (not RNG)
- Cooperative mechanics (purification, resource pooling)
- Adversarial surveillance (Codex vs. Tempest agents)

**Key Design Decisions:**
- Echo Calibrator is NOT default starting gear (must be purchased)
- Hollows = 3x power (deliberate temptation mechanic)
- Void 10 = possession, but RECOVERABLE via purification
- Void and Soulcredit are INDEPENDENT variables
- Pre-validation prevents DM hallucination on purchases

**Technical Debt to Address:**
- Rename `energy_inventory` → `energy_purse` (consistency)
- Decouple Soulcredit gating (reusable for location access, NPC attitudes, etc.)
- Add vendor state persistence (inventory depletion, restock mechanics)

---

## 🚀 Vision

**When Phases 1-5 are complete:**
- Players can buy/sell items with energy currency
- Hollows create risk/reward decisions (3x power vs. Void corruption)
- Soulcredit gates vendor access (social stratification)
- Codex surveillance creates adversarial gameplay (evasion strategies)
- Cooperative purification enables high-risk Hollow farming (party synergy)
- ML agents discover 8+ emergent strategies (from Conservative to Black Market Dealer)

**End Goal:**
> "Multi-agent reinforcement learning agents learning to optimize resource acquisition under multi-dimensional constraints (Void, Soulcredit, survival, cooperation) in a surveillance-constrained economy with temporal pressure and adversarial dynamics."

**Translation:**
> "Agents learning to play the best game I ever made, and generating PhD-quality training data as a side effect."

---

**Next Session:** Start Phase 1 (Bug Fixes)
