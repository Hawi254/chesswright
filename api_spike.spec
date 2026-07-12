# Spike-only PyInstaller spec -- proves FastAPI/uvicorn survive freezing
# alongside this project's existing backend modules. Deliberately
# separate from chesswright.spec/chesswright-pro.spec (per the
# chesswright_pro_pyinstaller_spec_gotcha project memory: building the
# wrong spec silently drops things) -- this file is never used for a
# real release build.
import pathlib
from PyInstaller.utils.hooks import collect_all

ROOT = pathlib.Path(".").resolve()

# Every root-level module except desktop_app.py (the GUI launcher itself,
# never imported by the data layer). The original narrow list only covered
# what the spike's 3 Overview endpoints needed directly -- `import data` in
# api/main.py pulls in dashboard/data/__init__.py's full re-export surface,
# whose transitive closure turned out much wider (found by repeated
# ModuleNotFoundError iterations: opponent_analysis.py -> sync.py ->
# achievements.py, three hops deep, not visible from the Overview-only
# spike). Bundling everything up front avoids more of that.
BACKEND_MODULES = [
    "ingest.py", "worker.py", "annotate.py", "analytics.py", "db.py",
    "config.py", "chess_utils.py", "migrate.py", "sync.py", "opening_explorer.py",
    "db_import.py", "joblock.py", "motif.py", "opponent_analysis.py",
    "sync_chesscom.py", "chesscom_pgn.py", "backfill_batch_eval_cache.py",
    "achievements.py", "backfill_achievements.py", "backfill_legal_reply_count.py",
]

datas = [(str(ROOT / name), ".") for name in BACKEND_MODULES]
# config.py's DEFAULT_CONFIG_PATH resolves to __file__'s own directory when
# CHESSWRIGHT_CONFIG_PATH isn't set (dev-workflow default) -- that's the
# bundle root when frozen (config.py sits at "."), so config.yaml has to
# sit there too. Missing this raised a plain FileNotFoundError, masked by
# a confusing secondary streamlit.errors.NoSessionContext (the
# @st.cache_resource spinner's teardown reacting to the underlying
# exception while running outside a real session, not an independent bug).
datas += [(str(ROOT / "config.yaml"), ".")]
datas += [(str(ROOT / "migrations"), "migrations")]
# dashboard/_common.py's transitive import chain (via dashboard/data/*.py,
# which api/main.py imports wholesale) reaches into several sibling flat
# dashboard/*.py helper modules -- confidence.py, chess_display.py, and
# potentially others -- not just _common.py itself. Whack-a-mole-adding
# them one ModuleNotFoundError at a time (each rebuild costs ~2 minutes)
# stopped being worth it after the second one; bundling the whole
# directory (2.9MB total, confirmed small) is simpler and robust against
# any other flat-module dependency dashboard/data/*.py picks up later.
datas += [(str(ROOT / "dashboard"), "dashboard")]
datas += [(str(ROOT / "api"), "api")]

hiddenimports = []
binaries = []
# dashboard/_common.py (imported transitively via api/db.py -> _common) does
# an unconditional `import streamlit as st` even in bare/non-served mode --
# confirmed live: without collecting it here, the frozen binary's
# run_api_server_mode() crashes with ModuleNotFoundError the first time
# dispatch actually reaches api/main.py's real imports (masked until now by
# the fork-bomb bug, which never got this far). chesswright.spec already
# does collect_all("streamlit") for the same reason -- reusing the same
# proven call, not inventing a new one.
# Full requirements.txt third-party list except pywebview (GUI-launcher-only,
# never touched by the data layer `import data` pulls in) -- added in one
# batch after rapidfuzz was the third one-off ModuleNotFoundError found via
# individual rebuild cycles; the whole dashboard/data package's transitive
# closure is wider than the original 3-endpoint Overview spike exercised.
for pkg in ["fastapi", "uvicorn", "starlette", "duckdb", "pandas", "chess", "yaml",
            "streamlit", "numpy", "matplotlib", "anthropic", "requests", "plotly",
            "keyring", "jinja2", "rapidfuzz", "markdown"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["api/spike_launcher.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="api_spike",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="api_spike")
