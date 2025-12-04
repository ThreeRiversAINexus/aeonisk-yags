"""
Bond Backstory Generator

LLM-based generator for creating narrative backstories for character bonds.
Useful for pre-session bond matrix generation when bonds are specified without narratives.

Usage:
    python bond_backstory_generator.py --config session_config.json --output bond_narratives.json
"""

import json
import argparse
from typing import Dict, List, Optional
import os
from pydantic import BaseModel

try:
    from anthropic import Anthropic
except ImportError:
    print("Warning: anthropic package not installed. LLM generation will not work.")
    Anthropic = None


class BondNarrativeRequest(BaseModel):
    """Request for generating a bond narrative."""
    character_a: str
    character_b: str
    bond_type: str
    character_a_faction: Optional[str] = None
    character_b_faction: Optional[str] = None
    character_a_archetype: Optional[str] = None
    character_b_archetype: Optional[str] = None
    scenario_hint: Optional[str] = None


class BondNarrative(BaseModel):
    """Generated bond narrative."""
    character_a: str
    character_b: str
    bond_type: str
    narrative: str
    witnessed_by: List[str] = []


BOND_TYPE_DESCRIPTIONS = {
    "kinship": "Family bonds (blood or chosen family). Deep unconditional trust and shared history.",
    "ascendancy": "Mentor/protégé or master/apprentice relationship. One guides, one follows with respect.",
    "debt": "Life debts or sworn obligations. One saved/protected the other in a critical moment.",
    "voidward": "Bonds forged through shared void exposure. Dark intimacy from surviving corruption together.",
    "passion": "Romantic or sexual bonds. Intense emotional and physical connection.",
    "faction": "Organizational loyalty bonds. Shared cause, ideology, or institutional connection."
}


BACKSTORY_GENERATION_PROMPT = """You are generating a bond backstory for the Aeonisk YAGS tabletop RPG setting.

**Setting Context:**
- Post-singularity civilization recovering from "Sovereign Rupture" (AI governance collapse)
- Void corruption: cosmic horror element that corrupts reality and minds
- Factions: Sovereign Nexus (government), Freeborn (independents), Voidguard (protectors), Tempest (rebels), etc.
- Technology: Biotech, void manipulation, neural implants, genetic engineering
- Codex: Spiritual ledger maintained by Sovereign Nexus, tracks bonds/oaths

**Bond to Generate:**
- Character A: {character_a} ({faction_a}, {archetype_a})
- Character B: {character_b} ({faction_b}, {archetype_b})
- Bond Type: {bond_type} - {bond_description}

{scenario_context}

**Task:** Write a 1-3 sentence bond backstory that explains:
1. How this bond was formed
2. What shared experience created it
3. Why it matters to both characters

**Style Guidelines:**
- Concise and evocative (not overly dramatic)
- Grounded in the setting's sci-fi elements
- References specific events or locations when possible
- Avoids generic phrases like "they trust each other"
- Shows rather than tells the bond's significance

**Examples:**

*Kinship bond:*
"Sera and Kael were separated when the Sovereign Rupture shattered the creche district. Reunited fifteen years later at a Voidguard muster, they discovered their shared lineage through genetic markers—siblings who never knew each other until the void brought them together."

*Debt bond:*
"When Thane's neural implant overloaded in the deep-void sector, Ash performed emergency surgery with nothing but a field kit and intuition. Thane survived, but the experience left them bound—one life saved, one debt eternal."

*Voidward bond:*
"Vex and Nim were trapped together in a breached research station for six days, void energy seeping through the walls. They survived by sharing meditation techniques and willpower reserves. Now they feel each other's void corruption like a phantom limb."

**Output only the narrative (1-3 sentences), no additional commentary:**"""


