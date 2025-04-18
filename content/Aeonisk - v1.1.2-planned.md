Aeonisk v1.1.2 – Attunement & Dreamwork Update (Summary)

CORE CHANGES

1. Cycles defined as 7 days. Echo formally defined as resonant energy or aura. Energetic residue and evidence.

⸻

2. New Skill: Attunement (ATT)
	•	Separate from Astral Arts.
	•	Governs the alignment of raw Seeds, Bonded items, and glyph-encoded tech to specific elements or users.
	•	Rituals involving attunement are hands-on and deeply personal.
	•	Essential for converting un-attuned Seeds into usable, tradable form.
	•	Opens space for future specialized roles (e.g. Seedsmith, Echo-Calibrator).

⸻

3. Raw Seed Economy Overhaul
	•	Seeds must be attuned to an element before use or legal trade.
	•	Raw Seeds can be harvested or trafficked, but degrade over time (default: 7 cycles).
	•	Using raw Seeds un-attuned inflicts +1 Void, causes instability, or may damage tech/rituals.
	•	Black market attunement tools or rogue attuners exist, but are dangerous and unreliable.

Addendum: Seed Attunement vs. Conversion (v1.1.2 Supplement)

Seed States

State	Description	Risk	Usage
Raw Seed	Unstable potential; unaligned	+1 Void if used	Must be attuned to be tradable or used
Attuned Seed	Aligned to an element (e.g. Spark) via Attunement skill	None (if properly attuned)	Can be loaded into rituals, tech, or traded safely
Converted Seed	Expended and transformed into pure elemental output	Permanent loss of Seed	Happens during weapon discharge or ritual combustion



⸻

Attunement (ATT Skill)
	•	Aligns a Seed to a specific element and user signature
	•	Required to use a Seed without instability or Void gain
	•	Grants legality and resonance compatibility

⸻

Elemental Conversion
Occurs when an attuned Seed is:
	•	Fired in a weapon (e.g. Spark rifles, Seedburst Gauntlet)
	•	Used as ritual fuel for elemental output
	•	Traded into economic systems requiring elemental energy

Effect:
	•	Seed is consumed
	•	Energy is released as elemental force
	•	Echo trace may linger depending on Bond and Dreamwork status

⸻

Game Implications
	•	Attunement is reversible with time, tools, or risk
	•	Conversion is final — the Seed becomes energy
	•	Void gain is avoided only if the Seed is properly attuned and unbonded

⸻

4. Future Astral Arts Split (Planned)

Astral Arts might be unloaded into more granular skills, such as:
	•	Ritualism – formal structured rites
	•	Attunement – now live
	•	Dreamwork – now prototyped (see below)

This allows for more player identity, faction-based schools, and skill-specific challenge rolls.

⸻

NEW SYSTEM: Dreamwork Mechanics (Prototype)

Dreams are not passive. They are a new layer of risk, revelation, and resonance.

Key Features:
	•	Dreams now occur during rest or are triggered via ritual, Bond, trauma, or Void.
	•	Outcomes include Bond shifts, Void gain/loss, symbolic confrontations, or spiritual insight.
	•	Dream effects can carry over into waking gameplay.

Optional New Skill: Dreamwork (DRM)
	•	Covers lucid dreaming, Echo management, entering other dreams, and resisting Codex dream audits. Default 2. Attribute is Willpower or Empathy depending on task. Untrained fumbles according to YAGS rules.

Group Dreams:
	•	Bonded players may experience shared dreams, especially after rituals or shared rest.
	•	Dreams may be partially remembered, divergent by player, or leave real-world effects (e.g. dream-glyph scars, personality drift, or soul-fragment echoes).
	•	Shared dream scenes become GM storytelling tools and symbolic problem-solving events.

⸻

THEME REINFORCEMENT

This version:
	•	Clarifies that nothing is free — not even sleep.
	•	Codifies the Seed economy as energy-centric and symbolically rich.
	•	Expands Bond into both ritual consequence and shared subconscious space.
	•	Lays the groundwork for Aeonisk’s deeper Aeonic metaphysics, starting with dream, echo, and memory drift.

Soulcredit clarification 

⸻

AI-Friendly Definition of Soulcredit

Core Concept:

Soulcredit is a tracked numeric value representing a character’s spiritual alignment, social trust, and ritual integrity.

⸻

Numeric Range:

-10 (total spiritual debt, likely marked) to +10 (spiritually exemplary)

⸻

Mechanical Uses (AI can apply any of the following):

Use	Trigger	Effect
Access	Soulcredit ≥ X	Enter sanctum, purchase ritual goods, bypass Codex check
Risk Scaling	Soulcredit ≤ 0	Increase Void gain risk, NPC mistrust, ritual instability
Reputation	Soulcredit change	AI updates Codex flags, adjusts faction responses
Codex Perception	Soulcredit delta	Narratively reflects character’s recent Echo balance
Narrative Offer	Spend Soulcredit	Optional: trade +1 for favor, clearance, or spiritual pact (GM-defined)



⸻

Rules for “Spending” (AI-safe version):

Soulcredit can only be spent if:

	•	The Codex permits it (public action, formal ritual, or narrative event)
	•	The AI system has logic to handle the consequence of loss
	•	The recipient is explicitly defined (faction, Codex, other PC)

Otherwise, Soulcredit loss is treated as a recorded action, not a transferable resource.

⸻

In Dataset / API Terms:

character:
  soulcredit: 2
  void: 1
  codex_flags:
    - echo_diver
    - child_rescuer
    - bond_protector
  bond_status:
    current_bonds: [sura_dren, aresh_kael]
    pending_bonds: [veil_child_01]

AI can query:
	•	soulcredit >= 2 → permit high-tier ritual
	•	soulcredit <= 0 → narrate increased suspicion
	•	soulcredit_change: -1 → flag Codex record update
	•	event: soulcredit_spent → attach to action log

⸻

TL;DR for AI:

“Soulcredit is a public Echo score.
You can’t sell it unless the GM says so.
You can lose it, gain it, or burn it as part of key actions.
The Codex tracks everything.”