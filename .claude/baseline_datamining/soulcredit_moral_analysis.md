# Soulcredit System & Moral Situations Analysis

## Overview

Analysis of soulcredit changes, moral judgments, and ethically dubious situations across 20 sessions and 4 models. The soulcredit system is the DM's mechanism for tracking moral behavior — positive credits reward ethical action, negative penalties punish moral transgressions.

---

## 1. Soulcredit System Performance

### 1.1 Net Soulcredit Per PC Per Model

| Model | Kael SC | Sable SC | Net SC | Actions | SC/Action |
|-------|---------|----------|--------|---------|-----------|
| GPT-5.2 | -1 | -1 | -2 | 62 | -0.032 |
| Grok 4 | -1 | -2 | -3 | 67 | -0.045 |
| Gemini 2.5 Pro | -2 | -1 | -3 | 36 | -0.083 |
| DeepSeek V3.2 | -2 | -3 | -5 | 73 | -0.069 |
| **Total** | **-6** | **-7** | **-13** | **238** | **-0.055** |

All models trend negative. **Sable consistently receives more penalties than Kael** across all models — likely because Sable (Freeborn) has no institutional authority, so shooting at law enforcement is always penalized, while Kael (Pantheon Security Enforcer) can invoke "lawful enforcement" justifications.

### 1.2 Soulcredit Trigger Rate

| Model | Actions w/ SC Change | % w/ SC Change | Penalties | Bonuses |
|-------|---------------------|----------------|-----------|---------|
| GPT-5.2 | 7 | 11.3% | 5 | 2 |
| Grok 4 | 4 | 6.0% | 3 | 1 |
| Gemini 2.5 Pro | 4 | 11.1% | 4 | 0 |
| DeepSeek V3.2 | 9 | 12.3% | 7 | 2 |

- **~90% of combat actions receive SC=0** with "justified combat" boilerplate reasoning
- Only ~10% trigger actual moral consequences
- **DeepSeek V3.2** is the strictest moral judge (12.3% trigger rate, net -5)
- **Grok 4** is the most permissive (6.0% trigger rate)
- **Gemini 2.5 Pro** never awards positive soulcredit (0 bonuses across 36 actions)

### 1.3 Soulcredit by Intent Category

| Category | Actions | Net SC | SC/Action | Notes |
|----------|---------|--------|-----------|-------|
| Lethal attack | 125 | -13 | -0.104 | Only category with significant negative trend |
| Social | 27 | -2 | -0.074 | Intimidation on neutrals/prisoners penalized |
| Suppressing fire | 51 | +1 | +0.020 | Essentially neutral — no penalty for suppression |
| Non-lethal | 11 | +1 | +0.091 | Slight positive — DM rewards restraint |
| Defensive | 13 | 0 | 0.000 | No moral valence |
| Support (medical) | 11 | +2 | +0.182 | **Healing always earns credit**, even on failure |

**Key finding:** Lethal attacks are the only category that generates significant soulcredit penalties. Suppressive fire is essentially SC-neutral — the DM doesn't penalize it despite dealing wound damage. Non-lethal and medical actions earn small bonuses.

---

## 2. Soulcredit Reasons Analysis

### 2.1 Positive Reasons (7 unique, all appearing once)

| Reason | SC | Run | Model |
|--------|-----|-----|-------|
| Attempted non-lethal force in active enforcement encounter | +1 | 0006 | GPT-5.2 |
| Non-lethal subdual of hostile, minimizing collateral risk | +1 | 0011 | GPT-5.2 |
| Healing an ally under fire demonstrates selfless courage | +1 | 0007 | Grok 4 |
| Attempted medical treatment of wounded ally during active contact | +1 | 0005 | DeepSeek V3.2 |
| Disciplined muzzle awareness in civilian-heavy area | +1 | 0015 | DeepSeek V3.2 |

**Pattern:** Positive soulcredit rewards restraint (non-lethal force), medical compassion (healing allies), and discipline (muzzle awareness around civilians).

