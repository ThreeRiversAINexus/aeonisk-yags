#!/usr/bin/env python3
"""
Final cleanup script for tables in core.md
Fixes the remaining table issues and section numbering
"""

import re
import sys
import os

def fix_file(file_path):
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Make a backup
    backup_path = file_path + '.bak_final'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Created backup at {backup_path}")
    
    # Fix section numbering (replace the mess with proper headers)
    content = re.sub(r'# 5\. 4\. 3\. 2\. 1\. What is YAGS\?', '# 1. What is YAGS?', content)
    content = re.sub(r'# The Core Mechanics', '# 2. The Core Mechanics', content)
    content = re.sub(r'# Characteristics', '# 3. Characteristics', content)
    content = re.sub(r'# Core Skills', '# 4. Core Skills', content)
    content = re.sub(r'# Genres and Settings', '# 5. Genres and Settings', content)
    content = re.sub(r'# GNU GENERAL PUBLIC LICENSE', '# 6. GNU GENERAL PUBLIC LICENSE', content)
    
    # Fix "Type of Task / TN" table 
    type_task_table = """| Type of Task | TN |
|-------------|-------|
| Very easy | 10 (-10) |
| Easy | 15 (-5) |
| Moderate | 20 (+0) |
| Challenging | 25 (+5) |
| Difficult | 30 (+10) |
| Very difficult | 40 (+20) |
| Extreme | 50 (+30) |
| Heroic | 60 (+40) |
| Sheer folly | 75 (+55) |
| Absurd | 100 (+80) |
"""
    content = re.sub(
        r'\| Type of Task \| TN \|\n\|-------------|-------\|\n\| Very easy.*?chance of success\.',
        type_task_table,
        content,
        flags=re.DOTALL
    )
    
    # Fix Charm table
    charm_table = """| Target | Reaction |
|--------|----------|
| <10 | You manage to annoy or upset the person such that they dislike you. They are unlikely to help you, and may hinder you depending on their personality. |
| 10-19 | You haven't upset them, but you haven't impressed them either. Whether they help or hinder you will depend on their personality. |
| 20-29 | You made a good impression, and the person has had their opinion of you improved. They will probably be willing to help you, or spend time in your company, as long as it doesn't cost them too much. |
| 30-39 | You have really impressed them, and they will make an effort to aid you, or to keep you happy. It requires a few minutes of chat for someone to be Impressed by you. |
| 40-49 | They are taken with you, and will go out of their way to try and help you, even if it involves effort on their part. This requires up to an hour of your time to awe someone like this. |
| 50-59 | You have made a deep connection with the person, and they will try their best to impress you and make sure that you return their affection. An evening. |
| 60+ | You have the person eating out of your hand. They will do anything for you. A few evenings. |
"""
    content = re.sub(
        r'\| Target \| Reaction \|\n\|--------|----------\|\n\| <10 \| You manage to annoy.*?A few evenings\.',
        charm_table,
        content,
        flags=re.DOTALL
    )
    
    # Fix Sleight table
    sleight_table = """| Bonus | Situation |
|-------|-----------|
| +10 | A busy and crowded environment, such as the tube during rush hour or around a busy market stand. |
| +5 | A crowded street, full of distractions but where physical contact between people is fleeting. |
| -5 | Empty street. |
| -10 | Obvious. |
"""
    content = re.sub(
        r'\| Bonus \| Situation \|\n\|-------|----------\|\n\| \+10 \| A busy and crowded environment.*?A crowded street, full of distractions but where physical contact between people is fleeting\.',
        sleight_table,
        content,
        flags=re.DOTALL
    )
    
    # Fix Encumbrance table
    encumbrance_table = """| Effects | Load |
|---------|------|
| Unencumbered | A character carrying up to their Strength is considered to be completely unencumbered, and never suffers penalties. |
| Lightly (0) | A character carrying more than their Strength, is lightly encumbered. They are only at penalties in certain weight critical situations (such as swimming). |
| Moderately (1) | A character carrying up to twice the square of their Strength is at -1 to Agility. They are also unable to sprint. |
| Heavily (2) | The character has a -2 penalty to Agility, -1 to Dexterity, and cannot run or sprint. Their base movement is halved. |
| Greatly (3) | A greatly encumbered character suffers a -4 penalty to Agility and -2 to Dexterity, and cannot run or sprint. Their base movement is halved. |
| Over encumbered | Character cannot move, all agility checks are automatically zero and -2 to dexterity. |
"""
    content = re.sub(
        r'\| Effects \| Load \|\n\|---------|------\|\n\| Unencumbered \| A character carrying up to their Strength.*?Character cannot move, all agility checks are automatically zero and -2 to dexterity\.',
        encumbrance_table,
        content,
        flags=re.DOTALL
    )
    
    # Fix Athletics Running Obstruction table
    running_table = """| Target | Obstruction |
|--------|-------------|
| 0 | No obstructions, a completely clear path. |
| 5 | A typical lightly crowded street, or through a wood. Running is easy, unless you fumble and trip up. |
| 10 | A busy street, a warehouse full of crates, across rubble or through dense woods. |
| 20 | A busy market, or through thick foliage. |
| +5/+10 | Unstable footing, such as rubble, crumbling rock or swaying rigging. |
| +5/+10 | Narrow or uneven footing, such as a narrow ledge or ground with many holes or cracks. |
| +5/+10 | Additionally to the other modifiers, if the surface is icy, oil covered or otherwise lacking in grip. |
| +5 | If any of the other modifiers apply, and it is windy, add a further +5. |
"""
    content = re.sub(
        r'\| Target \| Obstruction \|\n\|--------|-------------\|\n\| 0 \| No obstructions.*?If any of the other modifiers apply, and it is windy, add a further \+5\.',
        running_table,
        content,
        flags=re.DOTALL
    )
    
    # Fix Awareness Example table
    awareness_table = """| Target | Example |
|--------|---------|
| 10 | Notice something obvious, such as a knife laying next to a dead body. |
| 20 | Something in plain sight, but not immediately obvious. A torn note on a desk, a wet pair of shoes on someone who hasn't been outside. |
| 30 | Subtle clues that require attention to detail. |
"""
    content = re.sub(
        r'\| Target \| Example \|\n\|--------|--------\|\n\| 10 \| Notice something obvious.*?Something in plain sight, but not immediately obvious\. A torn note on a desk, a wet pair of shoes on someone who hasn\'t been outside\.',
        awareness_table,
        content,
        flags=re.DOTALL
    )
    
    # Fix any quote marks that might still be escaped
    content = content.replace("\\'", "'").replace('\\"', '"')
    
    # Write the fixed content back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Final fixes applied to {file_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = "converted_yagsbook/markdown/core.md"
    
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        sys.exit(1)
    
    fix_file(file_path)
    print("Done!")
