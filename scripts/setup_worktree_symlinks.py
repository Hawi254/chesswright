#!/usr/bin/env python3
"""Symlink this repo's gitignored-but-shared docs and skills into a git
worktree.

BRIEF.md, CLAUDE.md, docs/implementation_roadmap.md, docs/scoping/, and
.claude/skills/ are all listed in .gitignore (private project docs /
local-only tooling), so a fresh `git worktree add` checkout starts
without any of them -- discovered the hard way once already when a
frontend-rewrite worktree had no BRIEF.md/CLAUDE.md to read. Symlinking
(not copying) means edits made from either the main checkout or the
worktree stay in sync automatically, with nothing to accidentally drift.

Usage:
    python3 scripts/setup_worktree_symlinks.py <path-to-worktree>

Safe to re-run: skips anything already correctly symlinked, and refuses
to touch a path that exists as a real file/dir instead of a symlink
(never silently clobbers actual content).
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Relative to the repo root on both sides.
SHARED_PATHS = [
    "BRIEF.md",
    "CLAUDE.md",
    "docs/implementation_roadmap.md",
    "docs/scoping",
    ".claude/skills",
]


def main():
    if len(sys.argv) != 2:
        print("Usage: setup_worktree_symlinks.py <path-to-worktree>", file=sys.stderr)
        return 1

    worktree = pathlib.Path(sys.argv[1]).resolve()
    if not worktree.is_dir():
        print(f"Not a directory: {worktree}", file=sys.stderr)
        return 1
    if worktree == REPO_ROOT:
        print("Refusing to symlink the main repo root onto itself.", file=sys.stderr)
        return 1

    ok = True
    for rel in SHARED_PATHS:
        source = REPO_ROOT / rel
        target = worktree / rel

        if not source.exists():
            print(f"SKIP {rel}: no such path in the main repo ({source})", file=sys.stderr)
            ok = False
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        if target.is_symlink():
            if target.resolve() == source.resolve():
                print(f"OK   {rel}: already correctly symlinked")
            else:
                print(f"SKIP {rel}: exists as a symlink to something else ({target.resolve()})", file=sys.stderr)
                ok = False
            continue

        if target.exists():
            print(f"SKIP {rel}: exists as a real file/dir, not a symlink -- not touching it", file=sys.stderr)
            ok = False
            continue

        target.symlink_to(source)
        print(f"LINKED {rel} -> {source}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
