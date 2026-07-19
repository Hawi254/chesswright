"""On-demand Stockfish analysis for interactive Streamlit dashboard
panels. The streamlit-free core (EngineService, LiveResult,
get_engine_service, get_engine_status_summary) moved to
dashboard/engine_status.py (2026-07-13) so api/main.py can use engine
status without importing streamlit -- see that module's docstring. This
file keeps only what actually touches st.session_state/st.spinner/
st.checkbox/st.caption.

A threading.Lock (inside EngineService, in engine_status.py) serialises
analyse() calls from rapid reruns.
"""
import config
import joblock
import streamlit as st

import chess_display
import engine_status
from engine_status import EngineService, LiveResult, get_engine_status_summary  # noqa: F401 -- re-exported


def get_engine_service():
    """Thin wrapper: the real process-wide singleton lives in
    engine_status.py so api/main.py can reuse it without importing
    streamlit. .clear() is attached below so dashboard/settings_view.py's
    existing live_engine.get_engine_service.clear() calls (force a
    reconnect after an engine-path change) keep clearing the SAME cache
    engine_status.py owns, not a second, independently-stale one."""
    return engine_status.get_engine_service()


get_engine_service.clear = lambda: engine_status.clear_engine_service_cache()


def batch_running() -> bool:
    """True when the batch worker holds the joblock and its process is alive."""
    info = joblock.status()
    return info is not None and info.alive


def _result_to_dict(live_result: LiveResult) -> dict:
    """LiveResult -> the {eval_cp, ..., source} dict shape callers display.
    source is derived from engine_version rather than tracked separately --
    fetch_cloud_eval() tags its results "Lichess cloud", any real UCI
    engine reports its own name instead."""
    source = "lichess_cloud" if live_result.engine_version == "Lichess cloud" else "live"
    return {
        "eval_cp": live_result.eval_cp,
        "eval_mate": live_result.eval_mate,
        "best_move_san": live_result.best_move_san,
        "pv_json": live_result.pv_json,
        "depth": live_result.depth,
        "source": source,
    }


def get_or_analyse_position(sqlite_conn, fen: str, analysis: dict | None,
                             session_key: str, on_fresh_result=None) -> dict | None:
    """Fills a DB-cache miss (analysis is None) by trying Lichess's cloud-eval
    database first, then falling back to a local engine spinner probe --
    consolidates the sequence previously duplicated across
    openings_view.py's "Most-repeated positions" and "Repertoire holes"
    panels.

    `analysis` is whatever the caller's own st.cache_data-wrapped
    data.get_position_analysis() lookup already returned (moves/
    position_cache tiers) -- passed straight through on a hit.

    session_key: a caller-chosen key (typically the FEN, or something that
    varies with it) used to memoize a fresh cloud/live result in
    st.session_state across reruns of the same position, the same
    convention openings_view.py's live_result__{fen} keys already used.

    on_fresh_result: called once, only when this invocation newly wrote a
    result (cloud or local) -- never on a rerun that finds the result
    already in st.session_state. Callers use this to invalidate their own
    page-level st.cache_data wrapper (e.g. cached_position_analysis.clear())
    so the position promotes to the fast DB-cache tier on the next lookup,
    exactly as the pre-refactor inline code did."""
    if analysis is not None:
        return analysis

    import data  # local import: avoids a module-level dashboard.data <-> live_engine dependency

    live_key = f"live_result__{session_key}"
    live_result = st.session_state.get(live_key)
    if live_result is not None:
        return _result_to_dict(live_result)

    cfg = config.load_config().get("interactive_engine", {})
    if cfg.get("use_lichess_cloud_eval", True):
        import lichess_cloud_eval  # local import: avoids a live_engine <-> lichess_cloud_eval cycle
        cloud_result = lichess_cloud_eval.fetch_cloud_eval(fen)
        if cloud_result is not None:
            st.session_state[live_key] = cloud_result
            data.store_position_analysis(sqlite_conn, fen, cloud_result)
            if on_fresh_result:
                on_fresh_result()
            return _result_to_dict(cloud_result)

    engine_svc = get_engine_service()
    if engine_svc is None:
        st.caption("Stockfish not found — configure the engine path in Settings.")
        return None
    if batch_running():
        st.caption("Batch analysis running — live engine paused until it finishes.")
        return None
    with st.spinner("Analysing position..."):
        live_result = engine_svc.analyse(fen)
    if live_result is None:
        return None
    st.session_state[live_key] = live_result
    data.store_position_analysis(sqlite_conn, fen, live_result)
    if on_fresh_result:
        on_fresh_result()
    return _result_to_dict(live_result)


def render_confirm_toggle(sqlite_conn, fen: str, key: str,
                           label: str = "Confirm with live engine") -> None:
    """Optional live-engine confirmation, off by default (analyse() has a
    real time cost) -- shared by SRS Drills and Opening Tree so both get
    the same session_state caching convention game_detail_view.py's
    "Analyse position" button already established."""
    import data  # local import: avoids a module-level dashboard.data <-> live_engine dependency

    engine_svc = get_engine_service()
    if engine_svc is None:
        return

    if not st.checkbox(label, key=key):
        return

    live_key = f"live_result__{fen}"
    live_result = st.session_state.get(live_key)
    if live_result is None:
        if batch_running():
            st.caption("Batch analysis running — live engine paused.")
            return
        with st.spinner("Analysing..."):
            live_result = engine_svc.analyse(fen)
        if live_result is None:
            st.caption("Engine analysis unavailable right now.")
            return
        st.session_state[live_key] = live_result
        data.store_position_analysis(sqlite_conn, fen, live_result)

    eval_label = chess_display.eval_str(live_result.eval_cp, live_result.eval_mate)
    pv = chess_display.pv_str(fen, live_result.pv_json)
    depth_str = f" (depth {live_result.depth})" if live_result.depth else ""
    st.caption("Engine: " + eval_label + (f" — {pv}" if pv else "") + depth_str)
