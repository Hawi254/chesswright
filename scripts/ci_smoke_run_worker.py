#!/usr/bin/env python3
"""CI smoke test: run the *built* app's `--run-worker` mode against a real
Stockfish and confirm it actually analyzes a game end to end, catching the
frozen-bundle failure class a plain build-succeeds check can't -- unlike
--server-mode (ci_smoke_boot.py) or --check-imports, --run-worker takes a
DIFFERENT import/execution path through the frozen bundle: no Streamlit
bootstrap at all, straight into desktop_app.run_worker_mode() ->
worker.main() -> worker.run(), so PyInstaller's static analysis missing
something on THAT path (e.g. a joblock/chess.engine import gap) would only
ever surface here, not in the other two smoke checks.

Complements ci_smoke_boot.py (server-mode) and --check-imports: between the
three, the frozen build's three real entry-point behaviors (full GUI
server, analysis-only worker, static import graph) are all exercised.

Never touches the real ~/.chesswright -- every invocation gets its own
scratch HOME so USER_DATA_DIR (computed at desktop_app.py import time from
pathlib.Path.home()) can't resolve anywhere near a real install.

Usage:
    python scripts/ci_smoke_run_worker.py path/to/chesswright[.exe]
"""
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT))

RUN_TIMEOUT_S = 180  # cold Stockfish start + a couple of shallow-depth games' worth of headroom


def main():
    if len(sys.argv) < 2:
        print("usage: ci_smoke_run_worker.py path/to/chesswright[.exe]", file=sys.stderr)
        sys.exit(2)
    exe = pathlib.Path(sys.argv[1]).resolve()
    if not exe.exists():
        print(f"FAIL: built executable not found: {exe}", file=sys.stderr)
        sys.exit(1)

    from worker import find_engine_path
    stockfish = find_engine_path(None)
    if not stockfish:
        print("FAIL: no system Stockfish found on this machine -- install one "
              "(e.g. `sudo apt install stockfish`) to run this smoke test.",
              file=sys.stderr)
        sys.exit(1)

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="chesswright-smoke-worker-"))
    scratch_home = workdir / "home"
    scratch_home.mkdir()
    env = {"HOME": str(scratch_home), "PATH": __import__("os").environ.get("PATH", "")}

    def fail(msg, proc=None):
        print(f"FAIL: {msg}", file=sys.stderr)
        if proc is not None:
            print("---- stdout ----", file=sys.stderr)
            print(proc.stdout, file=sys.stderr)
            print("---- stderr ----", file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
        shutil.rmtree(workdir, ignore_errors=True)
        sys.exit(1)

    try:
        # 1. First launch: no pending games yet, just bootstraps
        #    ~/.chesswright/config.yaml (via ensure_user_data()) so the
        #    scratch database.path can be discovered and seeded.
        first = subprocess.run(
            [str(exe), "--run-worker", "--max-games", "1"],
            capture_output=True, text=True, env=env, timeout=RUN_TIMEOUT_S,
            cwd=str(exe.parent),
        )
        if first.returncode != 0:
            fail("first --run-worker call (bootstrapping the scratch config) "
                 f"exited {first.returncode}", first)

        user_config = scratch_home / ".chesswright" / "config.yaml"
        if not user_config.exists():
            fail(f"expected {user_config} to exist after --run-worker bootstrapped it")

        import yaml
        cfg = yaml.safe_load(user_config.read_text())
        db_path = pathlib.Path(cfg["database"]["path"])

        # 2. Seed exactly one pending game into that same scratch database.
        import migrate as migrate_mod
        import ingest
        migrate_mod.migrate(str(db_path))
        ingest.ingest(pgn_path=str(FIXTURES / "synthetic_games.pgn"), db_path=str(db_path),
                      player_name="TestPlayerWhite")

        pending_before = sqlite3.connect(db_path).execute(
            "SELECT COUNT(*) FROM games WHERE analysis_status='pending'"
        ).fetchone()[0]
        if pending_before == 0:
            fail("expected at least one pending game after seeding, found none")

        # 3. Run --run-worker for real against the seeded scratch database.
        second = subprocess.run(
            [str(exe), "--run-worker", "--max-games", "1", "--depth", "4",
             "--multipv", "1", "--threads", "1", "--engine-path", stockfish],
            capture_output=True, text=True, env=env, timeout=RUN_TIMEOUT_S,
            cwd=str(exe.parent),
        )
        if second.returncode != 0:
            fail(f"--run-worker exited {second.returncode}", second)

        conn = sqlite3.connect(db_path)
        statuses = [r[0] for r in conn.execute("SELECT analysis_status FROM games").fetchall()]
        conn.close()
        if "done" not in statuses:
            fail(f"expected at least one game with analysis_status='done', got {statuses}", second)

        print(f"OK: frozen --run-worker analyzed a game end to end "
              f"(statuses now {statuses}) against a scratch HOME at {scratch_home}, "
              "never touching the real ~/.chesswright.")
        shutil.rmtree(workdir, ignore_errors=True)
        sys.exit(0)
    except subprocess.TimeoutExpired as exc:
        fail(f"a subprocess call timed out after {RUN_TIMEOUT_S}s: {exc}")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(f"unexpected error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
