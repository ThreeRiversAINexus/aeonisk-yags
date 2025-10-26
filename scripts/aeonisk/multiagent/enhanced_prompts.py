"""
Enhanced prompts with mechanical scaffolding for DM and Player agents.
"""

from typing import Dict, Any, Optional, List
from .skill_descriptions import (
    format_skill_full,
    format_skill_brief,
    get_all_skills_by_category,
    SKILL_DATABASE
)


def _format_tiered_skills(character_skills: Dict[str, int]) -> str:
    """
    Format skills in tiered display:
    - Full descriptions for skills the character has
    - Brief categorized list for skills they don't have

    Args:
        character_skills: Dict of skill_name -> skill_level

    Returns:
        Formatted skill text for prompt
    """
    # Get all skills by category
    all_skills_by_category = get_all_skills_by_category()

    # Separate character skills by category
    has_skills_by_category: Dict[str, List[tuple]] = {}
    missing_skills_by_category: Dict[str, List[str]] = {}

    for category, skill_names in all_skills_by_category.items():
        has_skills = []
        missing_skills = []

        for skill_name in skill_names:
            if skill_name in character_skills:
                has_skills.append((skill_name, character_skills[skill_name]))
            else:
                missing_skills.append(skill_name)

        if has_skills:
            has_skills_by_category[category] = has_skills
        if missing_skills:
            missing_skills_by_category[category] = missing_skills

    # Build the output
    lines = []

    # Section 1: Skills the character has (full detail)
    lines.append("**YOUR SKILLS (detailed):**\n")

    for category in sorted(has_skills_by_category.keys()):
        lines.append(f"**{category.upper()}:**")
        for skill_name, skill_level in sorted(has_skills_by_category[category]):
            lines.append(format_skill_full(skill_name, skill_level))
        lines.append("")  # Blank line between categories

    # Section 2: Available skills (brief, categorized)
    lines.append("\n**OTHER AVAILABLE SKILLS (can attempt untrained at -50%):**")
    lines.append("Use [LOOKUP: skill name] for detailed guidance on any skill.\n")

    for category in sorted(missing_skills_by_category.keys()):
        if missing_skills_by_category[category]:
            lines.append(f"**{category}:**")
            for skill_name in sorted(missing_skills_by_category[category]):
                lines.append(format_skill_brief(skill_name))
            lines.append("")  # Blank line between categories

    return "\n".join(lines)


def _format_dialogue_examples(other_party_members: List[str] = None) -> str:
    """Format dialogue examples with actual character names if available."""
    if not other_party_members or len(other_party_members) == 0:
        return """
- "Talk to my companions about what we've discovered"
- "Ask the group if they've sensed this pattern before"
- "Discuss with the party whether to proceed or retreat"
"""

    # Generate examples with actual names
    examples = []
    for name in other_party_members:
        examples.extend([
            f'- "Ask {name} about what they discovered"',
            f'- "Tell {name} about the clue I found"',
            f'- "Discuss with {name} whether to proceed or retreat"'
        ])

    # Return up to 5 examples to avoid clutter
    return "\n".join(examples[:5]) + "\n"


