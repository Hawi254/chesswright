# Real (non-spike) PyInstaller spec for the pure React+FastAPI desktop
# build -- see docs/superpowers/specs/2026-07-13-react-frontend-
# packaging-design.md. Graduated from api_spike.spec, which proved
# FastAPI/uvicorn survive freezing alongside this project's backend
# modules. Kept as a THIRD, isolated spec alongside chesswright.spec/
# chesswright-pro.spec -- same precedent this repo already has for
# keeping specs from silently colliding (chesswright_pro_pyinstaller_
# spec_gotcha project memory). Zero risk to the existing production
# chesswright.spec/build.yml -- nothing about the Streamlit build
# changes.
import pathlib
from PyInstaller.utils.hooks import collect_all

ROOT = pathlib.Path(".").resolve()

# Every root-level module the API's import chain reaches, PLUS
# connections.py (new) and desktop_app.py (reused for its
# ensure_user_data/resource_dir/free_port/wait_for_server/
# check_cpu_compat/check_webview2 helpers -- see react_desktop_app.py).
# desktop_app.py's own `if __name__ == "__main__"` guard means importing
# it has no side effects.
BACKEND_MODULES = [
    "ingest.py", "worker.py", "annotate.py", "analytics.py", "db.py",
    "config.py", "chess_utils.py", "migrate.py", "sync.py", "opening_explorer.py",
    "db_import.py", "joblock.py", "motif.py", "opponent_analysis.py",
    "sync_chesscom.py", "chesscom_pgn.py", "backfill_batch_eval_cache.py",
    "achievements.py", "backfill_achievements.py", "backfill_legal_reply_count.py",
    "connections.py", "desktop_app.py",
]

datas = [(str(ROOT / name), ".") for name in BACKEND_MODULES]
datas += [(str(ROOT / "config.yaml"), ".")]
datas += [(str(ROOT / "migrations"), "migrations")]
# dashboard/*.py's transitive flat-module dependencies (chess_display.py,
# confidence.py, etc.) -- same reasoning as api_spike.spec: bundling the
# whole directory (a few MB) is simpler and more robust than whack-a-mole
# adding individual modules as ModuleNotFoundErrors surface.
datas += [(str(ROOT / "dashboard"), "dashboard")]
datas += [(str(ROOT / "api"), "api")]
# The built frontend -- produced by `npm run build` in frontend/ (see
# scripts/build_react_app.py, which runs that BEFORE this spec).
# api/main.py's FRONTEND_DIST_DIR resolves to this same relative location
# in both source and frozen mode (see that module's comment).
datas += [(str(ROOT / "frontend" / "dist"), "frontend/dist")]

hiddenimports = []
binaries = []
# NOTE: "streamlit" is deliberately ABSENT from this list, unlike
# api_spike.spec -- the connections.py/engine_status.py extraction
# (docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md)
# removed it from api/main.py's real import closure. Confirmed by
# Task 5's zero-streamlit check; this spec's own build (Task 9) confirms
# it again against the actual frozen bundle.
for pkg in ["fastapi", "uvicorn", "starlette", "duckdb", "pandas", "chess", "yaml",
            "numpy", "matplotlib", "anthropic", "requests", "plotly",
            "keyring", "jinja2", "rapidfuzz", "markdown", "pywebview"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["react_desktop_app.py"],
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
    name="chesswright-react",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="chesswright-react")
