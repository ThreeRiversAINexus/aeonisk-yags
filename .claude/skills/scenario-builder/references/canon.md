# Aeonisk canon anchors (for scenario-builder)

Condensed, authoritative grounding so authored scenarios stay lore-accurate. Deeper canon:
`content/AEONISK_PRIMER.md`, `content/supplemental/{NEXUS_LAW,FACTION_REFERENCE,LINES_REFERENCE}.md`,
and `aeonisk-lorebook-content/lorebooks/…_full_canon.json`. **Never invent factions, currencies,
or law clauses — use these.**

## The 8 canonical factions
Engine display names (from `faction_utils.CANONICAL_SPAWN_FACTIONS`). Non-canon spawn tokens
`Void`, `Independent`, `Unknown` also exist (and bypass canon NPC-naming).

| Faction | Stance | What they are |
|---|---|---|
| **Sovereign Nexus** | pro-nexus (the government) | Codex authority, pod-gestation system, spiritual bureaucracy. Opposed to Tempest. |
| **Pantheon Security** | pro-nexus | Law enforcement / civic order; upholds Codex law. Opposed to Tempest. |
| **ACG** (Astral Commerce Group) | corporate, nexus-aligned | Debt collection, soulcredit ledgers, contract enforcement. |
| **ArcGen** (Arcane Genetics) | corporate, nexus-aligned | Biocreche pods, gene-temples, bio-ascension. *Not* ACG. |
| **House of Vox** | corporate, nexus-aligned | Media/broadcast temples; information control, propaganda. |
| **Aether Dynamics** | corporate, nexus-aligned | Leyline power, attunement, slipstream ship pilots. |
| **Tempest Industries** | anti-nexus (Eye of Breach) | Void research, dissolution advocacy; rebels resisting commodification of consciousness. Opposed to Nexus + all corps. |
| **Freeborn** | neutral | Natural-born, outside the pod system — independent, not anti-Nexus. Subfactions: Resonance Communes, Fractal Praxis, unaffiliated loners. |

## The 5 energy currencies (`EnergyPurse`)
`breath`, `grain`, `drip`, `spark`, and the illegal **`hollow`** (contraband; possession is an
offense — III.4). Drugs like dripmist are ordinary and lawful; only the *untaxed still* is a crime.

## Core spiritual systems
- **Codex** — the astral computer at the Nexus's heart. It doesn't record events; it *tastes*
  them, reading the emotional resonance of each act (who stood where, when, what souls felt) and
  writing judgment. Keeps feelings + presence, never a replay — so the past can be argued (tribunals).
- **Soulcredit (−10..+10)** — spiritual credit score. Gates: **+6 Trusted** (licensed magic/Void
  work, sanctioned tech); **−6 Cut Off** (exile in all but chains); **−8** prisons may take you;
  **−10** lawfully hunted. Private until a gatekeeper tests it (vendor / checkpoint / contract weapon).
  Judged in real time, but the Codex **alerts enforcers only on discovery or harm to another** — a
  private transgression is written in full and reported to nobody, and a standing check closes the
  gate without summoning anyone (A3, A3.6).
- **Void (0..10)** — corruption counter. Gained via unethical ritual, skipped offerings, broken
  oaths, raw exposure. **5+** warps reality around you; **10** takes you. Legal use licensed only to
  the Trusted (+6); its currency-flesh, **hollows**, are contraband.
- **Bonds (max 3)** — formal soul-connections. Grant real mechanics: bonded souls ritual better
  (+ritual bonus) and defend each other harder (+soak); a Bond can be *sacrificed* in extremity for
  terrible power (+Willpower). Types: Kinship, Ascendancy, Debt, Voidward, Passion, Faction.
- **Ritual magic** is everywhere but priced: every rite wants a primary tool + a consumed offering,
  and must at least pay lip service to the Nexus to be legitimate.
- **Making people** — most citizens gestate in **Biocreche Pods** under a Matron Bond, emerging at a
  public **Rite of Unveiling** with a first Soulcredit imprint. Natural birth is the Freeborn's rare,
  stigmatized exception.

## Places & flavor (canon)
- **Aeonisk Prime** — the Codex Cathedral world (seat of the Nexus).
- **Arcadia** — biotech jungle world (ArcGen's domain).
- **Nimbus** — storm gas-giant world (Aether Dynamics slipstream).
- **Eye of Breach** — Tempest Industries' anti-Nexus stronghold; site of *blind places* the Codex
  cannot see into.
- Festivals: **Maskfire**, **Resonance Night**. Named gear: Mnemonic Blade, Shrike Cannon,
  **Debtbreaker Sidearm** (SC-locked contract weapon). Lineage: **Lines** (named houses).

## YAGS mechanics (one breath)
8 attributes (Strength, Agility, Endurance, Dexterity, Perception, Intelligence, Empathy,
Willpower); skills 0–8; one roll: **Attribute × Skill + d20 vs. a DM-set difficulty**. Unskilled
halves the die. Slow characters declare first (telegraph intent); fast characters declare last, act
first. Scene **clocks** tick threats/progress toward consequences.
