"""Shared helpers for the Phase 6 dashboard.

Mirrors analysis/_common.py's pattern (project-root sys.path insertion,
DuckDB-over-SQLite connection) but kept as its own module rather than
importing analysis/_common.py directly -- both directories are flat
(non-package) module collections, and adding both to sys.path at once
would risk an ambiguous `_common` import. Trivial duplication of the
connection helper, not of any query logic.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import duckdb
import streamlit as st

from config import load_config, pick
from db import get_connection as _get_sqlite_connection
import migrate


def get_duckdb_connection(db_path):
    conn = duckdb.connect()
    conn.execute("INSTALL sqlite; LOAD sqlite;")
    conn.execute(f"ATTACH '{db_path}' AS db (TYPE sqlite)")
    return conn


def get_sqlite_connection(db_path):
    """check_same_thread=False -- see db.get_connection's docstring.
    Caveat worth knowing, not just silently working around: this allows
    cross-thread use but doesn't make the connection safe for truly
    CONCURRENT access from multiple threads at once. Fine for a
    single-user personal dashboard where reruns happen one at a time;
    would need real per-session connections if this ever serves multiple
    simultaneous users."""
    return _get_sqlite_connection(db_path, check_same_thread=False)


def resolve_db_path(cli_db_path=None, config_path=None):
    # Pro profile takes precedence when active, unless a specific path or
    # config was explicitly requested by the caller (CLI flags, import flow).
    if not cli_db_path and not config_path:
        from config import get_active_profile, get_profile_db_path
        active = get_active_profile()
        if active:
            return str(get_profile_db_path(active))
    cfg = load_config(config_path)
    return pick(cli_db_path, cfg["database"]["path"])


def get_config(config_path=None):
    if not config_path:
        from config import get_active_profile, get_profile_config_path
        active = get_active_profile()
        if active:
            profile_cfg = get_profile_config_path(active)
            if profile_cfg.exists():
                return load_config(str(profile_cfg))
    return load_config(config_path)


@st.cache_resource
def get_connections():
    """One SQLite connection + one DuckDB connection for the whole server
    session (st.cache_resource, not cache_data -- these are live
    connections, not serializable results). Moved here from app.py in
    Phase 6c.3 (multi-page restructure) specifically so every page module
    (game_explorer_view.py, game_detail_view.py, app.py itself) shares the
    SAME cached singleton -- two separately-defined get_connections()
    functions in different modules would each get their OWN cache entry
    (Streamlit keys st.cache_resource by function identity), silently
    reopening the connection and re-triggering the ~94s structure_ctx
    rebuild cost this caching exists to avoid in the first place."""
    db_path = resolve_db_path()
    migrate.migrate(db_path)
    return get_sqlite_connection(db_path), get_duckdb_connection(db_path)


def navigate_on_row_click(df, key, detail_page, self_page, return_label, column_config=None):
    """One shared drill-down mechanism (Phase 6c.4): renders df with
    native st.dataframe row selection, and on a click, stores the
    selected row's game_id + where to return to, then switches to Game
    Detail. df MUST have a game_id column. Used by every Tactical
    Highlights/Matchups & Opponents panel that lists individual games --
    avoids re-typing the same on_select/session_state wiring per panel."""
    selection = st.dataframe(df, width='stretch', on_select="rerun",
                              selection_mode="single-row", key=key,
                              column_config=column_config)
    st.caption("Click a row to open that game's full detail.")
    rows = selection.selection.rows if selection and selection.selection else []
    if rows:
        st.session_state["selected_game_id"] = df.iloc[rows[0]].game_id
        st.session_state["return_page"] = self_page
        st.session_state["return_page_label"] = return_label
        st.switch_page(detail_page)