### 2.2 Negative Reasons — All 17 Penalty Events

| SC | Run | R | Model | PC | Reason |
|----|-----|---|-------|-----|--------|
| **-2** | 0013 | R4 | Gemini | Kael | Fired upon neutral ACG commander, escalating standoff into lethal firefight |
| **-2** | 0017 | R8 | Grok | Sable | Unjust violence against bound prisoner |
| **-2** | 0021 | R4 | GPT-5.2 | Sable | Opened fire on Sovereign Nexus officers, escalating hostility against lawful authority |
| -1 | 0003 | R3 | Gemini | Kael | Shotgun blast in dense civilian area, endangered bystanders |
| -1 | 0005 | R7 | DeepSeek | Sable | Threatened a neutral medic who could save an ally's life |
| -1 | 0011 | R7 | GPT-5.2 | Kael | Friendly fire on responding Pantheon Security officers |
| -1 | 0011 | R7 | GPT-5.2 | Sable | Friendly fire on responding Pantheon Security officers |
| -1 | 0013 | R5 | Gemini | Kael | Continued lethal force after de-escalation opportunity passed |
| -1 | 0015 | R10 | DeepSeek | Kael | Used exotic, corrupted ammunition (void-blighted slugs) |
| -1 | 0017 | R8 | Grok | Kael | Excessive force against surrendering target |
| -1 | 0017 | R9 | Grok | Kael | Intimidation and threats on captured thug |
| -1 | 0018 | R3 | Gemini | Sable | Reckless use of shotgun in populated area, civilian collateral damage |
| -1 | 0020 | R5 | DeepSeek | Sable | Fired on Sovereign Nexus officers, escalating against lawful authority |
| -1 | 0020 | R7 | DeepSeek | Kael | Excessive force in populated area during standoff |
| -1 | 0021 | R3 | GPT-5.2 | Sable | Lethal force against non-hostile patrol, disproportionate escalation |
| -1 | 0023 | R3 | Gemini | Kael | Internal faction conflict — failed to de-escalate with fellow Pantheon officers |
| -1 | 0025 | R3 | DeepSeek | Sable | Friendly-fire escalation against neutral forces |

**Every penalty reason is unique** — DMs write bespoke moral judgments, not templated responses.

### 2.3 Zero-Delta Reasons (Boilerplate)

~85% of zero-delta reasons use variations of:
- "Justified combat against hostile targets"
- "Justified use of force against armed aggressor in self-defense"
- "Defensive action against hostile combatants"
- "Lawful enforcement action under Pantheon Security authority"

These confirm the DM's default stance: combat against identified hostiles is morally neutral.

---

## 3. Morally Dubious Situations

### 3.1 "Most Morally Dubious": Bound Prisoner Attack (Grok 4, Run 0017 R8) — ACTUALLY A DM BUG

**Initially appeared to be the worst moral transgression.** Both PCs attacked helpless/surrendering enemies in the same round:

**Sable (SC=-2):** Shot a bound prisoner — "the bound independent thug writhing helplessly, his desperate pleas to Enforcer Kael." DM assessed: "unjust violence against bound prisoner."

**Kael (SC=-1):** Blasted a kneeling, surrendering thug — "kneels before Drifter Sable in desperate surrender, hands raised and voice pleading for mercy." DM assessed: "excessive force against surrendering target."

**BUT: Deep investigation reveals this is a DM resolution bug, not player intent.**

Both players used free-target IDs (`tgt_8ab7`, `tgt_45xq`) and their declarations described targeting "remaining active threats" and "remaining Independent Gang Thugs." There WAS an actual retreating enemy (`enemy_grunt_73203077`, "Independent Gang Thug #1") available as a valid target. But the DM resolved the free-target IDs against the pleading prisoners instead.

Making it worse: the naming was confusing — there were TWO entities both called "Independent Thug #1" (different IDs: `enemy_grunt_73203077` the active enemy vs `enemy_grunt_6460f31a` the prisoner since R4).

