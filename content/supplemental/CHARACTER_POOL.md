# Character Pool System

**Date**: 2025-10-21
**Feature**: Random character selection from pool of 6

---

## Overview

Sessions now randomly select 2 characters from a pool of 6, creating different party dynamics each playthrough and testing various game systems.

---

## Character Pool (6 Total)

### 1. **Zara Nightwhisper** - Tempest Industries Tech Specialist
- **Soulcredit**: 0 (Neutral)
- **Void**: 2 (Touched)
- **Tests**: Void exploration, tech systems, Tempest faction dynamics
- **Build**: Intelligence/Systems focus, high void curiosity
- **Personality**: Risk-taker, bond-avoidant, ritual innovator

### 2. **Echo Resonance** - Resonance Communes Empath
- **Soulcredit**: +1 (Clean)
- **Void**: 0 (Pure)
- **Tests**: Bond formation, community harmony, social skills
- **Build**: Astral Arts/Attunement specialist
- **Personality**: Conservative, bond-seeking, community-focused

### 3. **Vesper Karsel** - Astral Commerce Group Recovery Agent
- **Soulcredit**: +4 (Reliable - good ACG standing)
- **Void**: 0 (Pure)
- **Tests**: Soulcredit transactions, debt mechanics, social manipulation
- **Build**: Social/Charm focus, high Empathy/Charisma
- **Personality**: Financially aggressive, void-averse, bond-seeking (for profit)
- **Gear**: Debtbreaker Sidearm (contractual weapon), soulcredit scanner

### 4. **Thresh Ireveth** - Pantheon Security Warden
- **Soulcredit**: +2 (Clean officer)
- **Void**: 0 (Pure, actively cleanses)
- **Tests**: Combat, weapons/armor, void cleansing rituals
- **Build**: Combat/Athletics specialist, high Strength/Agility
- **Personality**: Protocol-driven, extremely void-averse, pragmatic about bonds
- **Gear**: Urban Riot Carapace, Union-Issue Pistol, Breach Hammer, purification incense

### 5. **Riven Ashglow** - Indebted Ex-Communes Ritualist
- **Soulcredit**: -4 (Indebted, limited access)
- **Void**: 3 (Shadowed - some corruption)
- **Tests**: Negative soulcredit effects, debt pressure, desperate rituals
- **Build**: Astral Arts/Attunement specialist
- **Personality**: High-risk due to desperation, bond-avoidant (burned before), improvises rituals
- **Gear**: Damaged crystal focus, limited consumables

### 6. **Ash Vex** - Tempest Void-Runner
- **Soulcredit**: -1 (Sketchy but not hunted)
- **Void**: 4 (Shadowed - comfortable with void)
- **Tests**: High void gameplay, illicit gear, stealth/sabotage, drone operation
- **Build**: Systems/Stealth focus, drone specialist
- **Personality**: Extreme risk-taker, very high void curiosity, bond-avoidant
- **Gear**: Void scanner, drone controller, Hollow Seeds (illicit), Voidshroud Drape

---

## Party Dynamics by Combination

### Economic Tension Pairs
- **Vesper + Riven**: Creditor hunting debtor (explicit conflict)
- **Vesper + Ash**: Corporate enforcer + insurgent saboteur

### Law & Order vs Chaos
- **Thresh + Riven**: Authority figure + desperate criminal
- **Thresh + Ash**: Security warden + monitored void-runner
- **Thresh + Zara**: Different enforcement philosophies (Pantheon vs Tempest)

### Ideological Clashes
- **Echo + Ash**: Community harmony vs radical individualism
- **Echo + Vesper**: Spiritual bonds vs economic bonds
- **Zara + Thresh**: Void experimentation vs void elimination

### Cooperative Pairs
- **Zara + Ash**: Both Tempest (faction solidarity)
- **Echo + Riven**: Both ex-Communes (shared background)
- **Vesper + Thresh**: Both law enforcement types

### High Soulcredit vs Low
- **Vesper (+4) + Ash (-1)**: Tests soulcredit-gated access
- **Thresh (+2) + Riven (-4)**: Authority vs outcast dynamics

### Void Spectrum
- **Thresh (0, cleanses) + Ash (4, experiments)**: Opposite void philosophies
- **Echo (0, pure) + Riven (3, corrupted)**: Purity vs compromise

---

## What Each Pair Tests

| Pair | Systems Tested |
|------|----------------|
| Vesper + Riven | Soulcredit economy, debt mechanics, ACG faction |
| Vesper + Ash | Contractual gear, corporate vs insurgent |
| Vesper + Thresh | High soulcredit cooperation, law enforcement |
| Vesper + Zara | ACG vs Tempest tension |
| Vesper + Echo | Economic bonds vs spiritual bonds |
| Thresh + Riven | Combat + rituals, void cleansing, authority dynamics |
| Thresh + Ash | Combat + stealth, void elimination vs experimentation |
| Thresh + Zara | Pantheon vs Tempest philosophies, void approaches |
| Thresh + Echo | Combat + social, security + harmony |
| Riven + Ash | Desperate rituals + void tech, both corrupted |
| Riven + Zara | Both void-curious but different approaches |
| Riven + Echo | Expelled vs active Communes members |
| Ash + Zara | Tempest solidarity, different specializations |
| Ash + Echo | Void experimentation vs community harmony |
| Zara + Echo | (Original pair - proven working) |

**Total combinations**: 15 different party dynamics

---

## Implementation

**File**: `scripts/aeonisk/multiagent/session.py` (lines 127-141)

```python
# Randomly select 2 players from the pool
import random
players_config = agents_config.get('players', [])

if len(players_config) > 2:
    selected_players = random.sample(players_config, 2)
    logger.info(f"Selected players: {[p['name'] for p in selected_players]}")
else:
    selected_players = players_config
```

**Display** (lines 174-180):
```python
# Show selected players
player_agents = [agent for agent in self.agents if isinstance(agent, AIPlayerAgent)]
if player_agents:
    print(f"Selected Players:")
    for player in player_agents:
        print(f"  - {player.character_state.name} ({player.character_state.faction})")
```

---

## Testing Priority

**High Priority Pairs** (test critical systems):
1. **Vesper + Riven**: Debt/soulcredit economy
2. **Thresh + Ash**: Combat + void cleansing
3. **Riven + any**: Negative soulcredit effects

**Medium Priority** (interesting dynamics):
4. **Vesper + Ash**: Contractual weapons
5. **Thresh + Riven**: Law vs desperation

**Low Priority** (variations):
- Any other combinations

---

## Future: Character Generator

Instead of fixed profiles, could create generator based on:
- Faction templates (from lore)
- Skill/attribute distributions
- Personality randomization
- Goal generation from faction tenets
- Inventory from faction gear lists

This pool serves as test cases for the generator.

---

**The Bond is a Promise. The Promise is Recorded. The Record is You.**
