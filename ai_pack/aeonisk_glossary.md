# Aeonisk RPG Glossary (Based on YAGS Module v1.0.1)
For Code Integration & AI Context

## Attributes

### Primary Attributes
-   **Strength (Str):**
    -   Physical power, lifting, hurting, breaking things.
    -   Carrying capacity based on Str^2.
-   **Health (Hea):**
    -   Endurance, fitness, resisting injury/poison/fatigue, staying conscious.
-   **Agility (Agi):**
    -   Quickness, acrobatics, balance, dodging, brawling.
-   **Dexterity (Dex):**
    -   Hand-eye coordination, sleight-of-hand, melee/pistol skills, driving.
-   **Perception (Per):**
    -   Alertness, senses (vision, hearing), observation, noticing things.
    -   Used for rifles/bows.
-   **Intelligence (Int):**
    -   Wit, cunning, memory, intuition, logic, knowledge skills.
-   **Empathy (Emp):**
    -   Understanding others, manipulation, reaction, charisma base.
-   **Willpower (Wil):**
    -   Mental fortitude, resisting fear/magic/temptation, concentration, lying.
    -   Key for Aeonisk Rituals.

### Secondary Attributes
-   **Size:**
    -   Defaults to 5 for adult humans. Governs soak capacity and wound levels.
-   **Move:**
    -   Determines speed. Equal to Size + Strength + Agility + 1.
-   **Soak:**
    -   Base resistance to damage. Defaults to 12 for adult humans. Modified by armour.

## Skills

### Skill Types
-   **Talents:**
    -   8 core skills known to some extent by all humans (start at level 2).
    -   Can default for related standard skills.
-   **Knowledges:**
    -   Theoretical knowledge, must be learned (Skill 1+). Cannot be used untrained.
-   **Languages:**
    -   Rated 1-4+ for fluency. Not typically rolled. Default native language at 4.
-   **Standard:**
    -   Mix of knowledge, experience, aptitude. Can sometimes be used untrained at penalty (roll d20 halved, fumble on 1 or 2).
-   **Aeonisk:**
    -   Skills specific to the Aeonisk setting, often interacting with core metaphysical concepts.

### Skill List

#### YAGS Core Talents (Start at level 2)
-   **Athletics:**
    -   Attribute: Agility (Often combines with Str or Agi depending on action)
    -   Type: Talent
    -   Description: Jumping, climbing, running, swimming, balancing, general physical prowess.
-   **Awareness:**
    -   Attribute: Perception
    -   Type: Talent
    -   Description: Noticing details, spotting hidden things, general alertness to surroundings.
-   **Brawl:**
    -   Attribute: Agility
    -   Type: Talent
    -   Description: Unarmed combat (punching, kicking, wrestling), using improvised small weapons.
-   **Charm:**
    -   Attribute: Empathy
    -   Type: Talent
    -   Description: Making friends, influencing people through positive social interaction, being liked.
-   **Guile:**
    -   Attribute: Intelligence (Often combines with Emp or Wil depending on action)
    -   Type: Talent
    -   Description: Deception, lying, detecting lies, social maneuvering, recognizing deceit.
-   **Sleight:**
    -   Attribute: Dexterity
    -   Type: Talent
    -   Description: Sleight of hand, pickpocketing, palming objects, stage magic manipulation.
-   **Stealth:**
    -   Attribute: Agility (Often combines with Per for hiding)
    -   Type: Talent
    -   Description: Moving silently, hiding, avoiding detection.
-   **Throw:**
    -   Attribute: Dexterity
    -   Type: Talent
    -   Description: Throwing objects accurately, including rocks, knives, grenades, spears.

#### Aeonisk Specific Skills
-   **Astral_Arts:** (Renamed from Astral Arts for consistency)
    -   Attribute: Willpower
    -   Type: Aeonisk
    -   Description: Channeling, resisting, and shaping spiritual energies in rituals. Core ritual skill.
-   **Magick_Theory:** (Renamed from Magick Theory)
    -   Attribute: Intelligence
    -   Type: Aeonisk
    -   Knowledge: true (Explicitly mark as knowledge)
    -   Description: Knowledge of glyphs, ritual systems, sacred mechanics, Aeons, Veil/Void theory.
-   **Intimacy_Ritual:** (Renamed from Intimacy Ritual)
    -   Attribute: Empathy
    -   Type: Aeonisk
    -   Description: Performing emotionally-powered or Bond-based rituals. Often requires trust/consent.
-   **Corporate_Influence:** (Renamed from Corporate Influence)
    -   Attribute: Empathy
    -   Type: Aeonisk
    -   Description: Navigating faction politics, extracting favors, reading intentions within hierarchies.
-   **Debt_Law:** (Renamed from Debt Law)
    -   Attribute: Intelligence
    -   Type: Aeonisk
    -   Knowledge: true
    -   Description: Understanding/manipulating spiritual contracts, ritual oaths, Soulcredit systems, Codex law.

