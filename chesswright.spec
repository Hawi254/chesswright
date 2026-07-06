# PyInstaller spec for the packaged desktop app (BRIEF.md Phase C).
#
# desktop_app.py never directly `import`s dashboard/app.py or any of the
# backend modules (ingest.py, worker.py, etc.) -- it launches dashboard/
# app.py by FILE PATH via streamlit's bootstrap.run(), and dashboard/
# _common.py reaches the backend modules via its own sys.path.insert()
# at runtime. PyInstaller's static analysis can't discover either of
# those by following imports, so every one of these has to be listed
# explicitly as a DATA file (plain .py source, imported normally by the
# bundled interpreter at runtime -- not compiled into the frozen
# bytecode archive the way desktop_app.py's own actual imports are).
#
# Build: pyinstaller chesswright.spec
# Run (after building): dist/chesswright/chesswright (Linux/macOS) or
#                        dist/chesswright/chesswright.exe (Windows)
import pathlib
from PyInstaller.utils.hooks import collect_all

block_cipher = None
ROOT = pathlib.Path(".").resolve()

BACKEND_MODULES = [
    "ingest.py", "worker.py", "annotate.py", "analytics.py", "db.py",
    "config.py", "chess_utils.py", "migrate.py", "sync.py", "opening_explorer.py",
    "db_import.py", "joblock.py", "motif.py", "opponent_analysis.py",
    "sync_chesscom.py", "chesscom_pgn.py",
]

datas = [(str(ROOT / "config.yaml"), ".")]
datas += [(str(ROOT / name), ".") for name in BACKEND_MODULES]
datas += [(str(ROOT / "migrations"), "migrations")]
datas += [(str(ROOT / "dashboard"), "dashboard")]
datas += [(str(ROOT / ".streamlit"), ".streamlit")]

# DuckDB's sqlite extension is downloaded from extensions.duckdb.org, NOT
# shipped in the duckdb wheel -- so collect_all("duckdb") below can never
# bundle it, and without this the packaged app's first launch needs the
# network (a real Windows pilot failure: firewalled machine, IOException
# at startup). Fetched here at build time -- through the build env's own
# pinned duckdb, on the target platform's runner, so version and platform
# always match the interpreter being frozen.
#
# Deliberately NOT added to `datas` (v0.1.20 shipped it that way and broke
# the macOS build): PyInstaller inspects every datas/binaries file's
# CONTENT and auto-reclassifies anything that looks like a real binary as
# BINARY/EXTENSION, regardless of which list it came from (build_main.py's
# "automatic binary vs. data reclassification" pass) -- and .duckdb_extension
# files are genuine Mach-O dylibs with DuckDB's own metadata footer appended
# after them. That reclassification puts the file through PyInstaller's
# macOS codesign step (`codesign --force --all-architectures --timestamp`),
# which chokes on the non-standard trailing footer and fails with "main
# executable failed strict validation" -- a real v0.1.20 CI failure, not a
# hypothetical. build.yml now copies + (on macOS) ad-hoc-signs this file
# into dist/chesswright/_internal/duckdb_extensions/ as a POST-build step,
# entirely outside PyInstaller's Analysis/COLLECT TOC, so it never enters
# that reclassification path at all.
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_duckdb_extensions import fetch as _fetch_duckdb_ext
_fetch_duckdb_ext(ROOT / "build_assets" / "duckdb_extensions")

# streamlit needs its own DATA files bundled, not just its .py source --
# confirmed by two separate live failures, not assumed from the research
# alone: (1) PackageNotFoundError for streamlit's own version (it calls
# importlib.metadata on itself at import time -- needs the METADATA
# file); (2) once that was fixed, the server started and bound its port
# but every request to "/" returned a bare 404 -- streamlit's actual
# frontend (the built HTML/JS/CSS under streamlit/static/) was missing
# entirely, so it had nothing to serve at the root route.
#
# Every package below is needed for a DIFFERENT reason than the two
# above: dashboard/app.py and the backend modules are never statically
# `import`ed by desktop_app.py (they're loaded dynamically, by file
# path, at runtime -- see the module docstring) -- so PyInstaller's
# Analysis phase never traversed THEIR import statements either, and
# silently bundled none of their third-party dependencies at all.
# Confirmed live: the first full-launcher test got past streamlit's own
# loading fine and then crashed immediately with
# `ModuleNotFoundError: No module named 'chess'` the moment app.py
# actually started importing the backend modules. Every package any
# dashboard/*.py or backend *.py module imports needs to be listed here
# explicitly -- this isn't optional/defensive, it's the direct
# consequence of the dynamic-loading architecture chosen above.
#
# collect_all() pulls in a package's submodules, data files, AND
# binaries in one call -- broader than copy_metadata() alone, needed
# for duckdb/pandas/matplotlib specifically since they ship compiled
# extensions and/or non-Python data files, not just .py source.
hiddenimports = []
binaries = []
for pkg in ["streamlit", "chess", "yaml", "duckdb", "pandas", "matplotlib",
            "anthropic", "requests", "plotly", "keyring", "jinja2"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

# Third-party packages' own internal test suites -- dead weight in a frozen
# app (~18.5MB measured in the real bundle: pandas 16M, matplotlib 2.2M,
# pyarrow 324K, plotly 12K; BRIEF.md named this follow-up when the CI
# matrix first ran). Two prune points are BOTH needed: `excludes` below
# stops the module graph pulling them into the PYZ, and the a.datas
# filter after Analysis catches the data-file copies -- pyarrow's and
# plotly's tests arrive via PyInstaller's own dependency hooks during
# Analysis, not our collect_all() list, so filtering only `datas` here
# would miss them.
_TEST_PRUNE_PREFIXES = (
    "pandas/tests", "matplotlib/tests", "mpl_toolkits/tests",
    "pyarrow/tests", "plotly/matplotlylib/tests",
)


def _keep_toc_entry(dest_name: str) -> bool:
    # Segment-boundary match: prune "pandas/tests" and "pandas/tests/...",
    # never a lookalike like "pandas/testing" (a real public pandas API).
    name = dest_name.replace("\\", "/")
    return not any(name == p or name.startswith(p + "/")
                   for p in _TEST_PRUNE_PREFIXES)


hiddenimports = [h for h in hiddenimports
                 if not h.startswith(("pandas.tests", "matplotlib.tests",
                                      "pyarrow.tests", "plotly.matplotlylib.tests"))]

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "streamlit.web.bootstrap",
        "streamlit.runtime.scriptrunner.magic_funcs",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pandas.tests", "matplotlib.tests", "pyarrow.tests",
              "plotly.matplotlylib.tests"],
    noarchive=False,
    cipher=block_cipher,
)

a.datas = [entry for entry in a.datas if _keep_toc_entry(entry[0])]
a.pure = [entry for entry in a.pure if _keep_toc_entry(entry[0].replace(".", "/"))]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chesswright",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep visible for now -- engine/worker output goes to
                    # this console during a batch; revisit (console=False)
                    # once Phase D pilot feedback says it should be hidden.
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="chesswright",
)
