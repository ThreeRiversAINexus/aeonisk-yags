#!/bin/bash
# Script to clean up interim development files after branch finalization

echo "Cleaning up interim development files..."

# List of files to remove
FILES_TO_REMOVE=(
  "scripts/clean_tables.py"
  "scripts/comprehensive_table_fix.py"
  "scripts/convert_yagsbook_improved.sh"
  "scripts/final_cleanup.py"
  "scripts/final_table_fixes.py"
  "scripts/fix_tables.py"
  "scripts/fix_tables.sh"
  "scripts/internal_podman_convert_improved.sh"
  "scripts/preprocess_yags.lua"
  "scripts/preprocess_yags.py"
  "scripts/yags_tables_improved.lua"
  "Makefile.improved"
  "Podmanfile.improved"
)

# Remove each file
for file in "${FILES_TO_REMOVE[@]}"; do
  if [ -f "$file" ]; then
    rm "$file"
    echo "Removed: $file"
  else
    echo "Not found: $file"
  fi
done

echo "Cleanup complete."
echo ""
echo "The following files have been kept:"
echo "- scripts/convert_yagsbook.sh (updated version)"
echo "- scripts/internal_podman_convert.sh (updated version)"
echo "- scripts/table_fixes/* (directory with table fixing scripts)"
echo "- scripts/debug_ast.lua"
echo "- Makefile (updated version)"
echo "- Podmanfile (updated version)"
