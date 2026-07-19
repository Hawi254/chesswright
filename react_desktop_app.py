#!/usr/bin/env python3
"""
Packaged-app entry point for the pure React+FastAPI build (see
docs/superpowers/specs/2026-07-13-react-frontend-packaging-design.md).
Sibling to desktop_app.py (the Streamlit build's entry point) -- reuses
desktop_app.py's already-proven helpers (ensure_user_data, resource_dir,
free_port, wait_for_server, check_cpu_compat, check_webview2) directly
via import rather than duplicating them; desktop_app.py's own
`if __name__ == "__main__"` guard makes that safe (no side effects on
import).

Process model graduates api/spike_launcher.py's already-proven subprocess
pattern (proves clean start/fetch/shutdown, no orphaned processes) into a
real launcher that also opens a pywebview window, mirroring exactly how
desktop_app.py points pywebview at Streamlit's own local server --
different port/process underneath, same shape. The frozen-executable
re-invocation dispatch (`--api-server-mode` flag, not `-m uvicorn`) is
the same fork-bomb-safe fix desktop_app.py's own module docstring
documents and api/spike_launcher.py already validated -- reused verbatim.

Usage:
    python3 react_desktop_app.py             # GUI launcher mode (default)
    python3 react_desktop_app.py --api-server-mode --port N --config PATH
                                        # internal -- re-invoked by the
                                          launcher itself, not meant to
                                          be run directly
"""
import os
import signal
import subprocess
import sys
import urllib.request

import desktop_app


def launch_api_subprocess(port, config_path):
    """Re-invokes this same executable with --api-server-mode. sys.executable
    alone is correct in BOTH modes: a real Python interpreter in a source
    checkout (needs this script's own path passed too) or the bundled exe
    itself when frozen (which already knows its own entry point -- no
    extra script argument exists or is needed). Mirrors desktop_app.
    launch_server_subprocess() exactly."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--api-server-mode", "--port", str(port), "--config", config_path]
    else:
        cmd = [sys.executable, __file__, "--api-server-mode", "--port", str(port), "--config", config_path]
    return subprocess.Popen(cmd, cwd=str(desktop_app.resource_dir()))


def run_api_server_mode(port, config_path):
    """Runs in a dedicated subprocess (see launch_api_subprocess) -- this
    is that subprocess's entire job, on ITS main thread, so uvicorn.run()'s
    internal SIGTERM-handler registration is safe here, same reasoning as
    desktop_app.py's run_server_mode()."""
    os.environ["CHESSWRIGHT_CONFIG_PATH"] = config_path
    resource_dir = desktop_app.resource_dir()
    sys.path.insert(0, str(resource_dir))
    # api/main.py does `import data` (dashboard/data/*.py's flat-module
    # style, not `import dashboard.data`) -- this used to work by side
    # effect of api/db.py inserting dashboard/ onto sys.path itself
    # (dropped when api/db.py was pointed at connections.py, which lives
    # at the repo root and doesn't need it). Mirrors what every API test
    # file (test_api_static.py etc.) already does explicitly.
    sys.path.insert(0, str(resource_dir / "dashboard"))

    import uvicorn
    from api.main import app
    uvicorn.run(app, host="127.0.0.1", port=port)


def main():
    if "--api-server-mode" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
        config_path = sys.argv[sys.argv.index("--config") + 1]
        run_api_server_mode(port, config_path)
        return

    desktop_app.check_cpu_compat()
    desktop_app.check_webview2()
    user_config = desktop_app.ensure_user_data()
    port = desktop_app.free_port()
    url = f"http://127.0.0.1:{port}"

    proc = launch_api_subprocess(port, str(user_config))

    def _handle_sigterm(signum, frame):
        """External SIGTERM (OS logout, `kill`, a process manager -- not
        the window's own close button, which returns normally from
        webview.start() below and hits the `finally` block) does NOT run
        Python's `finally` blocks: GTK's own C-level main loop doesn't
        hand control back to the Python interpreter on SIGTERM, so
        webview.start() never returns and the api subprocess was left
        orphaned every time (confirmed live, 2026-07-13 -- desktop_app.py
        has this same latent gap, identical try/finally shape, not fixed
        there since that file is out of scope for this plan). Terminate
        the child explicitly, then restore the default disposition and
        re-send ourselves SIGTERM so the process still exits the normal
        way afterward."""
        proc.terminate()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTERM)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        if not desktop_app.wait_for_server(f"{url}/api/overview/headline-stats"):
            print("API server did not start in time.", file=sys.stderr)
            proc.terminate()
            sys.exit(1)

        import webview

        webview.create_window(
            "Chesswright", url, width=1280, height=860,
            background_color="#14181F",
            min_size=(1000, 650),
        )
        webview.start(
            private_mode=False,
            storage_path=str(desktop_app.USER_DATA_DIR / "webview_data"),
        )
    finally:
        # The window closing (webview.start() returning) is the signal to
        # shut the server down -- same reasoning as desktop_app.py's main().
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
