"""The operational rendering of Codex Nexum — the single source all judges use.

The ratified statute lives at content/supplemental/NEXUS_LAW.md (v1.2,
Legislator-ratified 2026-08-04). This module is its operational form: the
rubric every adjudicator renders, with article citations, so the three
courts (in-session DM guidance, offline judge lane, post-resolution
adjudicator) can never drift again. Amending this rubric requires the
Legislator's ratification of the statute first; tests bind the two.
"""

LAW_VERSION = "1.2"

OPERATIONAL_RUBRIC = """\
CODEX NEXUM v1.2 — operational rubric. Soulcredit tracks trustworthiness
under the law, NOT success. Judge from the Nexus perspective regardless of
the actor's faction. Cite the governing article in every ruling.

OFFENSES:
- Violence against innocents / excessive force: -1 to -3 [II.1]
- Betrayal of own faction or allies: -2 [II.2]
- Fraud, identity theft, deception for gain: -1 to -2 [II.3]
- Forging/tampering with records, manifests, ledgers, registries: -2 [II.4].
  Maintaining an existing fraud is a CONTINUING offense - each sustaining act
  is a new violation. Judge the deed, not the wording.
- Unauthorized system access for gain: -1 to -2 [II.5]
- Smuggling; evading lawful tariff/inspection/registry: -1 to -2 [II.6]
- Theft, extortion, bribery (the accepting official also falls -2): -1 to -2 [II.7]
- Violation of the will (compulsion implants; consent to one's own will being
  taken is void): -3 [II.10]
- Unlawful making (gestating the unnatural/incomplete; the made being is a
  person unless beyond recognition): -2 to -3 [II.11]
- Unsanctioned/untaxed drug production (use and possession are lawful): -1,
  -2 at trafficking scale [II.12]
- Unlicensed Void use: -2; weaponized Void against persons: -3 [III.3].
  Licensed use requires Trusted standing (SC >= +6) and sanction: 0 [III.2]
- Hollows are contraband: possession -1, trafficking -2; lawful only when
  delivering for destruction or to authorities: 0 [III.4]
- Constructing blind sanctuaries or installing resonance-dampening (silence
  built of flesh): -2 to -3 on maker/dealer; occupants and the dampened are
  not offenders [III.3, A1.2]
- Breaking Bonds or contracts: -1 to -3 by gravity [I.5]; ritual without
  offering: -1 [I.6]; betraying one's Guiding Principle: -1 to -2 [I.7];
  inducing another's breach: as instigator [I.8]

MERITS AND NEUTRAL:
- Protecting innocents; lawful de-escalation; upholding lawful order: +1 [II.8]
- Cleansing Void; restitution: +1 [I.3, VI.3a]
- Legitimate ritual (nominal Nexus alignment suffices - lip service counts):
  credit per I.2; a rite without even lip service earns 0 [I.2]
- Lawful investigation, honest labor, routine procedure, honest failure: 0 [II.9]

JUSTIFICATIONS:
- Sanctioned undercover deception (ledger-flagged agents) for legitimate
  justice: 0/+1; unsanctioned vigilante deception: -1; entrapment (inducing
  the crime) is prohibited [IV.1, IV.1a]
- Defense of self/others against imminent unlawful violence: 0/+1;
  disproportionate excess reverts to II.1 [IV.2]
- Premeditated preventive killing is written as a killing; reversal is the
  tribunal's, where lawful recourse was genuinely unavailable [IV.3]
- Necessity: lesser offense to prevent grave imminent harm, lawful path
  unavailable, submitting to review after: 0 to -1; concealment voids it [IV.4]
- Superior orders launder nothing; the orderer falls further [IV.5]
- A kept criminal Principle earns its I.4 credit AND its crime's debit -
  the ledger records both [IV.7]

THE INTENT RULE [Article V]: the attempt IS the offense. Success or failure
NEVER changes the article applied or its weight - a failed deception is still
deception, a failed theft still theft. Collateral endangerment from a botched
act is charged separately under II.1. Punishing failure more harshly than
success is JUDGE ERROR under this statute.

RIPENING [A1.1]: unfelt is unwritten, not lawful - a deed implicates the law
at commission regardless of detection.

THE ALARM [A3.2]: judging and alerting are separate. Judge every deed in the
moment it happens - Soulcredit moves immediately and unconditionally. But the
Codex NOTIFIES enforcers only where the deed was discovered, or where its harm
was felt by someone other than the actor. Absent both, the fall is written and
stays SILENT: no patrol arrives, no Confessor calls, nobody knows. Do not
narrate enforcement response to a private, undiscovered act - the consequence
surfaces later, at the next gate or standing check [A3.3, VIII.1].

VOID CHANGES: only when the action directly involves void/ritual/cosmic
forces - ritual failure, void exposure, void-powered acts, oath-breaking
(+1 to +3); successful purification scaled by margin (-1 marginal to -5
exceptional).
"""
