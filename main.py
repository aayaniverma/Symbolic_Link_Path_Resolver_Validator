#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set

def resolve_symlink_chain(symlink_path: Path, max_hops: int = 100) -> Dict:
    """
    Resolve a symlink chain for `symlink_path`.
    Returns dict with:
      - 'chain': list of (path, is_symlink)
      - 'resolved': absolute Path if resolution ends in an existing target else None
      - 'broken': True if final target doesn't exist
      - 'loop': True if loop detected
      - 'error': error message if exception occurred
    """
    result = {
        "start": str(symlink_path),
        "chain": [],
        "resolved": None,
        "broken": False,
        "loop": False,
        "error": None
    }
    visited: Set[str] = set()
    current = symlink_path
    hops = 0

    try:
        while hops < max_hops:
            hops += 1
            is_link = current.is_symlink()
            result["chain"].append({"path": str(current), "is_symlink": bool(is_link)})

            # If not a symlink, we've reached a final node
            if not is_link:
                # final resolved candidate (absolute)
                resolved_abs = current.resolve(strict=False)
                result["resolved"] = str(resolved_abs)
                result["broken"] = not resolved_abs.exists()
                break

            # readlink to get target as text (may be relative)
            try:
                raw_target = os.readlink(str(current))
            except OSError as e:
                # couldn't read link (permissions or weird reparse)
                result["error"] = f"readlink error: {e}"
                return result

            # compute target path relative to current.parent
            target_path = (current.parent / raw_target)

            # canonicalize the textual form for loop detection
            # use absolute-without-resolving to avoid exception if broken
            canonical = str(target_path.absolute())
            if canonical in visited:
                result["loop"] = True
                result["error"] = "symlink loop detected"
                return result
            visited.add(canonical)

            # move to next
            current = target_path
        else:
            result["error"] = f"max hops ({max_hops}) reached"
    except Exception as ex:
        result["error"] = str(ex)

    return result

def scan_tree(start: Path, follow_symlinks_dirs: bool = False) -> List[Dict]:
    """
    Walk the directory tree starting at `start`.
    By default, do not follow directory symlinks during scanning (safe).
    """
    findings: List[Dict] = []

    # os.walk with followlinks controls whether directory symlinks are followed.
    for dirpath, dirnames, filenames in os.walk(start, followlinks=follow_symlinks_dirs):
        base = Path(dirpath)

        # Check directories (they may be symlinks themselves)
        for d in list(dirnames):
            p = base / d
            if p.is_symlink():
                res = resolve_symlink_chain(p)
                res.update({"type": "dir"})
                findings.append(res)

        # Check files (symlink files)
        for f in filenames:
            p = base / f
            if p.is_symlink():
                res = resolve_symlink_chain(p)
                res.update({"type": "file"})
                findings.append(res)

    return findings

def pretty_print(findings: List[Dict]):
    print(f"Found {len(findings)} symlink(s).")
    for idx, r in enumerate(findings, 1):
        print("-" * 72)
        print(f"{idx}. start: {r.get('start')}")
        print(f"   type: {r.get('type')}")
        if r.get("error"):
            print(f"   ERROR: {r['error']}")
            continue
        print("   Chain:")
        for c in r.get("chain", []):
            mark = "-> symlink" if c.get("is_symlink") else "-> final"
            print(f"     {c['path']} {mark}")
        if r.get("loop"):
            print("   LOOP detected.")
        else:
            print(f"   Resolved (absolute): {r.get('resolved')}")
            print(f"   Broken (dangling): {r.get('broken')}")
    print("-" * 72)

def main():
    parser = argparse.ArgumentParser(description="Resolve symlinks in a directory tree.")
    parser.add_argument("start", nargs="?", default=".", help="Start path (default: current directory)")
    parser.add_argument("--follow-symlinks", action="store_true",
                        help="Follow directory symlinks while recursing (use with caution)")
    parser.add_argument("--json", metavar="OUT", help="Write results to JSON file")
    args = parser.parse_args()

    start = Path(args.start).resolve()
    if not start.exists():
        print(f"Start path does not exist: {start}")
        return

    findings = scan_tree(start, follow_symlinks_dirs=args.follow_symlinks)
    pretty_print(findings)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"start": str(start), "results": findings}, fh, indent=2)
        print(f"Saved JSON to {args.json}")

if __name__ == "__main__":
    main()
