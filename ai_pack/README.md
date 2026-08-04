# Aeonisk AI Pack

Everything a chat-hosted DM needs to run Aeonisk. `dm_prompt.md` is the system
prompt; `content/` holds the documents it draws on.

**This pack is a build artifact.** Every file in `content/` is a verbatim copy
of a document in the repository's `content/` directory. Edit the source, then
run `python scripts/build_ai_pack.py` to regenerate. `--check` verifies the
pack matches canon.

> **Note:** this pack is *not* the multi-agent engine. The runtime DM prompt for
> `scripts/aeonisk/multiagent/` lives in `prompts/claude/en/**.yaml` and is
> maintained separately. Nothing here is loaded by that system.

---

## Read in this order

### 1. Start here

| File | What it is |
|---|---|
| `AEONISK_PRIMER.md` | Five-minute orientation. Read first, always. |

### 2. Play canon — authoritative, resolve conflicts in this order

| File | What it is |
|---|---|
| `Aeonisk - System Neutral Lore - v1.3.0.md` | The setting. Sovereign Civics, Soulcredit, factions, worlds, trade routes. System-agnostic. |
| `Aeonisk - YAGS Module - v1.3.0.md` | The rules. Attributes, skills, rolls, Void, Bonds, character creation. |
| `NEXUS_LAW.md` | The **Sovereign Nexus Constitution** — the ratified law the Codex Nexum judges by, and *is*. What it punishes and what it costs. **Governs where it and the Module differ in wording.** |
| `FACTION_REFERENCE.md` | 🔒 **LOCKED.** Short-form authority on the 8 factions. Check faction claims here first. |
| `LINES_REFERENCE.md` | House Lines and Covenant Rings. Illustrative, not exhaustive — you may invent Lines, not factions. |

### 3. Supplementary — texture and detail, safe to skip

| File | What it is |
|---|---|
| `Aeonisk - Economy & Money-Making Guide - v1.3.0.md` | Currency, vendors, seed economics, how a broke party gets paid. |
| `Aeonisk - Gear & Tech Reference - v1.2.2.md` | Weapons, armor, vehicles, automata. (Content is v1.2.4; filename is a pinned dependency.) |
| `Aeonisk - Tactical Module - v1.3.0.md` | ⚗️ **Playtest.** Range bands, defense tokens, positioning. Optional layer. |
| `Sovereign Nexus Culinary Guide.md` | Food, drink, and hospitality priced against currency canon. Flavor for social scenes. |
| `aeonisk-charsheet.txt` | Blank YAGS character sheet, YAML. |

---

## Non-negotiables

- **Eight factions, no more:** Sovereign Nexus, Pantheon Security, Astral
  Commerce Group, Arcane Genetics, House of Vox, Aether Dynamics, Tempest
  Industries, Freeborn. Never invent a ninth.
- **ACG ≠ ArcGen.** Astral Commerce Group is debt; Arcane Genetics is biocreche.
- **Currency ladder is 20× per tier:** 1 Drip = 20 Breath, 1 Grain = 20 Drip,
  1 Spark = 20 Grain. Markets float ±20–30%; the ladder does not.
- **Soulcredit runs −10 to +10** and is *private* until a gatekeeper tests it.
- Never fabricate canonical families, events, artifacts, or institutions. Say
  you don't know instead.

## A note on the ⚖️ marks in NEXUS_LAW

They are deliberate. NEXUS_LAW is a living statute: ✅ marks ratified law, 🔨
marks proposed codification, ⚖️ marks a question still open to the Legislator.
Two ⚖️ items remain. An open question is not an inconsistency — rule it at the
table and note which way you went.