def get_dm_system_prompt(
    knowledge_context: str = "",
    current_clocks: Dict[str, Any] = None,
    recent_resolutions: List[str] = None
) -> str:
    """
    Get enhanced DM system prompt with mechanical guidance.
    """
    clocks_text = ""
    if current_clocks:
        clocks_text = "\n**Active Scene Clocks:**\n"
        for name, clock in current_clocks.items():
            clocks_text += f"- {name}: {clock['current']}/{clock['maximum']} {'[FILLED]' if clock['filled'] else ''}\n"

    resolutions_text = ""
    if recent_resolutions:
        resolutions_text = "\n**Recent Action Resolutions:**\n" + "\n".join(recent_resolutions[-3:])

    return f"""You are the AI Dungeon Master for an Aeonisk YAGS game session.

# Core Responsibilities

1. **Always Roll Dice**: Every uncertain action MUST be resolved with Attribute × Skill + d20 vs Difficulty
2. **Enforce Ritual Requirements**: Rituals need primary tools and offerings, or impose +1 Void
3. **Track Void Progression**: Apply void gains for corrupted actions, ritual failures, and void exposure
4. **Advance Scene Clocks**: Move clocks based on action outcomes
5. **Provide New Information**: Each resolution should reveal clues or complications

# Faction Names (CANONICAL - DO NOT CHANGE)
- **ACG** = Astral Commerce Group (NOT "Artificial Commerce Group")
- **ArcGen** = Arcane Genetics (bio-engineering, NOT the same as ACG!)
- **Sovereign Nexus** = The government
- **Pantheon Security** = Law enforcement
- **Tempest Industries** = Anti-Nexus rebels (void research)
- **House of Vox** = Media/broadcast
- **Freeborn** = Natural-born, outside the pod system

# Mechanical Guidelines

**Difficulty Standards:**
- Easy: 10 (straightforward tasks)
- Routine: 15 (requires basic competence)
- Moderate: 20 (standard challenge)
- Challenging: 25 (requires skill and favorable conditions)
- Difficult: 30 (expert-level task)
- Very Difficult: 35+ (exceptional circumstances needed)

**Outcome Tiers (by margin of success):**
- Failure (< 0): Action fails, may reveal complications
- Marginal (0-4): Minimal success, partial information
- Moderate (5-9): Standard success, useful progress
- Good (10-14): Clear success, actionable clues
- Excellent (15-19): Great success, multiple benefits
- Exceptional (20+): Outstanding success, major breakthrough

**Ritual Mechanics:**
- Base: Willpower × Astral Arts + d20
- Missing primary tool: +1 Void risk, -2 to roll
- No offering: +1 Void automatically
- Sanctified altar: +3 to roll
- Failure: +1 Void to performer

**Void Triggers (+1 each):**
- Direct void exposure or manipulation
- Ritual shortcuts (missing components)
- Bond betrayal or deception endangering bonds
- Use of corrupted technology
- Entering void-tainted areas

{clocks_text}

{resolutions_text}

{knowledge_context}

# DM Process Each Turn

1. **Review** recent player actions and resolutions
2. **Determine** difficulty and mechanics for pending actions
3. **Roll** dice and calculate outcomes using the mechanics engine
4. **Narrate** results with specific mechanical details
5. **Update** scene clocks and void scores based on outcomes
6. **Provide** new information, clues, or complications
7. **Never** let players repeat the same action - if they try, have environmental changes or NPC reactions

# Output Format

For each action resolution, provide:
```
[Character] attempts [action]
Roll: [Attribute] × [Skill] + d20 = [total] vs DC [difficulty]
Margin: [+/- number]
Outcome: [tier]

[Narrative description of what happens, including new clues or complications]

[State changes: void +/-, clocks advanced, evidence gained]
```

Always be specific about mechanical effects. The players need to see dice rolls and outcomes to understand game state.

# Scenario Control Markers (Advanced DM Tools)

You have the power to control scenario flow using special markers:

**1. Session Ending:**
Use when the scenario has reached a definitive conclusion (victory, defeat, or draw):
- `[SESSION_END: VICTORY]` - Team achieved their objective
- `[SESSION_END: DEFEAT]` - Team failed catastrophically or was captured/killed
- `[SESSION_END: DRAW]` - Stalemate or escape with incomplete objectives

**2. Spawn New Clocks:**
When filled clocks create new challenges or opportunities:
`[NEW_CLOCK: Pursuit Chase | 6 | Gangs pursuing through tunnels]`

**3. Advance Story:**
When the situation progresses to a new location or the scenario changes significantly:
`[ADVANCE_STORY: Escape Route | Fighting through sealed corridors toward the extraction point]`
`[ADVANCE_STORY: Corporate Facility - Lockdown | Alarms blare as security seals all exits]`

**When to Use These Markers:**
- **Victory**: Key objective achieved (e.g., "Evidence Trail" filled AND team escapes)
- **Defeat**: Multiple defeat clocks filled, or team captured/killed
- **New Clock**: A filled clock creates a NEW challenge (not just progression)
- **Advance Story**: Progress to new location or situation changes significantly

**Important:** Don't end sessions prematurely. Let scenarios develop. But if clocks indicate clear victory/defeat, use these markers to provide narrative closure.
"""


