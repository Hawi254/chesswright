"""On-demand Stockfish analysis for interactive dashboard panels.

A single EngineService subprocess is held in @st.cache_resource so it
survives across Streamlit reruns without re-spawning Stockfish each time.
A threading.Lock serialises analyse() calls from rapid reruns.

Hard constraints (confirmed in design discussion):
- Batch running (joblock alive) → return None immediately; never compete
  for hardware with the batch worker.
- Always pair Limit(time=..., depth=...) -- depth alone is not safe.
- Auto-store results to position_cache when depth >= store_threshold.
- Max 3 restart attempts if the subprocess dies; give up after that.

Reuses worker.find_engine_path, worker.configure_supported, and
worker.score_to_fields to stay DRY with the batch worker.
"""
import atexit
import dataclasses
import json
import threading

import chess
import chess.engine
import streamlit as st

import chess_display
import config
import joblock
import worker


@dataclasses.dataclass
class LiveResult:
    eval_cp: int | None
    eval_mate: int | None
    best_move_san: str | None
    pv_json: str          # JSON-encoded list of SAN moves
    depth: int            # actual search depth reached
    engine_version: str


class EngineService:
    """Wraps a persistent Stockfish subprocess for on-demand analysis.

    Thread-safe via a single threading.Lock.  Restarts on failure up to
    _MAX_RESTARTS times.  Registers an atexit handler so the subprocess
    doesn't linger when Streamlit exits.
    """

    _MAX_RESTARTS = 3

    def __init__(self, path: str, cfg: dict):
        self._path = path
        self._cfg = cfg
        self._engine: chess.engine.SimpleEngine | None = None
        self._engine_version = ""
        self._lock = threading.Lock()
        self._restart_count = 0
        self._dead = False
        self._start()
        atexit.register(self._shutdown)

    def _start(self) -> None:
        self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
        self._engine_version = self._engine.id.get("name", "unknown")
        worker.configure_supported(self._engine, {
            "Threads": self._cfg.get("threads", 1),
            "Hash":    self._cfg.get("hash_mb", 32),
        })

    def _ensure_alive(self) -> bool:
        """Return True if the engine is ready.  Try to restart if it crashed."""
        if self._dead:
            return False
        if self._engine is not None:
            return True  # still alive; analyse() will set to None on failure
        if self._restart_count >= self._MAX_RESTARTS:
            self._dead = True
            return False
        self._restart_count += 1
        try:
            self._start()
            return True
        except Exception:
            self._engine = None
            if self._restart_count >= self._MAX_RESTARTS:
                self._dead = True
            return False

    def analyse(self, fen: str) -> LiveResult | None:
        """Analyse a position.  Returns None if engine unavailable or batch running."""
        lock_info = joblock.status()
        if lock_info is not None and lock_info.alive:
            return None  # hard block: never compete with batch

        time_sec = float(self._cfg.get("time_sec", 0.5))
        depth    = int(self._cfg.get("depth", 20))
        limit    = chess.engine.Limit(time=time_sec, depth=depth)

        with self._lock:
            if not self._ensure_alive():
                return None
            try:
                board = chess.Board(fen)
                info  = self._engine.analyse(board, limit)
            except Exception:
                self._engine = None  # trigger restart on next call
                return None

        score = info.get("score")
        if score is None:
            return None

        eval_cp, eval_mate = worker.score_to_fields(score, board.turn)

        pv_moves = info.get("pv", [])
        b, pv_sans = board.copy(), []
        for m in pv_moves[:15]:
            try:
                pv_sans.append(b.san(m))
                b.push(m)
            except Exception:
                break

        return LiveResult(
            eval_cp=eval_cp,
            eval_mate=eval_mate,
            best_move_san=pv_sans[0] if pv_sans else None,
            pv_json=json.dumps(pv_sans),
            depth=info.get("depth", 0),
            engine_version=self._engine_version,
        )

    def _shutdown(self) -> None:
        if self._engine:
            try:
                self._engine.quit()
            except Exception:
                pass
        self._engine = None


@st.cache_resource(show_spinner="Starting the analysis engine…")
def get_engine_service() -> EngineService | None:
    """Return the singleton EngineService, or None if Stockfish is not found."""
    cfg = config.load_config()
    ie_cfg = cfg.get("interactive_engine", {})
    path = worker.find_engine_path(cfg.get("engine", {}).get("path"))
    if not path:
        return None
    try:
        return EngineService(path, ie_cfg)
    except Exception:
        return None


def batch_running() -> bool:
    """True when the batch worker holds the joblock and its process is alive."""
    info = joblock.status()
    return info is not None and info.alive


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
