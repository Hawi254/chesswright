# Spike-only PyInstaller spec -- proves FastAPI/uvicorn survive freezing
# alongside this project's existing backend modules. Deliberately
# separate from chesswright.spec/chesswright-pro.spec (per the
# chesswright_pro_pyinstaller_spec_gotcha project memory: building the
# wrong spec silently drops things) -- this file is never used for a
# real release build.
import pathlib
from PyInstaller.utils.hooks import collect_all

ROOT = pathlib.Path(".").resolve()

BACKEND_MODULES = [
    "ingest.py", "worker.py", "annotate.py", "analytics.py", "db.py",
    "config.py", "chess_utils.py", "migrate.py", "sync.py", "opening_explorer.py",
    "db_import.py", "joblock.py", "motif.py", "opponent_analysis.py",
    "sync_chesscom.py", "chesscom_pgn.py", "backfill_batch_eval_cache.py",
]

datas = [(str(ROOT / name), ".") for name in BACKEND_MODULES]
datas += [(str(ROOT / "migrations"), "migrations")]
datas += [(str(ROOT / "dashboard" / "_common.py"), "dashboard")]
datas += [(str(ROOT / "dashboard" / "data"), "dashboard/data")]
datas += [(str(ROOT / "api"), "api")]

hiddenimports = []
binaries = []
for pkg in ["fastapi", "uvicorn", "starlette", "duckdb", "pandas", "chess", "yaml"]:
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