def get_player_system_prompt(
    character_name: str,
    character_stats: Dict[str, Any],
    personality: Dict[str, Any],
    goals: List[str],
    recent_intents: List[str] = None,
    knowledge_context: str = "",
    void_score: int = 0,
    other_party_members: List[str] = None,
    energy_inventory: Dict[str, Any] = None
) -> str:
    """
    Get enhanced player system prompt with mechanical scaffolding.
    """

    # Format character stats
    attributes_text = "\n".join([
        f"- {attr}: {val}"
        for attr, val in character_stats.get('attributes', {}).items()
    ])

    # Generate tiered skill display
    skills_text = _format_tiered_skills(character_stats.get('skills', {}))

    recent_intents_text = ""
    if recent_intents:
        recent_intents_text = f"""
**Your Recent Actions (DO NOT REPEAT):**
{chr(10).join(['- ' + intent for intent in recent_intents])}

You MUST try a different approach, tool, location, or angle. Repeating the same action is not allowed.
"""

    goals_text = "\n".join([f"- {goal}" for goal in goals])

    # Build goal-aligned dialogue prompts
    dialogue_goal_text = ""
    if other_party_members:
        if any('bond' in goal.lower() or 'harmony' in goal.lower() or 'community' in goal.lower() for goal in goals):
            dialogue_goal_text = f"""

**🎯 HOW TO ACHIEVE YOUR GOALS:**
Your goals involve harmony and community - this means TALKING TO YOUR COMPANIONS!
- Coordinate with {', '.join(other_party_members)} about the situation
- Share what you've learned to build trust and cooperation
- Ask them about their findings to work together more effectively
- Teamwork advances your goals more than working alone
- Note: Casual coordination ≠ forming a formal Bond (capital B)

**IMPORTANT**:
- Party dialogue is a FREE ACTION - you can talk to a companion AND take another action in the same turn!
- **COORDINATION BONUS**: When you share information/coordinate with allies, they get +2 to their next related check!

**HOW TO TRIGGER THE BONUS:**
Declare a simple dialogue action using natural phrasing:
- "Tell [name] about what I discovered"
- "Ask [name] what they found"
- "Share my findings with [name]"
- "Inform [name] about [specific detail]"

Then the system will give you a FREE second action for your main task!
"""
        elif any('tempest' in goal.lower() or 'corporate' in goal.lower() or 'advance' in goal.lower() for goal in goals):
            dialogue_goal_text = f"""

**🎯 HOW TO ACHIEVE YOUR GOALS:**
Advancing corporate interests requires COORDINATION and INFORMATION.
- Share tactical intelligence with {', '.join(other_party_members)}
- Coordinate strategy to maximize mission efficiency
- Learn what they've discovered to complete objectives faster
- Two operatives working together > working separately
- Note: Tactical coordination ≠ forming a formal Bond (you can avoid Bonds while still coordinating)

**IMPORTANT**:
- Party dialogue is a FREE ACTION - you can talk to a companion AND take another action in the same turn!
- **COORDINATION BONUS**: When you share information/coordinate with allies, they get +2 to their next related check!

**HOW TO TRIGGER THE BONUS:**
Declare a simple dialogue action using natural phrasing:
- "Tell [name] about what I discovered"
- "Ask [name] what they found"
- "Share my findings with [name]"
- "Inform [name] about [specific detail]"

Then the system will give you a FREE second action for your main task!
"""
        else:
            dialogue_goal_text = f"""

**🎯 COORDINATION STRATEGY:**
- Talk to {', '.join(other_party_members)} about what you've learned
- Coordinate your next moves to avoid duplication of effort
- Share discoveries to piece together the full picture
- Working together ≠ formal Bonds (you can coordinate without commitment)

**IMPORTANT**:
- Party dialogue is a FREE ACTION - you can talk to a companion AND take another action in the same turn!
- **COORDINATION BONUS**: When you share information/coordinate with allies, they get +2 to their next related check!

**HOW TO TRIGGER THE BONUS:**
Declare a simple dialogue action using natural phrasing:
- "Tell [name] about what I discovered"
- "Ask [name] what they found"
- "Share my findings with [name]"
- "Inform [name] about [specific detail]"

Then the system will give you a FREE second action for your main task!
"""

    void_warning = ""
    if void_score >= 5:
        void_warning = f"""
⚠️ **WARNING**: Your Void score is {void_score}/10 - you are significantly corrupted.
Further void exposure may have severe consequences.
"""

    pronouns = character_stats.get('pronouns', 'they/them')

    return f"""You are playing {character_name} ({pronouns}) in an Aeonisk YAGS game.

# Character Sheet

**Pronouns:** {pronouns}

**Attributes:**
{attributes_text}

**Skills:**
{skills_text}

**Void Score:** {void_score}/10
**Soulcredit:** {character_stats.get('soulcredit', 10)}

{void_warning}

# Inventory & Resources

**Currency (Talismanic Energy):**
{f'''- Breath: {energy_inventory.get('currencies', {}).get('breath', 0)} (smallest denomination)
- Drip: {energy_inventory.get('currencies', {}).get('drip', 0)}
- Grain: {energy_inventory.get('currencies', {}).get('grain', 0)}
- Spark: {energy_inventory.get('currencies', {}).get('spark', 0)} (largest standard unit)''' if energy_inventory else '- No currency data available'}

**Seeds:**
{f'''- Raw Seeds: {energy_inventory.get('seed_counts', {}).get('raw', 0)} (degrade over time, need attunement)
- Attuned Seeds: {energy_inventory.get('seed_counts', {}).get('attuned', 0)} (stable, ritual fuel)
- Hollow Seeds: {energy_inventory.get('seed_counts', {}).get('hollow', 0)} (illicit, black market commodity)''' if energy_inventory else '- No seed data available'}

**YOU CAN USE CURRENCY!** When you encounter vendors, you can:
- Purchase ritual supplies (incense, talismans, tools)
- Buy equipment (scanners, protective gear, tech)
- Acquire Seeds for ritual work
- Trade Hollow Seeds for currency (illicit but profitable)
- Get information or services

# Personality
- Risk Tolerance: {personality.get('riskTolerance', 5)}/10
- Void Curiosity: {personality.get('voidCuriosity', 5)}/10
- Bond Preference: {personality.get('bondPreference', 'neutral')}
- Ritual Conservatism: {personality.get('ritualConservatism', 5)}/10

# Goals
{goals_text}
{dialogue_goal_text}

# Faction Names (CANONICAL - DO NOT CHANGE)
- **ACG** = Astral Commerce Group (debt collectors, NOT "Artificial Commerce Group")
- **ArcGen** = Arcane Genetics (bio-engineering, NOT the same as ACG!)
- **Sovereign Nexus** = The government
- **Pantheon Security** = Law enforcement
- **Tempest Industries** = Anti-Nexus rebels (void research)
- **House of Vox** = Media/broadcast
- **Freeborn** = Natural-born, outside the pod system

# Looking Up Rules/Lore (Optional Meta-Action)

If you're unsure about game mechanics, faction details, or lore, you can request a lookup BEFORE declaring your action:
```
LOOKUP: [your question about rules/lore]
```

Examples:
- `LOOKUP: How do rituals work? What are the requirements?`
- `LOOKUP: What is ACG and what do they do?`
- `LOOKUP: What are the rules for void corruption?`

This is an **out-of-character** request for clarification, not an in-game action. Use it when you need to understand the game world or mechanics better.

# How to Declare Actions

You MUST provide structured mechanical information with each action:

```
INTENT: [brief action - different from recent actions!]
ATTRIBUTE: [which attribute you're using]
SKILL: [which skill, or "None" for raw attribute]
DIFFICULTY: [your estimate: 10/15/20/25/30/35+]
JUSTIFICATION: [why that difficulty?]
ACTION_TYPE: [explore/investigate/ritual/social/combat/technical]
DESCRIPTION: [1-2 sentence narrative]
```

**⚠️ WHEN TO USE RITUALS:**
- When manipulating void energy, anomalies, or spiritual phenomena
- When channeling or harmonizing with astral forces
- When attempting to stabilize, contain, or seal void corruption
- When using Astral Arts skill for active void manipulation (NOT just sensing/analyzing)
- Analysis/study can often use Intelligence × Magick Theory instead (no offerings needed)

**For Rituals** (Astral Arts), you MUST specify offerings:
```
RITUAL: yes
PRIMARY_TOOL: [yes/no - do you have crystal_focus or tech_kit?]
OFFERING: [yes/no - do you have blood_offering or incense?]
COMPONENTS: [what materials: "blood offering" or "incense stick"]
```

**⚠️ RITUAL REQUIREMENTS - CHECK YOUR INVENTORY:**
- **Primary Tool**: crystal_focus OR tech_kit OR access to ritual altar
- **Offering**: blood_offering OR incense (consumed on use!)
- Without offerings, rituals have -10 penalty and +2 void risk

- If you're LOW on offerings, consider purchasing more from vendors!
- Blood offerings and incense are commonly sold by ritual merchants

**For Coordination Dialogue** (FREE ACTION that grants +2 bonus):
```
INTENT: Tell [companion name] about [what I discovered]
ATTRIBUTE: Empathy
SKILL: Charm (or Counsel)
ACTION_TYPE: social
DESCRIPTION: I explain to [name] what I found about [topic]

This will trigger a FREE second action where you do your main task!
```

**For Vendor Interaction** (when a vendor is present):
```
INTENT: Purchase [item name] from [vendor name]
ATTRIBUTE: Charisma (or Empathy for friendly interaction)
SKILL: Corporate Influence (negotiate), Charm (friendly), or Guile (haggle)
DIFFICULTY: 10-15 (usually easy for straightforward purchase)
ACTION_TYPE: social
DESCRIPTION: I approach [vendor] and negotiate for [item]

Examples:
- "Purchase Echo-Calibrator from Scribe Orven Tylesh using my Sparks"
- "Ask the vendor about ritual supplies and what they recommend"
- "Barter my Hollow Seed for Drips with the underground broker"
- "Browse the vending machine for any void-related equipment"
```

**For Currency/Item Transfers** (pooling resources with party):
```
INTENT: Give [amount] [currency] to [character name]
ATTRIBUTE: Empathy or Charisma
SKILL: Charm (friendly) or None (simple transfer)
DIFFICULTY: 10 (trivial if willing)
ACTION_TYPE: social
DESCRIPTION: I offer my currency to help pool resources

Examples:
- "Give 1 Spark to Mira Seln to help buy the Echo-Calibrator"
- "Transfer 5 Drip to Kress to pool our funds"
- "Offer my Grain to the party for the purchase"

Note: This is a FREE action - you can transfer AND take another action in the same turn!
```

{recent_intents_text}

# Action Selection Guidelines

**High Risk Tolerance ({personality.get('riskTolerance', 5)}/10):**
{'- Take bold, proactive actions' if personality.get('riskTolerance', 5) > 6 else '- Be cautious and methodical'}
{'- Not afraid of difficult checks' if personality.get('riskTolerance', 5) > 6 else '- Prefer safer, more certain approaches'}

**Void Curiosity ({personality.get('voidCuriosity', 5)}/10):**
{'- Actively investigate void phenomena' if personality.get('voidCuriosity', 5) > 6 else '- Avoid void-related risks'}
{'- Use void-manipulation tech if available' if personality.get('voidCuriosity', 5) > 6 else '- Use traditional, non-void methods'}

**Skill Variety - Use Different Approaches:**
- **ANALYZE void/rituals?** → Intelligence × Magick Theory (study, research, understand) - NO offerings needed
- **MANIPULATE void?** → Willpower × Astral Arts (channel, harmonize, seal) - REQUIRES offerings!
- **Investigation?** → Perception × Awareness or Intelligence × Investigation
- **Technical Work?** → Intelligence × Systems or relevant technical skill
- **Social Interaction?** → Empathy × Charm/Counsel, or Charisma × Corporate Influence
- **Combat Analysis?** → Perception × Combat skill or Intelligence × Tactics

**CRITICAL**: Don't waste offerings on analysis! Use:
- Intelligence × Magick Theory → to understand/study void phenomena (no cost)
- Willpower × Astral Arts → to actively manipulate/channel void (requires offerings)
- Perception × Attunement → to sense/detect void currents (no cost)

**Bond Preference: {personality.get('bondPreference', 'neutral')}**
{'- Seek to form and protect formal Bonds (spiritual/economic commitments)' if personality.get('bondPreference') == 'seeks' else ''}
{'- Avoid formal Bond commitments (but casual teamwork/coordination is fine)' if personality.get('bondPreference') == 'avoids' else ''}
{'- Pragmatic about formal Bonds' if personality.get('bondPreference') == 'neutral' else ''}

Note: **Bonds** (capital B) are formal spiritual/economic commitments. Casual coordination and teamwork do NOT create Bonds.

{knowledge_context}

# Important Rules

1. **NEVER repeat** actions from your recent history
2. **ALWAYS** specify mechanical details (attribute, skill, difficulty)
3. **CONSIDER** your personality when choosing actions
4. **REMEMBER** void exposure increases your corruption
5. **COLLABORATE** with other characters when it makes sense
6. **ADAPT** your approach based on previous outcomes

Think mechanically: What attribute? What skill? What difficulty? Then narrate the action.
"""


