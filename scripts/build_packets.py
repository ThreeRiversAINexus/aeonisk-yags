#!/usr/bin/env python3
"""Assemble the two distributable Aeonisk packets from canon in content/.

Two audiences, two shapes, one source of truth:

  aeonisk-<version>-packet.zip   Foldered and ordered for a person. Carries the
                                 DM system prompt too, so one download is
                                 enough to start an AI-run session.
  aeonisk-<version>-ai-pack.zip  Flat content/ plus dm_prompt.md, the shape a
                                 chat-hosted DM wants: upload, paste, play.

Both are build artifacts. Every document in them is a byte-for-byte copy of a
file under content/ -- edit the source, never the packet.

    python scripts/build_packets.py              # build both zips
    python scripts/build_packets.py --pdf        # also render PDFs into the
                                                 # human packet (needs pandoc
                                                 # and xelatex)
    python scripts/build_packets.py --check      # verify nothing is stale
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASES = REPO_ROOT / "releases"
STAGING = RELEASES / "_staging"
PANDOC_FILTER = REPO_ROOT / "scripts" / "pandoc" / "aeonisk_print.lua"

VERSION = "1.4.0"

# Human packet: numbered directories so the reading order survives a file
# manager that sorts alphabetically. (source, destination-in-packet)
HUMAN_LAYOUT = [
    ("content/AEONISK_PRIMER.md", "01-start-here/AEONISK_PRIMER.md"),
    ("ai_pack/dm_prompt.md", "01-start-here/DM_SYSTEM_PROMPT.md"),
    ("content/Aeonisk - YAGS Module - v1.4.0.md", "02-rules/Aeonisk - YAGS Module - v1.4.0.md"),
    ("content/aeonisk-charsheet.txt", "02-rules/aeonisk-charsheet.txt"),
    (
        "content/experimental/Aeonisk - Tactical Module - v1.4.0.md",
        "02-rules/Aeonisk - Tactical Module - v1.4.0 (playtest).md",
    ),
    (
        "content/Aeonisk - System Neutral Lore - v1.4.0.md",
        "03-setting/Aeonisk - System Neutral Lore - v1.4.0.md",
    ),
    ("content/supplemental/NEXUS_LAW.md", "03-setting/NEXUS_LAW.md"),
    ("content/supplemental/FACTION_REFERENCE.md", "03-setting/FACTION_REFERENCE.md"),
    ("content/supplemental/LINES_REFERENCE.md", "03-setting/LINES_REFERENCE.md"),
    (
        "content/Aeonisk - Economy & Money-Making Guide - v1.4.0.md",
        "04-reference/Aeonisk - Economy & Money-Making Guide - v1.4.0.md",
    ),
    (
        "content/Aeonisk - Gear & Tech Reference - v1.4.0.md",
        "04-reference/Aeonisk - Gear & Tech Reference - v1.4.0.md",
    ),
    (
        "content/Sovereign Nexus Culinary Guide.md",
        "04-reference/Sovereign Nexus Culinary Guide.md",
    ),
    ("packaging/packet-README.md", "README.md"),
    ("LICENSE", "LICENSE-AEONISK.md"),
    ("content/experimental/LICENSE", "LICENSE-YAGS.md"),
]

# AI pack: ai_pack/ is already built and verified by build_ai_pack.py, so the
# zip is just that tree. Keeping it flat matters -- chat uploads have no
# directories, and the prompt refers to documents by bare filename.
AI_PACK_DIR = REPO_ROOT / "ai_pack"

# Documents worth rendering to PDF. The charsheet is YAML meant to be edited,
# and the licenses are boilerplate; neither earns a typeset page.
PDF_SOURCES = [dst for _, dst in HUMAN_LAYOUT if dst.endswith(".md") and not dst.startswith("LICENSE")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_human_packet() -> Path:
    root = STAGING / f"aeonisk-{VERSION}"
    if root.exists():
        shutil.rmtree(root)
    for src_rel, dst_rel in HUMAN_LAYOUT:
        src = REPO_ROOT / src_rel
        if not src.exists():
            raise SystemExit(f"missing source document: {src_rel}")
        dst = root / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return root


def render_pdfs(root: Path) -> None:
    """Render the human packet's markdown to PDF alongside the source.

    The DejaVu fonts and the print filter are both load-bearing: without them
    xelatex silently drops the status marks in NEXUS_LAW and the correct/wrong
    pairs in FACTION_REFERENCE. See scripts/pandoc/aeonisk_print.lua.
    """
    for rel in PDF_SOURCES:
        src = root / rel
        out = src.with_suffix(".pdf")
        cmd = [
            "pandoc",
            "--pdf-engine=xelatex",
            f"--lua-filter={PANDOC_FILTER}",
            "-V", "mainfont=DejaVu Sans",
            "-V", "monofont=DejaVu Sans Mono",
            "-V", "geometry:margin=1in",
            "--toc",
            str(src),
            "-o", str(out),
        ]
        print(f"  pdf: {rel}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"pandoc failed on {rel}:\n{result.stderr[-2000:]}")
        missing = [ln for ln in result.stderr.splitlines() if "Missing character" in ln]
        if missing:
            raise SystemExit(
                f"{rel}: xelatex dropped {len(missing)} character(s); the PDF would "
                f"be silently lossy. First: {missing[0]}"
            )


def write_zip(zip_path: Path, root: Path, arc_prefix: str) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f"{arc_prefix}/{path.relative_to(root)}")
    print(f"  {zip_path.relative_to(REPO_ROOT)}  ({len(files)} files, {zip_path.stat().st_size // 1024} KiB)")


def check() -> int:
    """Verify the shipped zips match canon. Non-zero if stale."""
    problems = []
    human_zip = RELEASES / f"aeonisk-{VERSION}-packet.zip"
    ai_zip = RELEASES / f"aeonisk-{VERSION}-ai-pack.zip"

    for zp in (human_zip, ai_zip):
        if not zp.exists():
            problems.append(f"{zp.name} has not been built")

    if human_zip.exists():
        with zipfile.ZipFile(human_zip) as zf:
            names = set(zf.namelist())
            for src_rel, dst_rel in HUMAN_LAYOUT:
                arc = f"aeonisk-{VERSION}/{dst_rel}"
                if arc not in names:
                    problems.append(f"{human_zip.name}: missing {dst_rel}")
                    continue
                if zf.read(arc) != (REPO_ROOT / src_rel).read_bytes():
                    problems.append(f"{human_zip.name}: {dst_rel} differs from {src_rel}")

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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", action="store_true", help="also render PDFs into the human packet")
    parser.add_argument("--check", action="store_true", help="verify the built zips match canon")
    args = parser.parse_args()

    if args.check:
        return check()

    # The AI pack must match canon before we ship it.
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

    human_root = stage_human_packet()
    if args.pdf:
        render_pdfs(human_root)
    write_zip(RELEASES / f"aeonisk-{VERSION}-packet.zip", human_root, f"aeonisk-{VERSION}")
    write_zip(RELEASES / f"aeonisk-{VERSION}-ai-pack.zip", AI_PACK_DIR, "ai_pack")

    shutil.rmtree(STAGING)
    print("Done. Upload both to itch.io; see packaging/itch-page.md for the listing copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
