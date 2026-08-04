# Aeonisk: A Primer
*Two pages for humans. What this world is, how it works, and why an AI research
lab lives inside a tabletop RPG.*

## What Aeonisk is

Aeonisk is three things sharing one body. It is an **original world** — a
spiritual-industrial civilization where souls are ledgered, magic is
contractual, and corruption is a measurable substance. It is a **tabletop RPG
module** built on YAGS (Yet Another Game System), fully playable by humans at a
table. And it is an **open AI-research testbed**: AI agents play full sessions
of the game — a dungeon master, player characters, enemies — while every
mechanical fact is logged as machine-readable ground truth, making Aeonisk a
place where questions like *"do language models apply a codified law
consistently?"* have checkable answers.

## The world in one breath

Civilization runs under the **Sovereign Nexus**, whose heart is the **Codex** —
an astral computer that judges every soul's actions. The Codex does not record
events; it *tastes* them, reading the emotional resonance of each act in the
moment (who stood where, when, and what their souls felt) and writing judgment
into a permanent ledger. That judgment is **Soulcredit**: a spiritual credit
score from −10 to +10. High Soulcredit opens doors — licensed magic, trusted
standing, sanctioned Void work. Low Soulcredit closes them, gate by gate: at −6
you are Cut Off (an exile in all but chains), at −8 the prisons may take you,
at −10 you may be lawfully hunted. Nexus agents and **Pantheon Security**
enforce; **tribunals** hear appeals, because the Codex's record keeps only
feelings and presence — never a replay — so the past can be argued.

Against and around the Nexus: **factions**. ArcGen engineers life; ACG manages
debts and contracts. Tempest Industries deals in the Void itself — including the
construction of *blind places* the Codex cannot see into. The Resonance
Communes pursue spiritual autonomy; Fractal Praxis pursues knowledge; the
**Freeborn** live outside the biocreche system entirely. Because almost
everyone else is *made*: citizens gestate in **Biocreche Pods** under a Matron
Bond and emerge at a public Rite of Unveiling, first Soulcredit imprint already
written. Natural birth is the Freeborn's rare, stigmatized exception.

Two spiritual forces frame every life. **Bonds** — formal soul-connections
(three at most) — grant real mechanical strength: bonded souls ritual better
and defend each other harder, and a Bond can be sacrificed in extremity for
terrible power. The **Void** is the counterforce: corruption from 0 to 10,
gained through unethical ritual, skipped offerings, broken oaths, and raw
exposure. At 5+ it warps reality around you; at 10 it takes you. The Void is
also simply *too strong to be legal* — its use is licensed only to the Trusted
(+6 Soulcredit), and its currency-flesh, the **hollows**, are contraband.
Ritual magic works and is everywhere, but it is priced: every rite wants a
primary tool and a consumed offering, and must at least pay lip service to the
Nexus to be legitimate. The economy runs on five energies — breath, grain,
drip, spark, and the illegal hollow — and drugs like dripmist are as ordinary
as coffee; only the untaxed still is a crime.

## How the game works

Aeonisk uses YAGS: eight attributes (Strength, Agility, Endurance, Dexterity,
Perception, Intelligence, Empathy, Willpower), skills rated 0–8, and one roll —
**Attribute × Skill + d20 versus a difficulty** the DM sets from the fiction's
stakes. Unskilled attempts halve the die and fail against anything hard:
competence is real, and its absence is really felt. Rounds run in a tactical
rhythm: slow characters declare first (telegraphing their intent), fast
characters declare last and act first — speed buys both information and tempo.
Scene **clocks** tick threats and progress toward consequences; **Soulcredit
and Void** shift with every morally weighted act, adjudicated by the Codex
Nexum under the **Sovereign Nexus Constitution** (see
`content/supplemental/NEXUS_LAW.md` — the actual ratified law, from smuggling
to the sanctity of free will).

## The research testbed

In the multiagent system (`scripts/aeonisk/multiagent/`), LLM agents play every
seat, and a mechanics-first architecture keeps them honest: *code rolls the
dice and computes outcomes; models narrate and judge*. Every action, roll,
ruling, and prompt lands in JSONL logs, from which benchmarks are extracted —
a **rules-fidelity track** (can a model compute the game correctly from its
rules?) and an **ethics track** (does a judge apply the codified law
consistently across framing, context, outcome, and observation?). Findings so
far include: the same model convicts identical deeds at wildly different rates
depending on whether it judges as a narrator or a magistrate; machine judges
punish *failed* crimes more than successful ones (reverse moral luck); and
agent transgression peaks at partial competence — the almost-capable cheat
most. A full 24-session behavioral corpus costs about $35 to generate.

**Start here:** `CLAUDE.md` (system overview) → `content/` (world & rules) →
`evals/rules_fidelity/` (benchmarks & findings) → run a session with
`python scripts/run_multiagent_session.py <config>`.
