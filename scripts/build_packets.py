#!/usr/bin/env python3
"""Assemble the two distributable Aeonisk packets from canon in content/.

Two audiences, two shapes, one source of truth:

  aeonisk-<version>-packet.zip   The itch.io download. The system prompt sits
                                 at the root; ai/ holds every book as flat
                                 markdown to paste or upload; humans/ holds the
                                 same books typeset as PDFs.
  aeonisk-<version>-ai-pack.zip  Flat content/ plus dm_prompt.md -- the legacy
                                 shape for a chat-hosted DM.

Both are build artifacts. Every document in them is a byte-for-byte copy of a
file under content/ -- edit the source, never the packet.

    python scripts/build_packets.py              # build both zips
    python scripts/build_packets.py --pdf        # also render humans/ PDFs
                                                 # (needs pandoc and xelatex)
    python scripts/build_packets.py --check      # verify nothing is stale
"""

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASES = REPO_ROOT / "releases"
STAGING = RELEASES / "_staging"
PANDOC_DIR = REPO_ROOT / "scripts" / "pandoc"
PRINT_FILTER = PANDOC_DIR / "aeonisk_print.lua"
TABLE_HEADER = PANDOC_DIR / "aeonisk-tables.tex"

VERSION = "1.4.0"

# ---------------------------------------------------------------------------
# ai/ -- flat markdown, nothing nested. Chat uploads have no directory
# structure, and a person pasting files should not have to hunt through
# folders. Names are kept exactly as canon spells them so the DM prompt's
# references ("Start by reading AEONISK_PRIMER.md") still resolve.
# ---------------------------------------------------------------------------
AI_FLAT = [
    "content/AEONISK_PRIMER.md",
    "content/Aeonisk - System Neutral Lore - v1.4.0.md",
    "content/Aeonisk - YAGS Module - v1.4.0.md",
    "content/supplemental/NEXUS_LAW.md",
    "content/supplemental/FACTION_REFERENCE.md",
    "content/supplemental/LINES_REFERENCE.md",
    "content/Aeonisk - Economy & Money-Making Guide - v1.4.0.md",
    "content/Aeonisk - Gear & Tech Reference - v1.4.0.md",
    "content/Sovereign Nexus Culinary Guide.md",
    "content/experimental/Aeonisk - Tactical Module - v1.4.0.md",
    "content/aeonisk-charsheet.txt",
]

# ---------------------------------------------------------------------------
# humans/ -- the same books, typeset. Grouped start-here / core / reference so
# a reader meets them in the order that makes sense.
#
# Each entry: (source, destination stem under humans/, page orientation)
#
# Orientation is not decoration. Canon has table rows up to 331 characters;
# at portrait width the reference tables wrap every cell and break headers
# mid-word. Prose-heavy books stay portrait because landscape prose reads
# badly; the four table-driven references go landscape.
# ---------------------------------------------------------------------------
PORTRAIT, LANDSCAPE = "portrait", "landscape"

HUMAN_LAYOUT = [
    ("packaging/start-here.md", "start-here/Start Here", PORTRAIT),
    ("content/AEONISK_PRIMER.md", "start-here/Primer", PORTRAIT),
    ("content/Aeonisk - System Neutral Lore - v1.4.0.md", "core/Aeonisk - The Setting", PORTRAIT),
    ("content/Aeonisk - YAGS Module - v1.4.0.md", "core/Aeonisk - The Rules", PORTRAIT),
    ("content/supplemental/NEXUS_LAW.md", "reference/The Sovereign Nexus Constitution", PORTRAIT),
    ("content/supplemental/FACTION_REFERENCE.md", "reference/Factions", PORTRAIT),
    ("content/supplemental/LINES_REFERENCE.md", "reference/Lines", PORTRAIT),
    ("content/Aeonisk - Economy & Money-Making Guide - v1.4.0.md", "reference/Economy", LANDSCAPE),
    ("content/Aeonisk - Gear & Tech Reference - v1.4.0.md", "reference/Gear & Tech", LANDSCAPE),
    ("content/Sovereign Nexus Culinary Guide.md", "reference/Culinary Guide", LANDSCAPE),
    (
        "content/experimental/Aeonisk - Tactical Module - v1.4.0.md",
        "reference/Tactical Module (playtest)",
        LANDSCAPE,
    ),
]

# Files that sit at the root of the packet.
ROOT_FILES = [
    ("ai_pack/dm_prompt.md", "AEONISK_SYSTEM_PROMPT.md"),
    ("packaging/start-here.md", "README.md"),
    ("LICENSE", "LICENSE-AEONISK.md"),
    ("content/experimental/LICENSE", "LICENSE-YAGS.md"),
]

# The character sheet is YAML to be edited, not read. It ships beside the
# reference PDFs as-is rather than being typeset.
HUMAN_VERBATIM = [("content/aeonisk-charsheet.txt", "reference/aeonisk-charsheet.txt")]

AI_PACK_DIR = REPO_ROOT / "ai_pack"


