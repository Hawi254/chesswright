#!/usr/bin/env python3
"""Local build pipeline for the pure React+FastAPI packaged app (see
docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md).
Local-only for now -- NOT wired into .github/workflows/build.yml, since
this path is an internal/parallel proof (most nav destinations still
404), not a real release artifact yet.

Steps: build the frontend (npm run build), confirm the DuckDB sqlite
extension has already been fetched, run PyInstaller, then copy the
DuckDB extension into the frozen bundle OUTSIDE PyInstaller's own
Analysis/COLLECT TOC -- mirrors .github/workflows/build.yml's existing
"Bundle DuckDB sqlite extension (post-build, outside PyInstaller's TOC)"
step exactly, for the same reason documented there: routing a
.duckdb_extension file through datas triggers PyInstaller's binary
reclassification and a macOS codesign failure that has nothing to do
with the file being broken (see the duckdb_macos_codesign_saga project
memory).

Usage: python3 scripts/build_react_app.py
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
DUCKDB_EXTENSION = ROOT / "build_assets" / "duckdb_extensions" / "sqlite_scanner.duckdb_extension"


def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    if not DUCKDB_EXTENSION.exists():
        print(
            f"error: {DUCKDB_EXTENSION} is missing.\n"
            "Run `python scripts/fetch_duckdb_extensions.py` once (while "
            "online) before building.",
            file=sys.stderr,
        )
        sys.exit(1)

    run(["npm", "ci"], cwd=str(FRONTEND_DIR))
    run(["npm", "run", "build"], cwd=str(FRONTEND_DIR))

    run(["pyinstaller", "chesswright-react.spec", "--noconfirm"], cwd=str(ROOT))

    bundled_ext_dir = ROOT / "dist" / "chesswright-react" / "_internal" / "duckdb_extensions"
    bundled_ext_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(DUCKDB_EXTENSION, bundled_ext_dir / DUCKDB_EXTENSION.name)
    print(f"Copied {DUCKDB_EXTENSION.name} into {bundled_ext_dir}")

    print("Build complete: dist/chesswright-react/chesswright-react")


if __name__ == "__main__":
    main()
