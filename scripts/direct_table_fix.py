#!/usr/bin/env python3
"""
Direct table fixing script for YAGS conversions
This script makes direct replacements of known table patterns in the core.md file
"""

import re
import sys

def fix_tables(file_path):
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Make a backup
    with open(file_path + '.bak', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Fix "Roll / Level of Success" table
    content = re.sub(
        r'Roll\s*\n\s*Level of Success\s*\n\s*success\.\s*\n\s*success\.\s*\n\s*success\.\s*\n\s*success\.\s*\n\s*success\.',
        """| Roll | Level of Success |
|------|------------------|
| TN + 0 | Moderate success. |
| TN + 10 | Good success. |
| TN + 20 | Excellent success. |
| TN + 30 | Superb success. |
| TN + 40 | Fantastic success. |""",
        content
    )
    
    # Fix "Score / Attribute" table
    content = re.sub(
        r'Score\s*\n\s*Attribute\s*\n\s*You have no rateable.*?Beyond what is naturally possible\.',
        """| Score | Attribute |
|-------|----------|
| 0 | None. You have no rateable ability in this attribute, and may not attempt skills which use it. |
| 1 | Crippled. You are crippled, being either very dumb, seriously ill or socially inept. |
| 2 | Poor. You are noticeably below average, being in the bottom 10% of the population. This is normally the minimum level of attribute it is possible to have. |
| 3 | Average. You are average, among the middle 80% of the population. |
| 4 | High. You are noticeably above average in ability, being in the top 10% of the population. |
| 5 | Very high. You are highly adept at tasks related to this attribute. This is about the highest that people will have naturally, without training. |
| 6 | Exceptional. You are truly exceptional, and have trained hard to develop your attribute this high. Most people will find it very hard to compete against you. |
| 7 | Incredible. You are one of a small number of people in your country. |
| 8 | Legendary. The normal maximum for humans. There may be a handful of people with an attribute this high in the modern world. |
| 9+ | Superhuman. Beyond what is naturally possible. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Type of Task / TN" table
    content = re.sub(
        r'Type of Task\s*\n\s*TN\s*\n\s*Such a task can be achieved.*?Above average attributes are required to have even a chance of success\.',
        """| Type of Task | TN |
|-------------|-------|
| Very easy. Such a task can be achieved by a person with little or no skill with a good chance of success. A professional will always succeed. | 10 (-10) |
| Easy. Anyone with a small amount of skill will be able to achieve this with a good chance of success, though it will be difficult for someone without any training at all. | 15 (-5) |
| Moderate. Such tasks can be achieved without difficulty by a professional in ideal conditions. Those without proper training can find it difficult however. | 20 (+0) |
| Challenging. People with less than professional level of skill will find it hard to succeed, and it is out of league of someone with only basic familiarity. | 25 (+5) |
| Difficult. Such tasks require a highly skilled person. Anyone with less than professional competence will always fail, and even professionals will be hard pressed. | 30 (+10) |
| Very difficult. A master of the skill can achieve such tasks with confidence, others will fail. About the highest level of difficulty under normal circumstances. | 40 (+20) |
| Extreme. A very difficult task under poor conditions. | 50 (+30) |
| Heroic. Truly heroic. | 60 (+40) |
| Sheer folly. Someone with superhuman level of skill will be hard pressed to achieve this difficulty. | 75 (+55) |
| Absurd. Well beyond what most people could achieve. Above average attributes are required to have even a chance of success. | 100 (+80) |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Size / Mass and examples" table
    content = re.sub(
        r'Size\s*\n\s*Mass and examples\s*\n\s*A large house cat\..*?Blue whale\.',
        """| Size | Mass and examples |
|------|------------------|
| 0 | 7kg. A large house cat. |
| 1 | 11kg. 1 year old child, a small dog (e.g., a beagle). |
| 2 | 18kg. 5 year old child. |
| 3 | 28kg. 10 year old child, a medium dog (e.g., a boxer). |
| 4 | 44kg. Small adult, lightweight woman, a wolf. |
| 5 | 70kg. Typical adult. This size constitutes most of the adult human population. Anyone outside of this average is very noticeably large or small. |
| 6 | 111kg. Heavyweight boxer, stereotypical barbarian warrior. |
| 7 | 176kg. Donkey, black bear. |
| 8 | 279kg. Lion. |
| 9 | 442kg. Riding horse, grizzly bear. |
| 10 | 700kg. War horse, prehistoric cave bear. Also, a family car. |
| 11 | 1.1t. Rhino. Also, an SUV or small tank. |
| 12 | 1.8t. Great white shark, anything up to about 2 tonnes in mass. Also, a typical tank. |
| 13 | 2.8t. |
| 14 | 4.4t. Triceratops. Also, a large tank. |
| 15 | 7t. Elephant. |
| 16 | 11t. |
| 17 | 17t. |
| 18 | 28t. Apatosaurus. The largest land animals known. |
| 19 | 44t. |
| 20 | 70t. |
| 21 | 110t. Blue whale. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Size / Vehicle examples" table
    content = re.sub(
        r'Size\s*\n\s*Vehicle examples',
        """| Size | Vehicle examples |
|------|------------------|
| 5 | Motorbike. |
| 10 | Family car. |
| 16 | Train carriage. |
| 17 | F-16 fighter. |
| 22 | Free Trader (Traveller). |
| 26 | Boeing 747. |
| 28 | Bismark. |
| 32 | USS Enterprise CVN-65. |
| 44 | Star Destroyer (Star Wars). |
| 80 | Death Star (Star Wars). |
| 94 | Skylark of Valeron (EE Doc Smith). |
| 110 | Earth |""",
        content
    )
    
    # Fix "Action / Distance/round" table
    content = re.sub(
        r'Action\s*\n\s*Distance/round',
        """| Action | Distance/round |
|--------|---------------|
| Careful (x1/2) | 1/2 MOVE |
| Standard | MOVE |
| Running (x2) | MOVE x 2 |
| Sprinting (x3) | MOVE x 2 + Athletics |""",
        content
    )
    
    # Fix "Target / Obstruction" table in Athletics Running section
    content = re.sub(
        r'Target\s*\n\s*Obstruction\s*\n\s*No obstructions.*?If you need to jump gaps between roof tops, then this counts as extra obstructions\.',
        """| Target | Obstruction |
|--------|-------------|
| 0 | No obstructions, a completely clear path. |
| 5 | A typical lightly crowded street, or through a wood. Running is easy, unless you fumble and trip up. |
| 10 | A busy street, a warehouse full of crates, across rubble or through dense woods. |
| 15 | A busy market, or through thick foliage. |
| +5 | Unstable footing, such as rubble, crumbling rock or swaying rigging. |
| +5 | Narrow or uneven footing, such as a narrow ledge or ground with many holes or cracks. |
| +10 | Additionally to the other modifiers, if the surface is icy, oil covered or otherwise lacking in grip. |
| +5 | If any of the other modifiers apply, and it is windy, add a further +5. |

Racing across rooftops might count as light obstruction (5) to avoid chimneys and aerials, with +5 for unstable (roof tiles will likely break) and +5 for uneven footing, for a total of 15. This goes up to 30 if you run, 45 if you sprint. If you need to jump gaps between roof tops, then this counts as extra obstructions.""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Target / Obstruction" table in Athletics Climbing section
    content = re.sub(
        r'Target\s*\n\s*Obstruction\s*\n\s*Get onto or over a chair.*?To perform these actions as a full round action, halve the difficulties\.',
        """| Target | Obstruction |
|--------|-------------|
| 5 | Get onto or over a chair or bench. Getting under a table or similar shelter is also very easy. |
| 10 | Get onto a table or object of similar height. Climbing under and through a table, assuming there are no chairs in the way. |
| 15 | Climb/jump over a table or object of similar size. Also, climbing over a fence no higher than you are. |

On success, all of these can be performed as a standard movement action at no penalty during combat. Failure results in no or partial movement, and loss of further attacks and defences that round.

To perform these actions as a full round action, halve the difficulties.""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Target / Surface being climbed" table
    content = re.sub(
        r'Target\s*\n\s*Surface being climbed\s*\n\s*Ladders, very easy slope or tree.*?About the hardest naturally occurring climbs\.',
        """| Target | Surface being climbed |
|--------|---------------------|
| 5 | Ladders, very easy slope or tree. |
| 10 | Trees with plenty of branches, cliff with lots of ledges and handholds, scaffolding or similar structure. |
| 15 | Typical cliff, on to the roof of a modern detached house (via garage, drain pipes etc). |
| 20 | Smooth cliff or brick wall of a modern house. |
| 30 | About the hardest most cliffs will be in general, though they may have sections which are harder than this. |
| 40 | About the hardest naturally occurring climbs. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Target / Example" table in Awareness section
    content = re.sub(
        r'Target\s*\n\s*Example\s*\n\s*Notice something obvious.*?Something in plain sight, but not immediately obvious\. A torn note on a desk, a wet pair of shoes on someone who hasn\'t been outside\.',
        """| Target | Example |
|--------|---------|
| 10 | Notice something obvious, such as a knife laying next to a dead body. |
| 20 | Something in plain sight, but not immediately obvious. A torn note on a desk, a wet pair of shoes on someone who hasn't been outside. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Modifier / Situation" table in Awareness section
    content = re.sub(
        r'Modifier\s*\n\s*Situation\s*\n\s*Base TN to see a person.*?If the target is almost entirely hidden\.',
        """| Modifier | Situation |
|---------|-----------|
| 15 | Base TN to see a person who is standing in the open, making no attempt to hide themselves. |
| +5 | If the target is over 50m away, then increase the TN by +5. |
| +10 | If the target is 100m away or more, then increase the TN by +10. Each doubling (200m, 400m) adds a further +10. |
| -/+5 | Each point of size of the target above 5, reduce the TN by 5. If they are smaller, then increase the TN by 5 per point. |
| +10 | If the target is hidden in half cover. |
| +20 | If the target is almost entirely hidden. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Target / Reaction" table in Charm section
    content = re.sub(
        r'Target\s*\n\s*Reaction\s*\n\s*You manage to annoy.*?You have the person eating out of your hand\. They will do anything for you\. A few evenings\.',
        """| Target | Reaction |
|--------|----------|
| <10 | You manage to annoy or upset the person such that they dislike you. They are unlikely to help you, and may hinder you depending on their personality. |
| 10-19 | You haven't upset them, but you haven't impressed them either. Whether they help or hinder you will depend on their personality. |
| 20-29 | You made a good impression, and the person has had their opinion of you improved. They will probably be willing to help you, or spend time in your company, as long as it doesn't cost them too much. |
| 30-39 | You have really impressed them, and they will make an effort to aid you, or to keep you happy. It requires a few minutes of chat for someone to be Impressed by you. |
| 40-49 | They are taken with you, and will go out of their way to try and help you, even if it involves effort on their part. This requires up to an hour of your time to awe someone like this. |
| 50-59 | You have made a deep connection with the person, and they will try their best to impress you and make sure that you return their affection. An evening. |
| 60+ | You have the person eating out of your hand. They will do anything for you. A few evenings. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Bonus / Situation" table in Sleight section
    content = re.sub(
        r'Bonus\s*\n\s*Situation\s*\n\s*A busy and crowded environment.*?A crowded street, full of distractions but where physical contact between people is fleeting\.',
        """| Bonus | Situation |
|-------|-----------|
| +10 | A busy and crowded environment, such as the tube during rush hour or around a busy market stand. |
| +5 | A crowded street, full of distractions but where physical contact between people is fleeting. |""",
        content,
        flags=re.DOTALL
    )
    
    # Fix "Effects / Load" table in Encumbrance section
    content = re.sub(
        r'Effects\s*\n\s*Load\s*\n\s*A character carrying up to their Strength.*?Character cannot move, all agility checks are automatically zero and -2 to dexterity\.',
        """| Effects | Load |
|---------|------|
| Unencumbered | A character carrying up to their Strength is considered to be completely unencumbered, and never suffers penalties. |
| Lightly Encumbered | A character carrying more than their Strength, is lightly encumbered. They are only at penalties in certain weight critical situations (such as swimming). |
| Encumbered | A character carrying up to twice the square of their Strength is at -1 to Agility. They are also unable to sprint. |
| Heavily Encumbered | The character has a -2 penalty to Agility, -1 to Dexterity, and cannot run or sprint. Their base movement is halved. |
| Greatly Encumbered | A greatly encumbered character suffers a -4 penalty to Agility and -2 to Dexterity, and cannot run or sprint. Their base movement is halved. |
| Over Encumbered | Character cannot move, all agility checks are automatically zero and -2 to dexterity. |""",
        content,
        flags=re.DOTALL
    )
    
    # Write the fixed content back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Direct table fixes applied to {file_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = "archive/converted_yagsbook/markdown/core.md"
    
    fix_tables(file_path)