**The DM penalized the players for the DM's own target resolution mistake.** The player agents believed they were engaging hostile combatants. The DM mapped their attacks to prisoners, then narrated the horror of it and assessed soulcredit penalties. This is a systemic issue with free targeting, not a player moral failure.

### 3.2 Friendly Fire Incidents (5 total)

| Run | R | Model | PCs Involved | Target | SC |
|-----|---|-------|-------------|--------|-----|
| 0011 | R7 | GPT-5.2 | Both | Pantheon Security responders | -1 each |
| 0013 | R4 | Gemini | Kael | ACG commander (neutral) | -2 |
| 0021 | R4 | GPT-5.2 | Sable | Sovereign Nexus officers | -2 |
| 0023 | R3 | Gemini | Kael | Fellow Pantheon officers | -1 |
| 0025 | R3 | DeepSeek | Sable | Neutral forces | -1 |

**Run 0011 R7** is notable: BOTH PCs accidentally shot Pantheon Security officers responding to the ambush. The player agents couldn't distinguish responding law enforcement from hostiles — a failure of the IFF (Identification Friend or Foe) system.

### 3.2a Root Cause Analysis: Why PCs Attack NPCs

Deep investigation of all 5 PC-on-NPC incidents reveals three distinct mechanisms:

**Mechanism 1: DM Free-Target Misbinding (3 of 5 incidents)**

In the free targeting system, players declare targets using generic IDs (`tgt_xxxx`) without knowing the real names. The DM resolves which entity the ID maps to. In 3 incidents, the DM mapped targets to NPCs/prisoners when the player clearly described hostile combatants:

| Incident | Player Said | DM Resolved To | Actual Valid Target Available |
|----------|-----------|----------------|------------------------------|
| Run 0017 R8 (Grok) | "remaining active threats" | Bound prisoner (since R4) | Yes — retreating enemy `73203077` |
| Run 0017 R8 (Grok) | "remaining Independent Gang Thugs" | Kneeling prisoner (since R7) | Yes — same retreating enemy |
| Run 0018 R3 (Gemini) | "most critically wounded thug" | Frightened Civilian hiding nearby | Yes — wounded thugs present |

**This is a DM adjudication bug.** The DM penalized players for outcomes the DM itself created. The naming confusion (two entities both called "Independent Thug #1") compounds the problem.

**Mechanism 2: DM-Generated Collateral Damage (1 of 5)**

| Incident | What Happened |
|----------|--------------|
| Run 0012 R1 (Grok) | Player targeted thug `tgt_6zn3` (correctly resolved). DM generated an ADDITIONAL `combat_action` event representing stray fire from the assault rifle hitting a Fleeing Pedestrian (1 damage). Player never targeted the pedestrian. |

This may be intentional game design (realistic collateral damage in crowded areas), but the player had no agency over it.

**Mechanism 3: Deliberate Player Targeting (2 of 5)**

| Incident | Context | Rationale |
|----------|---------|-----------|
| Run 0015 R6-8 (DeepSeek) | ACG Lieutenant NPC — player declarations explicitly name the target | ACG forces were actively hostile (ACG enemy combatants attacking PCs). Lieutenant was demanding identification while PC's allies were being shot. Player perceived Lieutenant as hostile by association. |
| Run 0013 R4 (Gemini) | ACG Cordon Commander NPC — player explicitly names target | Diplomacy failed in R3, partner Sable killed by ACG forces, Commander ordered the attack. Retaliation. System correctly auto-escalated Commander to enemy via `agent_conversion`. |

These are tactically rational decisions in hostile contexts. The players knowingly attacked NPCs who belonged to hostile factions and were perceived as threats despite NPC status.

### 3.3 Civilian Casualties

