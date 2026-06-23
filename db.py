import sqlite3


def get_connection(db_path: str, check_same_thread: bool = True) -> sqlite3.Connection:
    """All scripts should connect through this, not sqlite3.connect() directly --
    foreign_keys is a per-connection PRAGMA, not a database-file setting, so it
    has to be set every time a connection opens.

    check_same_thread=False is for the Streamlit dashboard only (Phase 6):
    st.cache_resource shares one long-lived connection across script
    reruns, but Streamlit runs each rerun in its own thread, and sqlite3
    refuses cross-thread use by default. Every other caller in this
    project runs single-threaded and should leave this at the default."""
    conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
