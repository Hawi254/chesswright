"""Unit/integration tests for desktop_app.py's `--run-worker` mode: the
frozen-app analysis-only entrypoint that calls worker.main() in-process,
skipping Streamlit/pywebview entirely (see desktop_app.run_worker_mode()
and its docstring for the CHESSWRIGHT_CONFIG_PATH ordering caveat this
mode has to get right -- config.DEFAULT_CONFIG_PATH is resolved once at
config.py's first import in the process, so the env var must be set
BEFORE ensure_user_data() triggers that first import, not after).

Follows tests/unit/test_desktop_preflight.py's style: real-subprocess
tests for the actual CLI surface, plus in-process monkeypatch tests for
dispatch logic that would be awkward to observe from outside a process.
"""
import os
import pathlib
import subprocess
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from tests.integration.test_eval_reuse_cache import REAL_STOCKFISH


# ---------------------------------------------------------------------------
# In-process dispatch tests
# ---------------------------------------------------------------------------

def test_run_worker_dispatches_argv_and_sets_config_env(tmp_path, monkeypatch):
    """--run-worker's trailing argv (everything after the flag itself) must
    reach worker.main() unchanged, and CHESSWRIGHT_CONFIG_PATH must land on
    ensure_user_data()'s real per-user config path -- not the bundle's
    read-only template -- before worker.main() is called."""
    import desktop_app

    scratch_home = tmp_path / "home"
    scratch_home.mkdir()
    monkeypatch.setattr(desktop_app, "USER_DATA_DIR", scratch_home / ".chesswright")
    monkeypatch.delenv("CHESSWRIGHT_CONFIG_PATH", raising=False)
    monkeypatch.setattr(
        sys, "argv",
        ["chesswright", "--run-worker", "--max-games", "1", "--depth", "4"])

    recorded = {}
    fake_worker = types.SimpleNamespace(
        main=lambda argv: recorded.setdefault("argv", list(argv)))
    monkeypatch.setitem(sys.modules, "worker", fake_worker)

    desktop_app.run_worker_mode()

    assert recorded["argv"] == ["--max-games", "1", "--depth", "4"]
    expected_config = scratch_home / ".chesswright" / "config.yaml"
    assert os.environ["CHESSWRIGHT_CONFIG_PATH"] == str(expected_config)
    assert expected_config.exists()  # ensure_user_data() actually ran


def test_run_worker_never_touches_cpu_or_webview_checks(tmp_path, monkeypatch):
    """--run-worker never boots Streamlit/pywebview, so it must skip
    check_cpu_compat()/check_webview2() entirely -- not just ignore their
    result -- mirroring test_desktop_preflight.py's
    test_probe_skipped_when_sse42_confirmed 'must not be reached' pattern."""
    import desktop_app

    scratch_home = tmp_path / "home"
    scratch_home.mkdir()
    monkeypatch.setattr(desktop_app, "USER_DATA_DIR", scratch_home / ".chesswright")
    monkeypatch.delenv("CHESSWRIGHT_CONFIG_PATH", raising=False)
    monkeypatch.setattr(sys, "argv", ["chesswright", "--run-worker"])

    fake_worker = types.SimpleNamespace(main=lambda argv: None)
    monkeypatch.setitem(sys.modules, "worker", fake_worker)

    def boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("--run-worker mode must not touch this check")
    monkeypatch.setattr(desktop_app, "check_cpu_compat", boom)
    monkeypatch.setattr(desktop_app, "check_webview2", boom)

    desktop_app.main()  # would raise via boom() if either check ran


def test_run_worker_reports_lock_error_cleanly(tmp_path, monkeypatch, capsys):
    """RuntimeError from worker.main() (covers joblock.LockHeldError and the
    'no Stockfish found' case) must surface as a clean one-line stderr
    message and a non-zero exit, not a raw traceback."""
    import desktop_app

    scratch_home = tmp_path / "home"
    scratch_home.mkdir()
    monkeypatch.setattr(desktop_app, "USER_DATA_DIR", scratch_home / ".chesswright")
    # run_worker_mode() sets CHESSWRIGHT_CONFIG_PATH via a raw os.environ
    # assignment (production code, not monkeypatch) -- pre-registering the
    # key with monkeypatch here (even though ensure_user_data() itself is
    # mocked below) makes monkeypatch restore/clear it on teardown instead
    # of leaking a scratch (soon deleted) path into later tests' subprocess
    # environments.
    monkeypatch.delenv("CHESSWRIGHT_CONFIG_PATH", raising=False)

    def fake_main(argv):
        raise RuntimeError("Another analysis run is already in progress (pid 123, started t0).")
    fake_worker = types.SimpleNamespace(main=fake_main)
    monkeypatch.setitem(sys.modules, "worker", fake_worker)
    monkeypatch.setattr(desktop_app, "ensure_user_data", lambda: scratch_home / ".chesswright" / "config.yaml")
    monkeypatch.setattr(sys, "argv", ["chesswright", "--run-worker"])

    with pytest.raises(SystemExit) as exc:
        desktop_app.run_worker_mode()
    assert exc.value.code == 1
    err = capsys.readouterr().err.strip()
    assert err == "Error: Another analysis run is already in progress (pid 123, started t0)."