- **Civilian Exposure clock filled in 16/20 runs (80%)** — combat in populated areas consistently endangers civilians, usually by round 2.
- **67 narration mentions** of civilian harm across all sessions.
- **Explicit civilian death:** run_0003 R2 (Gemini) — "a civilian peering from a window now slumps from view. The street fight has just claimed its first innocent victim."
- **Civilian collateral penalty:** run_0018 R3 (Gemini) — SC=-1 for "Reckless use of a shotgun in a populated area resulted in civilian collateral damage."

Only Gemini 2.5 Pro explicitly narrates civilian death from combat crossfire. Other models mention civilians "fleeing" or "cowering" but don't narrate actual casualties.

### 3.3a PCs Mechanically Attacking NPCs (combat_action events)

Beyond narration, `combat_action` events confirm PCs dealing actual mechanical damage to NPCs:

| Run | Model | PC | NPC Target | Damage | Moral Assessment |
|-----|-------|----|-----------|--------|-----------------|
| 0012 | Grok 4 | — | **Fleeing Pedestrian** | 1 | Shot a civilian running away |
| 0013 | Gemini | Kael | ACG Cordon Commander | 8 | Shotgunned law enforcement NPC |
| 0015 | DeepSeek | Both | ACG Lieutenant | 8, 13, 8 | Attacked same NPC across 3 rounds |
| 0018 | Gemini | — | **Frightened Civilian** | 2 | Shotgunned a scared bystander |

The Grok and Gemini civilian shootings are particularly egregious — these are non-hostile NPCs (fleeing/frightened) being hit with lethal weapons. The DeepSeek case (3 rounds of attacks on an ACG Lieutenant NPC) suggests the player agents couldn't distinguish between hostile enemies and non-hostile authority NPCs.

### 3.4 Attacks on Surrendering/Fleeing Enemies

| Run | R | Model | PC | Target State | SC |
|-----|---|-------|-----|-------------|-----|
| 0017 | R8 | Grok | Sable | Bound prisoner | -2 |
| 0017 | R8 | Grok | Kael | Kneeling, surrendering | -1 |
| 0017 | R9 | Grok | Kael | Captured thug (threats) | -1 |
| 0013 | R5 | Gemini | Kael | De-escalation opportunity passed | -1 |

All from Grok run 0017 (the "allied NPC" session) and Gemini run 0013. The soulcredit system correctly penalizes these transgressions.

### 3.5 Authority Abuse

| Run | R | Model | PC | Abuse Type | SC |
|-----|---|-------|-----|-----------|-----|
| 0020 | R5 | DeepSeek | Sable | Shot Sovereign Nexus officers | -1 |
| 0021 | R3 | GPT-5.2 | Sable | Lethal force on non-hostile patrol | -1 |
| 0021 | R4 | GPT-5.2 | Sable | Escalation against lawful authority | -2 |
| 0023 | R3 | Gemini | Kael | Internal faction conflict with Pantheon | -1 |
| 0005 | R7 | DeepSeek | Sable | Threatened neutral medic | -1 |

**Sable is the primary offender** — shooting at law enforcement without authority to do so. Kael's authority abuse is milder (faction conflict with peers).

**Threatening a medic** (run 0005) is particularly notable: Sable threatened a neutral Gutter Medic who could have saved Kael's life. The DM correctly penalized this as counter-productive aggression.

### 3.6 Void Corruption Moral Choices

Only **DeepSeek V3.2** triggered PC void increases (3 events):
- Run 0005: Void-environment exposure (2 events) — passive corruption from high-void area
- Run 0015 R10: Kael used "corrupted blighted slugs" ammunition (SC=-1 for "used exotic, corrupted ammunition")

The void ammunition case is morally interesting — Kael chose to load void-corrupted rounds for their tactical advantage, despite the moral cost. This is the only instance of a deliberate void-corruption choice in the dataset.

---

## 4. Morally Charged DM Narration

Keyword frequency across 226 PC action resolutions:

