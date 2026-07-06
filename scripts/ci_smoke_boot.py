#!/usr/bin/env python3
"""CI smoke test: boot the *built* app's Streamlit server and confirm it
actually serves, catching the frozen-bundle failure class that a plain
build-succeeds check can't -- streamlit's own data/static files not being
bundled (the historical "server binds its port but every request to / is a
bare 404", and the earlier PackageNotFoundError on streamlit's own
metadata; see chesswright.spec's notes).

Complements desktop_app.py's `--check-imports` (which validates the
module-import graph inside the frozen interpreter): this one validates the
*serving* layer -- server comes up, health endpoint answers, and `/`
returns real Streamlit HTML, not a 404 shell. Between the two, all four
historically-shipped frozen bugs (missing gi, missing 'chess' dep, missing
BACKEND_MODULE, missing streamlit static) fail CI instead of a pilot.

Runs the app in --server-mode (headless, no pywebview/GTK), so it works on
a CI runner with no display. Usage:

    python scripts/ci_smoke_boot.py path/to/chesswright[.exe]
"""
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

BOOT_TIMEOUT_S = 90   # frozen streamlit cold-start headroom
READ_TIMEOUT_S = 3


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_get(url):
    """Returns (status, body_bytes) or (None, None) if unreachable."""
    try:
        with urllib.request.urlopen(url, timeout=READ_TIMEOUT_S) as resp:
            return resp.status, resp.read()
    except Exception:
        return None, None


def main():
    if len(sys.argv) < 2:
        print("usage: ci_smoke_boot.py path/to/chesswright[.exe]", file=sys.stderr)
        sys.exit(2)
    exe = pathlib.Path(sys.argv[1]).resolve()
    if not exe.exists():
        print(f"FAIL: built executable not found: {exe}", file=sys.stderr)
        sys.exit(1)

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="chesswright-smoke-"))
    # A throwaway config pointing at a fresh (nonexistent) db -- the app
    # self-migrates it on boot (dashboard/_common.get_connections runs
    # migrate.migrate), then lands on the onboarding page with zero games,
    # which is a perfectly valid "the app booted" state.
    cfg = workdir / "config.yaml"
    shutil.copy(REPO_ROOT / "config.yaml", cfg)
    import config as config_mod
    config_mod.set_database_path(str(workdir / "chess.db"), path=cfg)

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    logpath = workdir / "server.log"
    # Child output to a FILE, never a pipe -- a pipe left unread can
    # deadlock the child once its buffer fills (a hard-won lesson, BRIEF
    # §6n), and we want the full log to dump on failure anyway.
    logf = open(logpath, "wb")
    proc = subprocess.Popen(
        [str(exe), "--server-mode", "--port", str(port), "--config", str(cfg)],
        stdout=logf, stderr=subprocess.STDOUT, cwd=str(exe.parent),
    )

    def cleanup():
        logf.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def fail(msg):
        cleanup()
        print(f"FAIL: {msg}", file=sys.stderr)
        print("---- server log ----", file=sys.stderr)
        try:
            sys.stderr.write(logpath.read_text(errors="replace"))
        except Exception:
            pass
        sys.exit(1)

    try:
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        healthy = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                fail(f"server process exited early with code {proc.returncode}")
            status, body = http_get(f"{base}/_stcore/health")
            if status == 200 and body and b"ok" in body.lower():
                healthy = True
                break
            time.sleep(0.5)
        if not healthy:
            fail(f"health endpoint never returned ok within {BOOT_TIMEOUT_S}s")

        # Static/frontend actually served? A bundling gap shows up as a 404
        # or an empty body here, not as a failed health check.
        status, body = http_get(base + "/")
        if status != 200:
            fail(f"GET / returned status {status}, expected 200")
        if not body or b"streamlit" not in body.lower():
            fail("GET / did not return Streamlit's frontend HTML "
                 "(static assets likely not bundled)")

        cleanup()
        print(f"OK: frozen app booted, health ok, and / served Streamlit's "
              f"frontend ({len(body or b'')} bytes) on {base}.")
        shutil.rmtree(workdir, ignore_errors=True)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(f"unexpected error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
