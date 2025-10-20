#!/usr/bin/env python3
"""
Fix duplicate tables and other formatting issues in the final document
"""

import re
import sys
import os

def fix_file(file_path):
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Make a backup
    backup_path = file_path + '.bak_duplicates'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Created backup at {backup_path}")
    
    # Fix duplicate Task/TN table
    task_tn_pattern = r'(\| Type of Task \| TN \|.*?Absurd \| 100 \(\+80\) \|)\n*\|\| Type of Task \| TN \|.*?Absurd \| 100 \(\+80\) \|'
    content = re.sub(task_tn_pattern, r'\1', content, flags=re.DOTALL)
    
    # Fix duplicate encumbrance table
    encumbrance_pattern = r'(\| Effects \| Load \|.*?Over encumbered \| Character cannot move, all agility checks are automatically zero and -2 to dexterity\. \|)\n*\|\| Effects \| Load \|.*?Over encumbered \| Character cannot move, all agility checks are automatically zero and -2 to dexterity\. \|.*?\|'
    content = re.sub(encumbrance_pattern, r'\1', content, flags=re.DOTALL)
    
    # Fix duplicate Athletics Running table
    running_pattern = r'(\| Target \| Obstruction \|.*?\| \+5 \| If any of the other modifiers apply, and it is windy, add a further \+5\. \|)\n*\|\| Target \| Obstruction \|.*?\| \+5 \| If any of the other modifiers apply, and it is windy, add a further \+5\. \|.*?\|'
    content = re.sub(running_pattern, r'\1', content, flags=re.DOTALL)
    
    # Fix duplicate Awareness table
    awareness_pattern = r'(\| Target \| Example \|.*?\| 30 \| Subtle clues that require attention to detail\. \|)\n*\|-\| Target \| Example \|.*?\| 30 \| Subtle clues that require attention to detail\. \|.*?\|'
    content = re.sub(awareness_pattern, r'\1', content, flags=re.DOTALL)
    
    # Fix duplicate Charm table
    charm_pattern = r'(\| Target \| Reaction \|.*?\| 60\+ \| You have the person eating out of your hand\. They will do anything for you\. A few evenings\. \|)\n*\|\| Target \| Reaction \|.*?\| 60\+ \| You have the person eating out of your hand\. They will do anything for you\. A few evenings\. \|.*?\|'
    content = re.sub(charm_pattern, r'\1', content, flags=re.DOTALL)
    
    # Fix duplicate Sleight table
    sleight_pattern = r'(\| Bonus \| Situation \|.*?\| -10 \| Obvious\. \|)\n*\|-\| Bonus \| Situation \|.*?\| -10 \| Obvious\. \|.*?\|'
    content = re.sub(sleight_pattern, r'\1', content, flags=re.DOTALL)
    
    # Fix any hanging vertical bars
    content = re.sub(r'\|\n\|---------|------|', '', content)
    content = re.sub(r'\|\n\|--------|----------|', '', content)
    content = re.sub(r' \|\n\|-', '', content)
    
    # Write the fixed content back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed duplicate tables in {file_path}")

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
