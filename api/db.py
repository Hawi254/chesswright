"""Connection helper for the FastAPI spike service.

Reuses dashboard/_common.py's get_connections() directly rather than
reimplementing it: get_connections() is @st.cache_resource-decorated, but
nothing in its own body touches an active ScriptRunContext (confirmed --
see tests/integration/test_api_overview.py::test_get_connections_works_outside_streamlit).
The DuckDB per-PID-snapshot + locked-connection machinery it wraps is a
hard-won fix for a real corruption incident (duckdb_sqlite_same_process_hazard
project memory) -- reused here, not duplicated, on purpose.
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(DASHBOARD_DIR))

import _common


def get_db_connections():
    """Returns (sqlite_conn, duck_conn). Thin re-export of
    dashboard/_common.py's get_connections() under an API-layer-scoped
    name."""
    return _common.get_connections()