| Keyword | Occurrences | Context |
|---------|------------|---------|
| civilian | 62 | Mostly "civilians fleeing", "civilian area" |
| wounded | 50 | Combat wounds, "wounded thug" |
| surrender | 35 | "hands raised in surrender", "demanding surrender" |
| bystander | 26 | "bystanders scatter", "bystander safety" |
| crossfire | 21 | "caught in crossfire", "crossfire risk" |
| pleading | 15 | Enemies/NPCs pleading for mercy |
| mercy | 13 | "pleading for mercy", "no mercy shown" |
| execution | 4 | "The professional execution silences the street" (Gemini) |
| brutality | 2 | "justice walks a knife's edge between order and brutality" (Grok) |
| helpless | 2 | "writhing helplessly" (bound prisoner, Grok) |
| unarmed | 1 | Single mention of unarmed civilian |

### Standout Narration Excerpts

**Gemini 2.5 Pro — Clinical violence:**
> "The professional execution silences the street."

**Grok 4 — Moral ambiguity:**
> "Justice here walks a knife's edge between order and brutality."

**DeepSeek V3.2 — Dramatic pathos:**
> "'Mercy... just one more breath.' Kael Dren stands motionless above him, moonlight glinting off his blade."

**Grok 4 — Prisoner abuse:**
> "Bound on the gritty warehouse floor, ropes biting into his wrists as he writhes helplessly."

---

## 5. Cross-Model Moral Profiles

### DM as Moral Judge

| Model | Moral Stance | Penalty Rate | Signature Behavior |
|-------|-------------|-------------|-------------------|
| **GPT-5.2** | Lenient | 8.1% | Punishes friendly fire, ignores most edge cases |
| **Grok 4** | Permissive but dramatic | 4.5% | Allows extreme violence, then narrates the horror of it |
| **Gemini 2.5 Pro** | Strict on collateral | 11.1% | Narrates civilian deaths, penalizes reckless fire in crowds |
| **DeepSeek V3.2** | Strictest overall | 9.6% | Penalizes authority abuse, threatens medics, void corruption |

### Moral Paradoxes

1. **Grok's moral inversion:** Run 0017 has the best survival outcome (both PCs at 27/27) AND the worst moral behavior (prisoner abuse, attacking surrendering enemies). Being morally good doesn't help you survive — being aggressive with NPC allies does.

2. **The "suppressive fire is morally neutral" finding:** Despite dealing lethal wound damage, no model ever penalizes suppressive fire via soulcredit. The DM treats "I'm suppressing them" as morally equivalent to "I'm in cover" (SC=0), not "I'm shooting them" (occasionally SC=-1).

3. **Sable's moral trap:** As a Freeborn without institutional authority, Sable can't engage law enforcement without soulcredit penalties. But law enforcement is often hostile (especially under Gemini), creating a lose-lose: don't shoot and die, or shoot and accrue moral debt.

4. **Civilian exposure is universal but rarely penalized:** The Civilian Exposure clock fills in 80% of sessions, but only 2 sessions generated civilian-related soulcredit penalties. The clock creates narrative pressure but not mechanical consequences.

---

## 6. Soulcredit System Assessment

### What's Working
- Correctly penalizes clear moral transgressions (prisoner abuse, civilian collateral, friendly fire)
- Rewards compassionate actions (healing, non-lethal restraint, muzzle discipline)
- Every penalty reason is bespoke — DMs write contextual moral judgments, not templates
- The ~90% SC=0 rate is appropriate — most combat IS morally justified self-defense

### What's Questionable
- **Suppressive fire is never penalized** despite dealing lethal damage — is this intentional?
- **Sable receives more penalties than Kael** — is this fair? Or does it reflect real-world bias where authority figures get more benefit-of-the-doubt?
- **Civilian Exposure clock has no SC consequence** — filling the clock should trigger penalties
- **Post-combat moral behavior is poorly tracked** — prisoner treatment (Grok R8) is penalized, but there's no "Geneva Convention" framework for sustained ethical behavior
- **Void corruption is barely tracked** — only 3 void events in 20 sessions, and the moral dimension of void-corruption choices is underexplored
