"""Connection helper for the FastAPI service.

Reuses connections.py's open_connections() directly rather than
reimplementing it: the DuckDB per-PID-snapshot + locked-connection
machinery it wraps is a hard-won fix for a real corruption incident
(duckdb_sqlite_same_process_hazard project memory) -- reused here, not
duplicated. Unlike dashboard/_common.py's get_connections() (which this
module used to call through), connections.open_connections() has no
streamlit dependency at all -- see connections.py's own docstring and
docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md.
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connections


def get_db_connections():
    """Returns (sqlite_conn, duck_conn). Thin re-export of connections.py's
    open_connections() under an API-layer-scoped name."""
    return connections.open_connections()
