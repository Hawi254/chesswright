#!/usr/bin/env python3
"""
Phase C packaged-app entry point: launches the Streamlit dashboard as a
background server and shows it inside a native pywebview window, instead
of a browser tab. This is the ONLY entry point that does this -- the
existing dev workflow (`streamlit run dashboard/app.py`, used throughout
Phases A/B) is untouched and still works exactly as before.

User-data location: a packaged build's own install directory can't be
trusted as a place to keep a growing personal database -- it may be
read-only (Windows Program Files), or for a --onefile PyInstaller build,
a temporary extraction directory wiped clean between runs. Instead this
writes to ~/.chesswright/, the same per-user data directory
api_key_store.py already established for the API key fallback file --
one convention, not two. On first launch, the bundled config.yaml
template is copied there (database.path rewritten to an absolute path
in that same directory) and never touched again; config.py's
CHESSWRIGHT_CONFIG_PATH env var redirects every config-loading script
to read from that copy instead of the bundle's read-only one.

Streamlit server architecture -- the trickiest part of this file, gone
through two wrong designs before this one, kept here so the reasoning
isn't lost:
  1. `subprocess.Popen([sys.executable, "-m", "streamlit", "run", ...])`
     -- works from a source checkout (sys.executable is a real Python
     interpreter there) but breaks once frozen: sys.executable in a
     frozen build IS the single bundled exe, which has no `-m streamlit`
     support.
  2. Calling `streamlit.web.bootstrap.run()` in-process, on a background
     thread, with pywebview on the main thread -- confirmed LIVE this
     crashes: bootstrap.run() registers a SIGTERM handler internally,
     and Python only allows `signal.signal()` from the main thread of
     the main interpreter, full stop, regardless of framework.
  3. **This file's actual approach**: re-invoke THIS SAME executable as
     a subprocess with a `--server-mode` flag (sys.executable alone is
     enough in both dev and frozen mode -- no separate "-m streamlit" or
     second script path needed). The subprocess's main() sees the flag
     and calls bootstrap.run() directly on ITS OWN main thread (no
     threading issue, since that process does nothing else). The
     original launcher process's main thread stays free for pywebview's
     GTK main loop, which Linux requires running on the main thread.
     Standard PyInstaller pattern for "one exe, multiple entry-point
     behaviors," not invented for this specifically.

Usage:
    python3 desktop_app.py             # GUI launcher mode (default)
    python3 desktop_app.py --server-mode --port N --config PATH
                                        # internal -- re-invoked by the
                                          launcher itself, not meant to
                                          be run directly
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import pathlib

USER_DATA_DIR = pathlib.Path.home() / ".chesswright"


def resource_dir():
    """Where the bundled (read-only) app resources live: the PyInstaller
    bundle's extraction directory when frozen, or this file's own
    directory when running from source."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).resolve().parent


def ensure_user_data():
    """First-launch setup: copies the bundled config.yaml template into
    USER_DATA_DIR and points its database.path at that same directory.
    A no-op on every later launch (config.yaml already exists -- never
    overwritten, since it may hold a real configured username/settings
    by then)."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    user_config = USER_DATA_DIR / "config.yaml"
    if not user_config.exists():
        shutil.copy(resource_dir() / "config.yaml", user_config)
        sys.path.insert(0, str(resource_dir()))
        import config as config_module
        config_module.set_database_path(str(USER_DATA_DIR / "chess.db"), path=user_config)
    return user_config


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout_s=30):
    import urllib.request
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def run_server_mode(port, config_path):
    """Runs in a dedicated subprocess (see module docstring, design #3)
    -- this is that subprocess's entire job, on ITS main thread, so
    bootstrap.run()'s internal SIGTERM-handler registration is safe here.

    flag_options keys use UNDERSCORES, not the dotted config-option names
    they actually represent (server.port, etc.) -- confirmed by reading
    bootstrap.load_config_options()'s real source: it does
    `name.replace("_", ".")` on every key. Got this wrong on the first
    attempt (used dotted keys directly) and it silently fell back to
    Streamlit's default port 8501 instead of the one this script chose,
    with no error -- caught live by checking which port the server
    actually bound to, not assumed correct from the API shape alone.

    Also calling bootstrap.load_config_options() explicitly before run()
    -- confirmed by reading streamlit/web/cli.py's own real call sequence
    that bootstrap.run() does NOT apply flag_options itself on startup;
    its internal _install_config_watchers() only reacts to LATER config
    FILE changes, not the initial flags passed in."""
    os.environ["CHESSWRIGHT_CONFIG_PATH"] = config_path
    app_path = str(resource_dir() / "dashboard" / "app.py")
    from streamlit.web import bootstrap
    flag_options = {
        "server_headless": True,
        "server_port": port,
        "server_address": "127.0.0.1",
        "browser_gatherUsageStats": False,
        "global_developmentMode": False,
    }
    bootstrap.load_config_options(flag_options=flag_options)
    bootstrap.run(app_path, False, [], flag_options)


def launch_server_subprocess(port, config_path):
    """Re-invokes this same executable with --server-mode. sys.executable
    alone is correct in BOTH modes: a real Python interpreter in a source
    checkout (needs this script's own path passed too) or the bundled exe
    itself when frozen (which already knows its own entry point -- no
    extra script argument exists or is needed)."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--server-mode", "--port", str(port), "--config", config_path]
    else:
        cmd = [sys.executable, str(pathlib.Path(__file__).resolve()),
               "--server-mode", "--port", str(port), "--config", config_path]
    return subprocess.Popen(cmd, cwd=str(resource_dir()))


def main():
    if "--server-mode" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
        config_path = sys.argv[sys.argv.index("--config") + 1]
        run_server_mode(port, config_path)
        return

    user_config = ensure_user_data()
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    proc = launch_server_subprocess(port, str(user_config))
    try:
        if not wait_for_server(url):
            print("Dashboard server did not start in time.", file=sys.stderr)
            proc.terminate()
            sys.exit(1)

        import webview
        webview.create_window("Chesswright", url, width=1280, height=860)
        webview.start()
    finally:
        # The window closing (webview.start() returning) is the signal to
        # shut the server down -- it has no reason to keep running once
        # nothing is displaying it, and leaving it alive would silently
        # accumulate orphaned server processes across repeated launches.
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