def stage_packet() -> Path:
    root = STAGING / f"aeonisk-{VERSION}"
    if root.exists():
        shutil.rmtree(root)

    def place(src_rel: str, dst_rel: str) -> None:
        src = REPO_ROOT / src_rel
        if not src.exists():
            raise SystemExit(f"missing source document: {src_rel}")
        dst = root / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for src_rel, dst_name in ROOT_FILES:
        place(src_rel, dst_name)
    for src_rel in AI_FLAT:
        place(src_rel, f"ai/{Path(src_rel).name}")
    for src_rel, dst_rel in HUMAN_VERBATIM:
        place(src_rel, f"humans/{dst_rel}")
    return root


def render_pdfs(root: Path) -> None:
    """Typeset humans/ from canon.

    The print filter and the DejaVu fonts are both load-bearing: without them
    xelatex silently drops the status marks in the Constitution and the
    correct/wrong pairs in the Faction reference. See aeonisk_print.lua.
    """
    for src_rel, dst_stem, orientation in HUMAN_LAYOUT:
        src = REPO_ROOT / src_rel
        out = root / "humans" / f"{dst_stem}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)

        geometry = ["-V", "geometry:margin=0.85in"]
        if orientation == LANDSCAPE:
            geometry = ["-V", "geometry:landscape", "-V", "geometry:margin=0.7in"]

        cmd = [
            "pandoc",
            "--pdf-engine=xelatex",
            f"--lua-filter={PRINT_FILTER}",
            "-H", str(TABLE_HEADER),
            "-V", "mainfont=DejaVu Sans",
            "-V", "monofont=DejaVu Sans Mono",
            "-V", "fontsize=10pt",
            "-V", "colorlinks=true",
            "-V", "linkcolor=black",
            *geometry,
            "--toc", "--toc-depth=2",
            str(src),
            "-o", str(out),
        ]
        print(f"  pdf ({orientation[:4]}): {dst_stem}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"pandoc failed on {src_rel}:\n{result.stderr[-2000:]}")
        missing = [ln for ln in result.stderr.splitlines() if "Missing character" in ln]
        if missing:
            raise SystemExit(
                f"{dst_stem}: xelatex dropped {len(missing)} character(s); the PDF "
                f"would be silently lossy. First: {missing[0]}"
            )


def write_zip(zip_path: Path, root: Path, arc_prefix: str) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f"{arc_prefix}/{path.relative_to(root)}")
    size = zip_path.stat().st_size // 1024
    print(f"  {zip_path.relative_to(REPO_ROOT)}  ({len(files)} files, {size} KiB)")


def check() -> int:
    """Verify the shipped zips match canon. Non-zero if stale."""
    problems = []
    packet = RELEASES / f"aeonisk-{VERSION}-packet.zip"
    ai_zip = RELEASES / f"aeonisk-{VERSION}-ai-pack.zip"

    for zp in (packet, ai_zip):
        if not zp.exists():
            problems.append(f"{zp.name} has not been built")

    if packet.exists():
        expected = [(s, d) for s, d in ROOT_FILES]
        expected += [(s, f"ai/{Path(s).name}") for s in AI_FLAT]
        expected += [(s, f"humans/{d}") for s, d in HUMAN_VERBATIM]
        with zipfile.ZipFile(packet) as zf:
            names = set(zf.namelist())
            for src_rel, dst_rel in expected:
                arc = f"aeonisk-{VERSION}/{dst_rel}"
                if arc not in names:
                    problems.append(f"{packet.name}: missing {dst_rel}")
                elif zf.read(arc) != (REPO_ROOT / src_rel).read_bytes():
                    problems.append(f"{packet.name}: {dst_rel} differs from {src_rel}")

    if ai_zip.exists():
        with zipfile.ZipFile(ai_zip) as zf:
            names = set(zf.namelist())
            for src in sorted(AI_PACK_DIR.rglob("*")):
                if not src.is_file():
                    continue
                arc = f"ai_pack/{src.relative_to(AI_PACK_DIR)}"
                if arc not in names:
                    problems.append(f"{ai_zip.name}: missing {arc}")
                elif zf.read(arc) != src.read_bytes():
                    problems.append(f"{ai_zip.name}: {arc} differs from ai_pack/")

    if problems:
        for p in problems:
            print(f"STALE: {p}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s). Run: make packets", file=sys.stderr)
        return 1
    print(f"packets are in sync (v{VERSION})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pdf", action="store_true", help="also typeset humans/")
    parser.add_argument("--check", action="store_true", help="verify built zips match canon")
    args = parser.parse_args()

    if args.check:
        return check()

    verify = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_ai_pack.py"), "--check"],
        capture_output=True, text=True,
    )
    if verify.returncode != 0:
        print(verify.stdout + verify.stderr, file=sys.stderr)
        print("ai_pack/ is stale; run python scripts/build_ai_pack.py first", file=sys.stderr)
        return 1

    print(f"Building Aeonisk v{VERSION} packets...")
    RELEASES.mkdir(exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)

    root = stage_packet()
    if args.pdf:
        render_pdfs(root)
    else:
        print("  (no --pdf: humans/ will contain only the character sheet)")
    write_zip(RELEASES / f"aeonisk-{VERSION}-packet.zip", root, f"aeonisk-{VERSION}")
    write_zip(RELEASES / f"aeonisk-{VERSION}-ai-pack.zip", AI_PACK_DIR, "ai_pack")

    shutil.rmtree(STAGING)
    print("Done. Upload to itch.io; listing copy is in packaging/itch-page.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
