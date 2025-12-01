# OpenAI Session Configs

All session configs in this directory use **OpenAI GPT-5-mini** instead of Anthropic Claude models.

## Cost & Performance Benefits

**vs. Claude Sonnet 4.5:**
- **8x cheaper output tokens** ($2.00/M vs $15.00/M)
- **10x higher rate limits** (400 req/min vs 75 req/min)
- **Faster sessions** due to higher throughput

**Pricing (per 1M tokens):**
- Input: $0.25 (vs Claude $3.00)
- Output: $2.00 (vs Claude $15.00)

## Temperature Strategy

**IMPORTANT:** gpt-5-mini **REQUIRES** temperature=1.0. Other values will fail with an OpenAI API error.

All configs use **temperature 1.0** for all agents (DM and players).

## Available Scenarios

### ML Training Scenarios (14 configs)

Converted from `ml_training_scenarios/` directory:

1. **medic_rescue_mission_openai.json** - Healer archetype, Medicine 6, plague outbreak
2. **hacker_drone_heist_openai.json** - Tech specialist, Hacking 6, infiltration
3. **negotiation_standoff_openai.json** - Pure diplomat, Charm 6, zero-combat negotiation
4. **dissolution_advocate_openai.json** - Void specialist, Astral Arts 6, void mechanics
5. **murder_at_gestation_pod_openai.json** - Investigation mystery, clue gathering
6. **debt_spiral_desperation_openai.json** - Economic pressure, soulcredit crisis
7. **three_way_alliance_openai.json** - Faction politics, multi-party diplomacy
8. **bonded_blade_duel_openai.json** - Bonded weapons, honor duel mechanics
9. **crossing_the_veil_openai.json** - Void threshold crossing, reality breakdown
10. **both_sides_valid_openai.json** - Moral dilemma, no clear right answer
11. **countdown_to_breach_openai.json** - Time pressure, ticking clock urgency
12. **uncharted_moon_expedition_openai.json** - Exploration, discovery mechanics
13. **gathering_storm_openai.json** - Calm before storm, tension building
14. **seed_cartel_war_openai.json** - Seed economy, cartel warfare
15. **failed_ascension_ritual_openai.json** - Ritual consequences, void escalation 3→9

### Action Scenarios (1 config)

16. **session_config_action_movie_openai.json** - High-octane heist, explosive combat, 4-person crew

### Test Configs (11 configs)

17. **session_config_openai_test.json** - Basic OpenAI provider integration test
18. **session_config_attunement_test_openai.json** - Seed attunement system comprehensive test (NEW)
    - Tests altar bonuses, Echo-Calibrator mechanics, upkeep payment, all energy conversions
    - See `ATTUNEMENT_TEST_GUIDE.md` for detailed verification checklist
19. **session_config_purchase_test_openai.json** - Vendor purchase system test
20. **session_config_purchase_1round_test_openai.json** - Single-round purchase validation
21. **session_config_item_transfer_test_openai.json** - Item/currency transfer system test
22. **session_config_transfer_test_openai.json** - Transfer mechanics validation
23. **session_config_economic_openai.json** - Energy economy and currency operations
24. **session_config_ritual_progression_test_openai.json** - Void accumulation across rituals
25. **session_config_sc_gating_test_openai.json** - Soulcredit gating mechanics
26. **session_config_gymbar_social_openai.json** - Social mechanics and NPC interaction
27. **session_config_action_movie_openai.json** - High-octane action (also in Action Scenarios)

## Running OpenAI Sessions

**Prerequisites:**
```bash
export OPENAI_API_KEY="sk-..."
```

**Run a session:**
```bash
source .venv/bin/activate
python3 scripts/run_multiagent_session.py scripts/session_configs/openai/<config_name>.json
```

**Example:**
```bash
python3 scripts/run_multiagent_session.py scripts/session_configs/openai/medic_rescue_mission_openai.json
```

## Converting More Configs

Use the conversion script to create OpenAI versions of any Anthropic config:

```bash
python3 scripts/convert_to_openai.py \
  scripts/session_configs/ml_training_scenarios/<category>/<scenario>.json \
  scripts/session_configs/openai/<scenario>_openai.json
```

**What the script does:**
- Updates `_role`, `_purpose`, `session_name` with OpenAI metadata
- Converts all LLMs to `gpt-5-mini` at temperature 1.0 (required by model)
- Adds cost/performance notes to `_design_notes` and `notes` fields

## Provider Comparison

| Aspect | OpenAI GPT-5-mini | Claude Sonnet 4.5 |
|--------|-------------------|-------------------|
| **Output Quality** | High (competitive with Claude) | Excellent (gold standard) |
| **Output Cost** | $2.00/M tokens | $15.00/M tokens |
| **Rate Limit** | 400 req/min | 75 req/min |
| **Session Speed** | Fast (higher throughput) | Moderate (API throttling) |
| **Best For** | ML training data generation, batch runs, cost-sensitive workflows | Production games, quality-critical scenarios |

## Testing Notes

All scenarios are identical to their Anthropic counterparts except for LLM provider configuration. This enables:
- **Direct quality comparison** between OpenAI and Claude outputs
- **Cost analysis** for ML training data generation
- **Performance benchmarking** across providers

No changes to mechanics, characters, clocks, or scenario design - only LLM provider differs.

## Version History

- **2025-11-16**: Added comprehensive seed attunement test config with detailed guide
- **2025-11-15**: Created 16 OpenAI configs from ML training scenarios + action movie
- **2025-11-14**: Initial OpenAI test config