# ---------------------------------------------------------------------------
# Real subprocess end-to-end tests
# ---------------------------------------------------------------------------

def _seed_scratch_home(tmp_path):
    """Sets up a scratch HOME so USER_DATA_DIR (pathlib.Path.home() /
    '.chesswright', computed at desktop_app.py import time from the
    subprocess's own HOME env var) can never resolve to the real
    ~/.chesswright. Returns (home_dir, env)."""
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home))
    return home, env


def _seed_pending_game(db_path):
    import migrate as migrate_mod
    import ingest
    migrate_mod.migrate(db_path)
    ingest.ingest(pgn_path=str(FIXTURES / "synthetic_games.pgn"), db_path=db_path,
                  player_name="TestPlayerWhite")


@pytest.mark.integration
@pytest.mark.skipif(REAL_STOCKFISH is None, reason="no Stockfish binary on this machine")
def test_run_worker_subprocess_analyzes_a_game_end_to_end(tmp_path):
    """chesswright --run-worker --max-games 1, run as a real subprocess
    against a scratch HOME, must never touch the real ~/.chesswright and
    must actually analyze a game (analysis_status -> 'done')."""
    home, env = _seed_scratch_home(tmp_path)

    # Confirm the HOME redirection actually lands before trusting the rest
    # of this test -- desktop_app.USER_DATA_DIR is computed at import time
    # from pathlib.Path.home().
    check = subprocess.run(
        [sys.executable, "-c",
         "import pathlib; print(pathlib.Path.home())"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert check.stdout.strip() == str(home)

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "desktop_app.py"), "--run-worker",
         "--max-games", "1", "--depth", "4", "--multipv", "1", "--threads", "1",
         "--engine-path", REAL_STOCKFISH],
        capture_output=True, text=True, env=env, timeout=180, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    user_config = home / ".chesswright" / "config.yaml"
    assert user_config.exists()

    # The subprocess's own config.yaml points database.path at the scratch
    # USER_DATA_DIR (ensure_user_data()'s job) -- but this test needs a
    # PENDING game there first, which a brand-new install never has. Seed
    # one now, then re-run --run-worker against that same scratch DB.
    import yaml
    cfg = yaml.safe_load(user_config.read_text())
    db_path = cfg["database"]["path"]
    _seed_pending_game(db_path)

    proc2 = subprocess.run(
        [sys.executable, str(REPO_ROOT / "desktop_app.py"), "--run-worker",
         "--max-games", "1", "--depth", "4", "--multipv", "1", "--threads", "1",
         "--engine-path", REAL_STOCKFISH],
        capture_output=True, text=True, env=env, timeout=180, cwd=str(REPO_ROOT),
    )
    assert proc2.returncode == 0, f"stdout={proc2.stdout}\nstderr={proc2.stderr}"

    import sqlite3
    conn = sqlite3.connect(db_path)
    statuses = [r[0] for r in conn.execute("SELECT analysis_status FROM games").fetchall()]
    conn.close()
    assert "done" in statuses, f"expected at least one game analyzed, got {statuses}"


@pytest.mark.integration
def test_run_worker_subprocess_lock_collision_is_clean(tmp_path, monkeypatch):
    """A pre-held joblock (e.g. a GUI batch already running, or another
    --run-worker) must make --run-worker fail with a clean one-line stderr
    message and non-zero exit, not a traceback -- proving the RuntimeError
    catch path in run_worker_mode() for real."""
    home, env = _seed_scratch_home(tmp_path)

    # Bootstrap the scratch user config directly (same call desktop_app.py's
    # own main() makes) so a pending game can be seeded into it before the
    # subprocess under test runs -- no --run-worker call yet, so nothing
    # touches the lock at this point.
    import desktop_app as desktop_app_mod
    user_data_dir = home / ".chesswright"
    monkeypatch.setattr(desktop_app_mod, "USER_DATA_DIR", user_data_dir)
    monkeypatch.setenv("CHESSWRIGHT_CONFIG_PATH", str(user_data_dir / "config.yaml"))
    user_config = desktop_app_mod.ensure_user_data()

    import yaml
    cfg = yaml.safe_load(user_config.read_text())
    db_path = cfg["database"]["path"]
    _seed_pending_game(db_path)

    # Hold the lock ourselves, at the same LOCK_PATH the subprocess's own
    # config resolves to (worker.lock next to the scratch config.yaml) --
    # same monkeypatch-the-lock-path style TestRealEngineCacheRoundTrip
    # already uses in test_eval_reuse_cache.py, just done directly since
    # this test needs the lock held BY THIS PROCESS while a separate
    # subprocess tries and fails to acquire it.
    import joblock
    lock_path = user_data_dir / "worker.lock"
    monkeypatch.setattr(joblock, "LOCK_PATH", lock_path)
    joblock.acquire()
    try:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "desktop_app.py"), "--run-worker",
             "--max-games", "1"],
            capture_output=True, text=True, env=env, timeout=60, cwd=str(REPO_ROOT),
        )
    finally:
        joblock.release()

    assert proc.returncode != 0
    assert "Traceback" not in proc.stderr
    assert "Error: Another analysis run is already in progress" in proc.stderr
