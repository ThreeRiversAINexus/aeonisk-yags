#!/usr/bin/env python3
"""Rebuild ai_pack/content/ from the canonical documents in content/.

The pack is a distribution artifact: every file under ai_pack/content/ is a
verbatim copy of a file in content/. Editing the copy instead of the source is
how the pack drifted out of canon in the first place, so this script is the
only supported way to update it.

    python scripts/build_ai_pack.py            # rebuild
    python scripts/build_ai_pack.py --check    # verify, non-zero if stale
"""

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_CONTENT = REPO_ROOT / "ai_pack" / "content"

# Source documents, in the reading order the pack README presents them.
PACK_SOURCES = [
    "content/AEONISK_PRIMER.md",
    "content/Aeonisk - System Neutral Lore - v1.4.0.md",
    "content/Aeonisk - YAGS Module - v1.4.0.md",
    "content/supplemental/NEXUS_LAW.md",
    "content/supplemental/FACTION_REFERENCE.md",
    "content/supplemental/LINES_REFERENCE.md",
    "content/Aeonisk - Economy & Money-Making Guide - v1.4.0.md",
    "content/Aeonisk - Gear & Tech Reference - v1.4.0.md",
    "content/experimental/Aeonisk - Tactical Module - v1.4.0.md",
    "content/Sovereign Nexus Culinary Guide.md",
    "content/aeonisk-charsheet.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without writing; exit 1 if the pack is stale",
    )
    args = parser.parse_args()

    PACK_CONTENT.mkdir(parents=True, exist_ok=True)
    expected = set()
    stale = []

    for rel in PACK_SOURCES:
        source = REPO_ROOT / rel
        if not source.is_file():
            print(f"MISSING SOURCE: {rel}", file=sys.stderr)
            return 2
        target = PACK_CONTENT / source.name
        expected.add(source.name)

        if target.is_file() and filecmp.cmp(source, target, shallow=False):
            continue
        stale.append(source.name)
        if not args.check:
            shutil.copy2(source, target)

    orphans = sorted(p.name for p in PACK_CONTENT.iterdir() if p.name not in expected)
    for name in orphans:
        stale.append(f"{name} (not a pack source)")
        if not args.check:
            (PACK_CONTENT / name).unlink()

    if args.check:
        if stale:
            print("ai_pack is stale:")
            for name in stale:
                print(f"  - {name}")
            print("Run: python scripts/build_ai_pack.py")
            return 1
        print(f"ai_pack is in sync ({len(expected)} documents).")
        return 0

    if stale:
        print(f"Rebuilt ai_pack/content/ ({len(stale)} changed):")
        for name in stale:
            print(f"  - {name}")
    else:
        print(f"ai_pack already in sync ({len(expected)} documents).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