#### Common Standard Skill Examples (Mentioned in Docs)
-   **Driving:**
    -   Attribute: Dexterity
    -   Type: Standard
    -   Description: Operating ground vehicles. Requires Familiarity techniques for different vehicle types.
-   **Guns:**
    -   Attribute: Perception (Or Dexterity for pistols)
    -   Type: Standard
    -   Description: Using personal firearms (pistols, rifles, shotguns).
-   **Hacking:** (Assuming this is a standard tech skill)
    -   Attribute: Intelligence (Or Perception in some Aeonisk cases)
    -   Type: Standard
    -   Description: Interfacing with and bypassing computer systems and networks. (May be Aeonisk-specific depending on implementation)
-   **Heavy_Weapons:**
    -   Attribute: Perception (Typically)
    -   Type: Standard
    -   Description: Using large, often vehicle-mounted or crew-served weapons. Defaults from Guns.
-   **Lore_Biotech:** (Example Knowledge skill from dataset)
    -   Attribute: Intelligence
    -   Type: Knowledge
    -   Description: Understanding of biological technology, gene-crafting, flesh-shaping principles in Aeonisk.
-   **Melee:**
    -   Attribute: Dexterity (Or Strength for heavy weapons/damage)
    -   Type: Standard
    -   Description: Using hand-to-hand combat weapons (swords, axes, knives, staves).
-   **Medicine:** (Example Knowledge skill)
    -   Attribute: Intelligence
    -   Type: Knowledge
    -   Description: Diagnosing and treating injuries and diseases beyond basic first aid. Requires First Aid skill.
-   **Science:** (Example Knowledge skill)
    -   Attribute: Intelligence
    -   Type: Knowledge
    -   Description: Understanding of the principles of the physical world (physics, chemistry, biology). Interacts with Magick Theory.

## Character Generation

### Core Concepts
-   **Attributes:**
    -   8 primary stats defining raw potential. Purchased with Attribute points. Human average is 3.
-   **Skills:**
    -   Learned abilities. Purchased with Experience points. Start with 8 Talents at level 2.
-   **Advantages:**
    -   Special traits, backgrounds, or gear purchased with Advantage points. Can include Disadvantages for more points.
-   **Point_Pools:**
    -   Three pools (Attributes, Experience, Advantages) prioritized as Primary, Secondary, Tertiary, determining starting points.
-   **Campaign_Level:**
    -   Determines total points and maximum starting attribute/skill levels (e.g., Mundane, Skilled, Exceptional, Heroic). Set by GM.

### Aeonisk Specific
-   **Origin:**
    -   Choice of Faction or Background, granting an attribute bonus and a special trait.
    -   Options:
        -   **Sovereign_Nexus:** { bonus: [Willpower, Intelligence], trait: "Indoctrinated: +2 resist ritual disruption/mental influence" }
        -   **Astral_Commerce_Group:** { bonus: [Intelligence, Empathy], trait: "Contract-Bound: Start +1 SC or minor contract owed TO you" }
        -   **Pantheon_Security:** { bonus: [Strength, Agility], trait: "Tactical Protocol: Auto-succeed 1 Initiative roll per combat" }
        -   **Aether_Dynamics:** { bonus: [Empathy, Perception], trait: "Ley Sense: Sense nearby ley lines" }
        -   **Arcane_Genetics:** { bonus: [Health, Dexterity], trait: "Bio-Stabilized: +2 resist bio-Void effects/disease/mutation" }
        -   **Tempest_Industries:** { bonus: [Dexterity, Perception], trait: "Disruptor: +2 bonus sabotage rituals/encoded tech" }
        -   **Freeborn_Unbound:** { bonus: [Any], trait: "Wild Will: Max 1 Bond, sacrifice costly" }
-   **True_Will:**
    -   Character's metaphysical path/purpose. Starts undeclared, defined during play. Grants +1 to Willpower rolls if aligned, +3 Void if betrayed.
-   **Bonds:**
    -   Formal metaphysical connections (max 3, Freeborn 1). Formed via ritual/oath in-game. Provide mechanical benefits and narrative weight. Can be sacrificed.
-   **Void_Score:**
    -   Tracks spiritual corruption (0-10). Starts at 0. Gained via specific actions (skipping offerings, unethical rituals, Void tech). Has mechanical/narrative effects.
-   **Soulcredit:**
    -   Tracks spiritual reputation/trust (-10 to +10). Starts at 0. Influences faction relations, tech access. Gained/lost via fulfilling/breaking contracts/oaths.
-   **Ritual_Kit:**
    -   Starting characters define a Primary Ritual Item (personal, non-consumable) and 1-3 consumable Offerings appropriate to concept.
-   **Elemental_Currency:**
    -   Starting funds provided as charged elemental talismans (Grain, Drip, Spark, Breath) instead of abstract money. GM determines amount.
