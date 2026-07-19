"""Streamlit-free on-demand-Stockfish state, shared by the Streamlit
dashboard (via dashboard/live_engine.py's thin get_engine_service()
wrapper) and the FastAPI service (api/main.py's engine-status endpoint)
directly.

Extracted from dashboard/live_engine.py (2026-07-13) so api/main.py's
`/api/overview/engine-status` endpoint doesn't pull in streamlit merely
by importing this module -- see docs/superpowers/specs/2026-07-13-
react-frontend-packaging-design.md. EngineService/LiveResult/
get_engine_service/get_engine_status_summary have zero streamlit calls in
their own bodies in the original file; only get_engine_service()'s
@st.cache_resource decorator did, replaced below with a plain
process-wide singleton (identical caching behavior, including caching a
legitimate None result -- see the _UNSET sentinel).

dashboard/live_engine.py keeps everything that actually touches
st.session_state/st.spinner/st.checkbox/st.caption
(render_confirm_toggle, get_or_analyse_position) -- those stay
Streamlit-only and unmoved.
"""
import atexit
import dataclasses
import json
import threading

import chess
import chess.engine

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


_popen_thread_patch_lock = threading.Lock()


def _popen_uci_daemonized(path: str) -> chess.engine.SimpleEngine:
    """chess.engine.SimpleEngine.popen_uci(path), forcing the background
    asyncio-loop thread it spawns (chess.engine.run_in_background,
    threading.Thread(target=background, name=name).start(), no explicit
    daemon= kwarg) to be a daemon thread.

    Root cause this works around (confirmed live 2026-07-13, reproduced
    in isolation outside any of this project's own code): a Python
    Thread's daemon flag defaults to its CREATING thread's daemon status
    when not passed explicitly. popen_uci() is normally called from the
    main thread (non-daemon), so the engine's background loop thread
    inherits non-daemon too. At interpreter exit, CPython's
    threading._shutdown() blocks joining every non-daemon thread BEFORE
    atexit callbacks run -- so EngineService._shutdown()'s atexit-
    registered eng.quit()/close() (the only thing that ever asks that
    background thread to stop) never even starts executing, and the
    whole process hangs forever. Forcing the thread daemon here sidesteps
    threading._shutdown()'s join entirely, so atexit runs normally and
    quit() succeeds against the still-alive daemon thread."""
    with _popen_thread_patch_lock:
        orig_init = threading.Thread.__init__

        def _daemon_init(self, *args, **kwargs):
            kwargs.setdefault("daemon", True)
            orig_init(self, *args, **kwargs)

        threading.Thread.__init__ = _daemon_init
        try:
            return chess.engine.SimpleEngine.popen_uci(path)
        finally:
            threading.Thread.__init__ = orig_init


class EngineService:
    """Wraps a persistent Stockfish subprocess for on-demand analysis.

    Thread-safe via a single threading.Lock.  Restarts on failure up to
    _MAX_RESTARTS times.  Registers an atexit handler so the subprocess
    doesn't linger when the process exits.
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
        self._engine = _popen_uci_daemonized(self._path)
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


_service_started = False

_UNSET = object()
_cached_service = _UNSET
_cache_lock = threading.Lock()


def get_engine_service() -> EngineService | None:
    """Process-wide singleton, including caching a legitimate None result
    (Stockfish not found) -- mirrors what the original @st.cache_resource
    decorator did (Streamlit caches whatever a decorated function returns,
    None included, until .clear()). _UNSET (not None) is the "never
    computed yet" sentinel so a real None doesn't trigger a rebuild on
    every call."""
    global _cached_service, _service_started
    if _cached_service is not _UNSET:
        return _cached_service
    with _cache_lock:
        if _cached_service is not _UNSET:
            return _cached_service
        _service_started = True
        cfg = config.load_config()
        ie_cfg = cfg.get("interactive_engine", {})
        path = worker.find_engine_path(cfg.get("engine", {}).get("path"))
        if not path:
            _cached_service = None
            return _cached_service
        try:
            _cached_service = EngineService(path, ie_cfg)
        except Exception:
            _cached_service = None
        return _cached_service


def clear_engine_service_cache():
    """Test hook / settings-change hook: get_engine_service() is a
    process-wide singleton, so this is the explicit way to force a
    reconnect. dashboard/live_engine.py's get_engine_service.clear()
    attribute (see that module) delegates here -- it's the same single
    source of truth dashboard/settings_view.py's existing call sites
    already expect (force a fresh EngineService after the user changes
    the engine path)."""
    global _cached_service
    _cached_service = _UNSET


def get_engine_status_summary() -> dict:
    """Cheap, read-only status for display (Overview's status strip, both
    the Streamlit and React versions). Only reports on an engine ALREADY
    started elsewhere (e.g. Game Detail's interactive analysis panel) --
    never calls get_engine_service() as the first caller, since that's
    what actually constructs a real Stockfish subprocess on its
    first-ever invocation. Viewing Overview must never be what eagerly
    starts the engine for a user who never opened an interactive-analysis
    feature."""
    if not _service_started:
        return {"connected": False, "version": None}
    service = get_engine_service()
    if service is None:
        return {"connected": False, "version": None}
    return {"connected": not service._dead, "version": service._engine_version or None}