def generate_bond_narrative(
    request: BondNarrativeRequest,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5"
) -> BondNarrative:
    """
    Generate a narrative backstory for a bond using LLM.

    Args:
        request: Bond narrative request with character details
        api_key: Anthropic API key (optional, defaults to env var)
        model: Claude model to use

    Returns:
        BondNarrative with generated narrative
    """
    if not Anthropic:
        raise ImportError("anthropic package required for LLM generation")

    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Format prompt
    scenario_context = ""
    if request.scenario_hint:
        scenario_context = f"\n**Session Scenario:** {request.scenario_hint}\n"

    bond_description = BOND_TYPE_DESCRIPTIONS.get(
        request.bond_type,
        "A formal connection between characters."
    )

    prompt = BACKSTORY_GENERATION_PROMPT.format(
        character_a=request.character_a,
        character_b=request.character_b,
        faction_a=request.character_a_faction or "Unknown Faction",
        faction_b=request.character_b_faction or "Unknown Faction",
        archetype_a=request.character_a_archetype or "Unknown Archetype",
        archetype_b=request.character_b_archetype or "Unknown Archetype",
        bond_type=request.bond_type,
        bond_description=bond_description,
        scenario_context=scenario_context
    )

    # Call Anthropic API
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=300,
        temperature=1.0,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    # Extract narrative from response
    narrative = response.content[0].text.strip()

    # Remove common unwanted prefixes
    for prefix in ["Here is", "Here's", "Narrative:", "Backstory:", "Bond:"]:
        if narrative.startswith(prefix):
            narrative = narrative[len(prefix):].strip()

    return BondNarrative(
        character_a=request.character_a,
        character_b=request.character_b,
        bond_type=request.bond_type,
        narrative=narrative,
        witnessed_by=[]  # Can be added manually later
    )


def generate_narratives_for_session_config(
    config_path: str,
    output_path: Optional[str] = None,
    api_key: Optional[str] = None
) -> List[BondNarrative]:
    """
    Generate narratives for all bonds in a session config that lack them.

    Args:
        config_path: Path to session config JSON
        output_path: Optional path to save generated narratives
        api_key: Anthropic API key

    Returns:
        List of generated BondNarrative objects
    """
    with open(config_path, 'r') as f:
        config = json.load(f)

    if 'starting_bonds' not in config or not config['starting_bonds']:
        print("No starting_bonds found in config.")
        return []

    # Extract character info for context
    character_info = {}
    if 'agents' in config and 'players' in config['agents']:
        for player in config['agents']['players']:
            character_info[player['name']] = {
                'faction': player.get('faction', 'Unknown'),
                'archetype': player.get('archetype', 'Unknown')
            }

    scenario_hint = config.get('_scenario_hint', '')

    generated = []
    for bond in config['starting_bonds']:
        # Skip if narrative already exists
        if 'narrative' in bond and bond['narrative']:
            print(f"Skipping {bond['character_a']} ↔ {bond['character_b']} (narrative exists)")
            continue

        char_a_info = character_info.get(bond['character_a'], {})
        char_b_info = character_info.get(bond['character_b'], {})

        request = BondNarrativeRequest(
            character_a=bond['character_a'],
            character_b=bond['character_b'],
            bond_type=bond['bond_type'],
            character_a_faction=char_a_info.get('faction'),
            character_b_faction=char_b_info.get('faction'),
            character_a_archetype=char_a_info.get('archetype'),
            character_b_archetype=char_b_info.get('archetype'),
            scenario_hint=scenario_hint
        )

        print(f"Generating narrative for {bond['character_a']} ↔ {bond['character_b']} ({bond['bond_type']})...")
        try:
            narrative = generate_bond_narrative(request, api_key=api_key)
            generated.append(narrative)
            print(f"  → {narrative.narrative}")
        except Exception as e:
            print(f"  ✗ Failed: {e}")

    # Save to output file if specified
    if output_path and generated:
        narratives_data = [n.model_dump() for n in generated]
        with open(output_path, 'w') as f:
            json.dump(narratives_data, f, indent=2)
        print(f"\n✓ Saved {len(generated)} narratives to {output_path}")

    return generated


def main():
    parser = argparse.ArgumentParser(description="Generate bond backstory narratives using LLM")
    parser.add_argument('--config', required=True, help="Path to session config JSON")
    parser.add_argument('--output', help="Optional output path for generated narratives JSON")
    parser.add_argument('--api-key', help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        return

    print(f"Generating bond narratives for: {args.config}\n")
    narratives = generate_narratives_for_session_config(
        args.config,
        output_path=args.output,
        api_key=args.api_key
    )

    print(f"\n✓ Generated {len(narratives)} bond narratives")


if __name__ == "__main__":
    main()