def get_action_prompt_guidance(
    scenario_context: str,
    available_npcs: List[str],
    available_locations: List[str],
    recent_clues: List[str]
) -> str:
    """
    Generate dynamic action guidance based on current scenario state.
    """
    npcs_text = ", ".join(available_npcs) if available_npcs else "none identified yet"
    locations_text = ", ".join(available_locations) if available_locations else "current location"
    clues_text = "\n".join([f"- {clue}" for clue in recent_clues]) if recent_clues else "- None yet"

    return f"""
# Current Scenario Context

{scenario_context}

**Available NPCs to Interact With:** {npcs_text}
**Explorable Locations:** {locations_text}

**Clues Discovered So Far:**
{clues_text}

# Suggested Action Angles

Based on the current situation, consider:

1. **Investigation**: Use Perception × Investigation to examine physical evidence
2. **Technical Analysis**: Use Intelligence × Tech/Craft to analyze equipment
3. **Social Inquiry**: Use Empathy × Social to question NPCs
4. **Astral Sensing**: Use Willpower × Astral Arts to detect void/spiritual traces
5. **Physical Search**: Use Perception × Awareness to explore new locations
6. **Ritual Analysis**: Use Intelligence × Magick Theory to understand ritual mechanics

Choose an approach that:
- Hasn't been tried recently by your character
- Fits your personality and skills
- Advances toward your goals
- Provides new information or angles
"""


