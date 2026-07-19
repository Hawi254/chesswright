"""Streamlit server subprocess management -- one of two sibling modules
split out of desktop_app.py (largest-file modularization, 2026-07-17).
Imports resource_dir from desktop_preflight.py (see that file's docstring
for why it lives there and not in desktop_app.py itself).
"""
import os
import pathlib
import socket
import subprocess
import sys
import time

from desktop_preflight import resource_dir


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
    """Runs in a dedicated subprocess (see desktop_app.py's module
    docstring, design #3) -- this is that subprocess's entire job, on ITS
    main thread, so bootstrap.run()'s internal SIGTERM-handler
    registration is safe here.

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
    extra script argument exists or is needed).

    Uses resource_dir() / "desktop_app.py" rather than a bare
    pathlib.Path(__file__).resolve() -- this function now lives in
    desktop_server.py, not desktop_app.py, and the re-invoked process
    must always be desktop_app.py specifically (the file with the
    if __name__ == "__main__": block that actually interprets
    --server-mode), never whichever sibling file this function happens to
    be defined in. resource_dir() returns the shared directory all three
    split files live in either way, so this reconstructs the exact same
    absolute path a literal __file__ reference would have produced back
    when this function was still defined inside desktop_app.py itself."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--server-mode", "--port", str(port), "--config", config_path]
    else:
        cmd = [sys.executable, str(resource_dir() / "desktop_app.py"),
               "--server-mode", "--port", str(port), "--config", config_path]
    return subprocess.Popen(cmd, cwd=str(resource_dir()))
