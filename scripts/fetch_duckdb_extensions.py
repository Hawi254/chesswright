"""Fetch DuckDB's sqlite_scanner extension at BUILD time so the packaged
app never needs extensions.duckdb.org at RUNTIME.

Why this exists (the actual pilot failure, not a hypothetical): DuckDB's
sqlite extension is NOT part of the duckdb wheel -- `INSTALL sqlite`
downloads it over the network on first use. dashboard/_common.py's
get_duckdb_connection() ran that on every fresh machine's first launch,
so a Windows pilot tester whose machine couldn't reach
extensions.duckdb.org (firewall/proxy/offline) got an IOException
traceback before the app ever drew a page. Fetching here, on the build
machine, and bundling the resulting file (chesswright.spec maps it into
_internal/duckdb_extensions/) makes first launch fully offline, which is
what "local install, never synced" promised in the first place.

The extension file is platform- AND duckdb-version-specific. Running the
fetch through the build environment's own duckdb (pinned in
constraints.txt) on the target platform's CI runner guarantees both
match the interpreter being frozen. A version marker file makes a stale
local cache from a previous duckdb pin impossible to ship silently.

Usage: python scripts/fetch_duckdb_extensions.py [dest_dir]
(default dest: <repo root>/build_assets/duckdb_extensions -- gitignored)
"""
import pathlib
import shutil
import sys

import duckdb

EXTENSION = "sqlite_scanner"  # `INSTALL sqlite` installs it under this name
_VERSION_MARKER = ".duckdb-version"


def fetch(dest_dir: pathlib.Path) -> pathlib.Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext_file = dest_dir / f"{EXTENSION}.duckdb_extension"
    marker = dest_dir / _VERSION_MARKER

    if ext_file.exists() and marker.exists() \
            and marker.read_text().strip() == duckdb.__version__:
        print(f"OK: {ext_file} already fetched for duckdb {duckdb.__version__}")
        return ext_file

    # INSTALL into a private staging directory (never ~/.duckdb -- the
    # build must not depend on, or pollute, the build machine's own
    # DuckDB state), then harvest the decompressed .duckdb_extension file
    # out of the versioned layout INSTALL creates.
    staging = dest_dir / "_staging"
    shutil.rmtree(staging, ignore_errors=True)
    conn = duckdb.connect(config={"extension_directory": str(staging)})
    try:
        conn.execute("INSTALL sqlite;")
    finally:
        conn.close()
    installed = list(staging.rglob(f"{EXTENSION}.duckdb_extension"))
    if len(installed) != 1:
        raise SystemExit(
            f"expected exactly one {EXTENSION}.duckdb_extension under "
            f"{staging}, found {len(installed)}: {installed}"
        )
    shutil.copy2(installed[0], ext_file)
    shutil.rmtree(staging, ignore_errors=True)
    marker.write_text(duckdb.__version__)

    # Prove the harvested file actually loads in THIS duckdb before the
    # build ships it -- catches a truncated download or platform mismatch
    # here, not on a pilot tester's first launch.
    check = duckdb.connect()
    try:
        check.execute(f"LOAD '{ext_file.as_posix()}'")
    finally:
        check.close()
    print(f"OK: fetched and load-verified {ext_file} "
          f"(duckdb {duckdb.__version__})")
    return ext_file


if __name__ == "__main__":
    default_dest = pathlib.Path(__file__).resolve().parent.parent \
        / "build_assets" / "duckdb_extensions"
    fetch(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else default_dest)