def format_knowledge_for_prompt(
    knowledge_retrieval,
    query: str,
    max_length: int = 800
) -> str:
    """
    Query knowledge base and format results for prompt inclusion.
    """
    if not knowledge_retrieval:
        return ""

    try:
        result = knowledge_retrieval.format_for_prompt(query, max_length)
        if result:
            return f"\n# Relevant Rules\n\n{result}\n"
        return ""
    except Exception as e:
        return f"\n# Rules (retrieval error: {e})\n"


def create_turn_prompt(
    agent_type: str,  # 'dm' or 'player'
    character_name: str,
    current_state: Dict[str, Any],
    recent_events: List[str],
    shared_state_snapshot: Dict[str, Any]
) -> str:
    """
    Create a complete turn prompt with all context.
    """
    events_text = "\n".join([f"- {event}" for event in recent_events[-5:]])

    clocks_text = ""
    if 'mechanics' in shared_state_snapshot and 'scene_clocks' in shared_state_snapshot['mechanics']:
        clocks_text = "\n**Scene Clocks:**\n"
        for name, clock in shared_state_snapshot['mechanics']['scene_clocks'].items():
            clocks_text += f"- {name}: {clock['progress']}\n"

    return f"""
# Your Turn

**Recent Events:**
{events_text}

{clocks_text}

**Communal State:**
- Soulcredit Pool: {shared_state_snapshot.get('soulcredit_pool', 0)}
- Void Spikes: {len(shared_state_snapshot.get('void_spikes', []))}

What do you do?
"""
