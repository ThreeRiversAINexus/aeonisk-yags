# Archive Directory

This directory contains legacy content and reference materials that have been moved out of the active development paths.

## Contents

### ai_pack/
Legacy AI training pack containing duplicate copies of:
- Aeonisk module documentation (YAGS rules, gear/tech reference, system-neutral lore)
- Dataset guidelines and normalized YAML exports
- Character sheets and glossaries
- Core YAGS rules modules (bestiary, character, combat, core, hightech, scifitech)

**Note:** The canonical versions of these materials are now maintained in:
- `datasets/` - For dataset specifications and training data
- `content/` - For active game content and documentation
- `converted_yagsbook/` - For YAGS rulebook reference

### releases/
Published PDF and EPUB releases of Aeonisk materials (versions 1.2.0-1.2.1):
- Gear & Tech Reference
- Lore Book
- Tactical Module
- YAGS Module

These are archival releases. Current development content is in the `content/` directory.

## Why These Were Archived

These directories contained duplicated content that was:
1. Already present in the active development paths (`datasets/`, `content/`)
2. Not referenced by the running code (backend API, frontend, or Python toolkit)
3. Serving as reference material rather than active dependencies

The archive preserves these materials for historical reference while keeping the main repository focused on active development.

## Restoration

If you need to restore any of these materials to active development:
```bash
git mv archive/<directory> ./
```
