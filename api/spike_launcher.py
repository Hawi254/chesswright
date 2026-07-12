"""Proves the FastAPI spike service can run as its own subprocess and
shut down cleanly -- the same pattern desktop_app.py already uses for
Streamlit, and for the same reason: desktop_app.py's own module docstring
documents that running a server's blocking loop in-process on a
background thread crashed live (bootstrap.run() installs a SIGTERM
handler, and Python only allows signal.signal() from the main thread --
uvicorn does the same signal-handler installation Streamlit's bootstrap
does, so the same crash applies here). Run directly:
    python3 api/spike_launcher.py

Frozen-mode dispatch mirrors desktop_app.py's launch_server_subprocess()/
main() pattern exactly (see that module's docstring for the two prior
designs that crashed before landing on this one): the original
`[sys.executable, "-m", "uvicorn", ...]` re-invocation worked from a
source checkout (sys.executable is a real interpreter there) but
fork-bombed once frozen, because a frozen sys.executable IS the bundled
exe itself -- it has no `-m` handling and just re-runs its own main()
regardless of args, recursively, with no base case (found live: 120+
processes within seconds). The fix: re-invoke this same executable with
a `--api-server-mode` flag instead of `-m uvicorn`; the subprocess's
main() sees the flag and calls uvicorn.run() directly on its own main
thread, in-process -- no interpreter-style CLI args needed, so freezing
can't break it.
"""
import socket
import subprocess
import sys
import time
import pathlib
import urllib.request


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout_s=30):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def launch_api_subprocess(port):
    """Re-invokes this same executable with --api-server-mode. sys.executable
    alone is correct in BOTH modes: a real Python interpreter in a source
    checkout (needs this script's own path passed too) or the bundled exe
    itself when frozen (which already knows its own entry point -- no
    extra script argument exists or is needed)."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--api-server-mode", "--port", str(port)]
    else:
        cmd = [sys.executable, str(pathlib.Path(__file__).resolve()),
               "--api-server-mode", "--port", str(port)]
    return subprocess.Popen(cmd)


def run_api_server_mode(port):
    """Runs in a dedicated subprocess (see launch_api_subprocess) -- this is
    that subprocess's entire job, on ITS main thread, so uvicorn.run()'s
    internal SIGTERM-handler registration is safe here, same reasoning as
    desktop_app.py's run_server_mode().

    Re-invoked directly as a script path (not `-m api.spike_launcher`), so
    Python puts THIS file's own directory (api/) on sys.path[0], not the
    project root -- `import api.main` would fail without adding the
    project root explicitly first. Mirrors desktop_app.py's resource_dir()
    reasoning: sys._MEIPASS is already the bundle's extraction root when
    frozen; this script's grandparent directory is the project root when
    running from source (spike_launcher.py lives in api/, one level below
    root)."""
    if getattr(sys, "frozen", False):
        project_root = pathlib.Path(sys._MEIPASS)
    else:
        project_root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

    import uvicorn
    from api.main import app
    uvicorn.run(app, host="127.0.0.1", port=port)


def main():
    if "--api-server-mode" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
        run_api_server_mode(port)
        return

    port = free_port()
    url = f"http://127.0.0.1:{port}"
    proc = launch_api_subprocess(port)
    try:
        if not wait_for_server(f"{url}/api/overview/headline-stats"):
            print("API server did not start in time.", file=sys.stderr)
            proc.terminate()
            sys.exit(1)

        resp = urllib.request.urlopen(f"{url}/api/overview/headline-stats", timeout=5)
        body = resp.read()
        print("Fetched real data through the subprocess API:", body[:200])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert proc.poll() is not None, "API subprocess did not exit cleanly"
    print(f"Clean shutdown confirmed -- exit code {proc.poll()}")


if __name__ == "__main__":
    main()
