#!/usr/bin/env python3
"""
symlink_resolver.py

Recursively scan a directory tree (or single path) for symbolic links,
attempt to resolve each symlink following chains, detect loops, and
report dangling links. Prints a readable table and optionally JSON.

Usage:
    python3 symlink_resolver.py /path/to/scan
    python3 symlink_resolver.py /path/to/scan --json
"""

from __future__ import annotations
import os
import sys
import argparse
import json
from typing import List, Tuple, Dict

MAX_FOLLOW = 200  # safety cap for link following

def resolve_symlink(start_path: str, max_follow: int = MAX_FOLLOW) -> Dict:
    """
    Attempt to resolve a symlink by following readlink targets.

    Returns dict:
      {
        "link": <absolute path to symlink>,
        "status": "ok" | "broken" | "loop" | "maxdepth",
        "resolved": <final absolute target if available or last attempted>,
        "chain": [list of intermediate absolute paths followed]
      }
    """
    link = os.path.abspath(start_path)
    if not os.path.islink(link):
        raise ValueError(f"{link} is not a symbolic link")

    visited = []
    current = link
    for i in range(max_follow):
        try:
            target = os.readlink(current)  # may be relative
        except OSError as e:
            # readlink failed unexpectedly
            return {"link": link, "status": "broken", "resolved": current, "chain": visited, "error": str(e)}
        # If target is relative, interpret relative to directory containing 'current'
        if not os.path.isabs(target):
            current_dir = os.path.dirname(current)
            next_path = os.path.normpath(os.path.join(current_dir, target))
            next_path = os.path.abspath(next_path)
        else:
            next_path = os.path.abspath(target)

        visited.append(next_path)

        # loop detection: if we've seen this absolute path before -> loop
        if next_path in visited[:-1]:
            return {"link": link, "status": "loop", "resolved": next_path, "chain": visited}

        # if next_path is itself a symlink, continue following it
        if os.path.islink(next_path):
            current = next_path
            continue

        # not a symlink anymore. Check whether the file/dir exists
        if os.path.exists(next_path):
            return {"link": link, "status": "ok", "resolved": os.path.abspath(next_path), "chain": visited}
        else:
            # reached a non-symlink target that doesn't exist -> dangling
            return {"link": link, "status": "broken", "resolved": next_path, "chain": visited}

    # if we exit the loop, we exceeded max_follow
    return {"link": link, "status": "maxdepth", "resolved": current, "chain": visited}


def scan_tree(path: str, follow_dirs: bool = False) -> List[Dict]:
    """
    Recursively walk `path` and find symlinks. For each symlink found,
    call resolve_symlink and collect results.

    follow_dirs controls whether os.walk follows directory symlinks while scanning.
    We do not follow directory symlinks by default to avoid scanning arbitrary other
    parts of the filesystem.
    """
    results = []
    # Use os.walk but avoid following dir-links unless user specifically requested it
    for root, dirs, files in os.walk(path, followlinks=follow_dirs):
        # examine entries in this directory using lstat to detect symlinks without following
        entries = files + dirs
        for name in entries:
            full = os.path.join(root, name)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if os.path.islink(full):
                try:
                    res = resolve_symlink(full)
                except Exception as e:
                    res = {"link": os.path.abspath(full), "status": "error", "error": str(e), "resolved": None, "chain": []}
                results.append(res)
    return results


def format_table(results: List[Dict]) -> str:
    """
    Produce a simple aligned text table of results.
    """
    lines = []
    header = f"{'SYMLINK':<60}  {'STATUS':<8}  {'RESOLVED (final)':<60}"
    sep = "-" * (len(header) + 10)
    lines.append(header)
    lines.append(sep)
    for r in results:
        link = r.get("link", "")
        status = r.get("status", "")
        resolved = r.get("resolved", "") or ""
        lines.append(f"{link:<60}  {status:<8}  {resolved:<60}")
        # add chain detail indented
        chain = r.get("chain", [])
        if chain:
            for c in chain:
                lines.append(f"{'':4}-> {c}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Symbolic Link Path Resolver & Validator")
    p.add_argument("path", nargs="?", default=".", help="Path to scan (file or directory).")
    p.add_argument("--json", action="store_true", help="Output results as JSON.")
    p.add_argument("--follow-dirs", action="store_true", help="Let os.walk follow directory symlinks while scanning.")
    args = p.parse_args()

    target = args.path
    if not os.path.exists(target) and not os.path.islink(target):
        print(f"Error: path '{target}' does not exist.", file=sys.stderr)
        sys.exit(2)

    # If target is a file path and that file is a symlink, just resolve that; otherwise scan tree
    results = []
    if os.path.islink(target) and not os.path.isdir(target):
        try:
            results = [resolve_symlink(target)]
        except Exception as e:
            results = [{"link": os.path.abspath(target), "status": "error", "error": str(e), "resolved": None, "chain": []}]
    else:
        # scan recursively
        results = scan_tree(target, follow_dirs=args.follow_dirs)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_table(results))

if __name__ == "__main__":
    main()
