#!/usr/bin/env python3
"""
Final table formatting cleanup script for YAGS markdown files.
Fixes remaining issues with table headers and cell formatting.
"""

import re
import sys
import os

def fix_table_formatting(file_path):
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Make a backup
    backup_path = file_path + '.bak_formatting'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Created backup at {backup_path}")
    
    # Fix weird ||| markers
    content = re.sub(r'\|\|\|', '|', content)
    
    # Fix extra cell markers in Roll/Level of Success table
    content = re.sub(r'(\| Roll \| Level of Success \|)\n\|\|\|', r'\1', content)
    
    # Fix extra cell markers in Size/Mass and examples table
    content = re.sub(r'(\| Size \| Mass and examples \|)\n\|\|\|', r'\1', content)
    
    # Fix extra cell markers in Size/Vehicle examples table
    content = re.sub(r'(\| Size \| Vehicle examples \|)\n\|\|\|', r'\1', content)
    
    # Fix extra cell markers in Type of Task/TN table
    content = re.sub(r'(\| Type of Task \| TN [^|]*\|)\-\|\-\|', r'\1', content)
    
    # Fix extra cell markers in Athletics table
    content = re.sub(r'(\| Action \| Distance/round\-\|)\-\-\-\|', r'\1', content)
    
    # Fix extra cell markers in Encumbrance table
    content = re.sub(r'(\| Effects \| Load \|)\|\|', r'\1', content)
    
    # Fix weird hyphens and broken table headers
    content = re.sub(r'\|\-\-\-\-\|', '|', content)
    content = re.sub(r'\-\|\-\|', '|', content)
    content = re.sub(r'\-\|\-\-\-\|', '|', content)
    
    # Fix remaining broken tables
    content = re.sub(r'(\| Roll \| Level of Success \|)\n\|\|', r'\1', content)
    content = re.sub(r'(\| Target \| Example\-\|)\-\-\-\|', r'\1', content)
    content = re.sub(r'(\| Target \| Obstruction\-\|)\-\|', r'\1', content)
    content = re.sub(r'(\| Target \| Surface being climbed\-\|)\-\-\-\|', r'\1', content)
    content = re.sub(r'(\| Bonus \| Situation\|)\-\-\-\-\-\|', r'\1', content)
    content = re.sub(r'(\| Target \| Reaction\-\|)\-\-\-\-\|', r'\1', content)
    content = re.sub(r'(\| Modifier \| Situation \|)\-\-\-\-\-\|', r'\1', content)
    
    # Normalize table headers
    content = re.sub(r'\| Roll \| Level of Success \|\n\|\|\|', '| Roll | Level of Success |\n|------|------------------|', content)
    content = re.sub(r'\| Score \| Attribute\|\-\-\-\-\|', '| Score | Attribute |\n|-------|----------|', content)
    content = re.sub(r'\| Type of Task \| TN \-\-\-\-\|\-\|', '| Type of Task | TN |\n|-------------|-------|', content)
    content = re.sub(r'\| Size \| Mass and examples \|\n\|\|\|', '| Size | Mass and examples |\n|------|------------------|', content)
    content = re.sub(r'\| Size \| Vehicle examples \|\n\|\|\|', '| Size | Vehicle examples |\n|------|------------------|', content)
    content = re.sub(r'\| Action \| Distance/round\-\|\-\-\-\|', '| Action | Distance/round |\n|--------|---------------|', content)
    content = re.sub(r'\| Target \| Obstruction\-\|\-\|', '| Target | Obstruction |\n|--------|-------------|', content)
    content = re.sub(r'\| Target \| Surface being climbed\-\|\-\-\-\|', '| Target | Surface being climbed |\n|--------|---------------------|', content)
    content = re.sub(r'\| Target \| Example\-\|\-\-\-\|', '| Target | Example |\n|--------|---------|', content)
    content = re.sub(r'\| Modifier \| Situation \|\-\-\-\-\-\|', '| Modifier | Situation |\n|---------|-----------|', content)
    content = re.sub(r'\| Target \| Reaction\-\|\-\-\-\-\|', '| Target | Reaction |\n|--------|----------|', content)
    content = re.sub(r'\| Bonus \| Situation\|\-\-\-\-\-\|', '| Bonus | Situation |\n|-------|-----------|', content)
    content = re.sub(r'\| Effects \| Load \|\|\|', '| Effects | Load |\n|---------|------|', content)
    
    # Remove duplicate table content sections
    content = re.sub(r'(\| Unencumbered \| A character carrying up to their Strength is considered to be completely unencumbered, and never suffers penalties\. \|.*?)\|\|\n\| Unencumbered \| A character carrying up to their Strength is considered to be completely\nunencumbered, and never suffers penalties\.', r'\1', content, flags=re.DOTALL)
    
    # Write the fixed content back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed table formatting in {file_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = "converted_yagsbook/markdown/core.md"
    
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        sys.exit(1)
    
    fix_table_formatting(file_path)
    print("Done!")
