# YAGS Conversion Improvements

This document outlines the improvements made to the YAGS DocBook to Markdown/EPUB conversion pipeline. The main goal was to fix table formatting issues in the converted Markdown files.

## Key Improvements

1. **Enhanced Lua Filter**: Improved the pandoc Lua filter to better handle DocBook tables
2. **Table Fixing Scripts**: Created specialized Python scripts to fix common table formatting issues
3. **Streamlined Conversion Process**: Updated the conversion script to include multiple post-processing steps

## Directory Structure

- `scripts/convert_yagsbook.sh` - Main conversion script
- `scripts/internal_podman_convert.sh` - Script that runs inside the container
- `scripts/table_fixes/` - Directory containing table fixing scripts:
  - `direct_table_fix.py` - Makes direct replacements for common tables
  - `final_fixes.py` - Fixes section numbering and additional table issues
  - `fix_duplicates.py` - Removes duplicate table sections
  - `fix_table_formatting.py` - Cleans up remaining table formatting issues
- `scripts/cleanup_backups.sh` - Script to clean up backup files
- `scripts/debug_ast.lua` - Lua script for debugging pandoc's AST
- `Podmanfile` - Container definition
- `Makefile` - Build system configuration

## How to Use

### Converting YAGS Files

To convert a single YAGS file:

```bash
./scripts/convert_yagsbook.sh path/to/file.yags
```

To convert all configured YAGS files:

```bash
make convert_yags
```

### Converting Markdown Files to PDF/EPUB

To convert markdown files in the content directory:

```bash
make convert_markdown
```

### Building the Container

To rebuild the container after changes:

```bash
make build_podman_image
```

### Cleaning Up

To clean up generated files:

```bash
make clean
```

To clean up backup files created during conversion:

```bash
make clean_backups
```

Or run the cleanup script directly:

```bash
./scripts/cleanup_backups.sh
```

## Table Fixing Process

The conversion process now includes multiple steps to fix table formatting:

1. **Pandoc Conversion**: Initial conversion with the Lua filter
2. **Direct Table Fixes**: Pattern-based replacements for known tables
3. **Section Numbering Fixes**: Ensures consistent section numbering
4. **Duplicate Removal**: Removes duplicate table entries that may occur
5. **Final Formatting**: Cleans up any remaining formatting issues

## Further Improvements

Potential areas for future improvements:

1. Add support for more complex table structures
2. Improve handling of nested lists
3. Better support for images and figures
4. Enhance cross-reference handling
