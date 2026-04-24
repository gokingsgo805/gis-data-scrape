#!/usr/bin/env python3
"""
organize_gis_files.py

Scans a source directory for .kmz and .geojson files, pairs them by base
filename (falling back to index-based grouping when names don't match), and
copies each pair into its own subdirectory.  Each subdirectory is initialized
as a git repository so it can be pushed to a separate GitHub remote.

Usage
-----
    python organize_gis_files.py <source_dir> [--output-dir <out_dir>]

    source_dir   – path that contains the .kmz / .geojson files
                   (e.g.  "C:\\Users\\Cobiwan Kenobi"  on Windows,
                    or   "/mnt/c/Users/Cobiwan Kenobi"  via WSL)
    --output-dir – where to create the paired sub-repos (default: ./gis-repos)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def find_gis_files(source_dir: Path):
    """Return sorted lists of .kmz and .geojson files found in *source_dir*."""
    kmz_files = sorted(source_dir.glob("*.kmz"))
    geojson_files = sorted(source_dir.glob("*.geojson"))
    return kmz_files, geojson_files


def pair_files(kmz_files, geojson_files):
    """
    Pair .kmz and .geojson files.

    Strategy
    --------
    1. Try to match by identical base name  (e.g. "parks.kmz" ↔ "parks.geojson").
    2. Remaining unmatched files are paired in order (first leftover kmz with
       first leftover geojson, etc.).
    3. Any truly unpaired file is placed in its own single-file group.

    Returns a list of tuples: [(name, [file, ...]), ...]
      where *name* is a directory-safe string and each inner list holds 1-2 Path
      objects that belong together.
    """
    kmz_by_stem = {f.stem: f for f in kmz_files}
    geojson_by_stem = {f.stem: f for f in geojson_files}

    pairs = []
    used_kmz = set()
    used_geojson = set()

    # --- matched by stem ---
    for stem in sorted(kmz_by_stem):
        if stem in geojson_by_stem:
            pairs.append((stem, [kmz_by_stem[stem], geojson_by_stem[stem]]))
            used_kmz.add(stem)
            used_geojson.add(stem)

    # --- unmatched: pair in order ---
    remaining_kmz = [f for s, f in sorted(kmz_by_stem.items()) if s not in used_kmz]
    remaining_geojson = [f for s, f in sorted(geojson_by_stem.items()) if s not in used_geojson]

    pair_idx = len(pairs) + 1
    while remaining_kmz and remaining_geojson:
        k = remaining_kmz.pop(0)
        g = remaining_geojson.pop(0)
        name = f"gis-pair-{pair_idx:02d}"
        pairs.append((name, [k, g]))
        pair_idx += 1

    # --- truly unpaired ---
    for f in remaining_kmz:
        pairs.append((f.stem, [f]))
    for f in remaining_geojson:
        pairs.append((f.stem, [f]))

    return pairs


def init_git_repo(repo_dir: Path):
    """Run `git init` inside *repo_dir* (requires git on PATH)."""
    try:
        subprocess.run(
            ["git", "init"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit – GIS data files"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        print(f"    ✔  git repo initialized in {repo_dir}")
    except FileNotFoundError:
        print("    ⚠  git not found on PATH – skipping repo initialization.")
    except subprocess.CalledProcessError as exc:
        print(f"    ⚠  git command failed: {exc.stderr.decode().strip()}")


def write_readme(repo_dir: Path, pair_name: str, files):
    """Write a minimal README.md into the new repo directory."""
    filenames = "\n".join(f"- `{f.name}`" for f in files)
    content = (
        f"# {pair_name}\n\n"
        "GIS data files automatically extracted from source directory.\n\n"
        "## Files\n\n"
        f"{filenames}\n"
    )
    (repo_dir / "README.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Pair KMZ/GeoJSON files and set up individual git repos."
    )
    parser.add_argument(
        "source_dir",
        help="Directory containing the .kmz and .geojson files",
    )
    parser.add_argument(
        "--output-dir",
        default="gis-repos",
        help="Directory where the paired sub-repos will be created (default: ./gis-repos)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not source_dir.is_dir():
        sys.exit(f"ERROR: source directory not found: {source_dir}")

    print(f"Source : {source_dir}")
    print(f"Output : {output_dir}")
    print()

    kmz_files, geojson_files = find_gis_files(source_dir)

    if not kmz_files and not geojson_files:
        sys.exit("No .kmz or .geojson files found in the source directory.")

    print(f"Found {len(kmz_files)} .kmz file(s) and {len(geojson_files)} .geojson file(s).")
    print()

    pairs = pair_files(kmz_files, geojson_files)
    output_dir.mkdir(parents=True, exist_ok=True)

    for pair_name, files in pairs:
        repo_dir = output_dir / pair_name
        repo_dir.mkdir(parents=True, exist_ok=True)

        print(f"Creating repo: {pair_name}/")
        for f in files:
            dest = repo_dir / f.name
            shutil.copy2(f, dest)
            print(f"    copied {f.name}")

        write_readme(repo_dir, pair_name, files)
        init_git_repo(repo_dir)
        print()

    print(f"Done. {len(pairs)} repo(s) created under {output_dir}")
    print()
    print("Next steps:")
    print("  1. Create a new GitHub repository for each sub-directory.")
    print("  2. Inside each sub-directory run:")
    print('       git remote add origin https://github.com/<user>/<repo-name>.git')
    print('       git branch -M main   # rename branch to main if needed')
    print('       git push -u origin main')


if __name__ == "__main__":
    main()
