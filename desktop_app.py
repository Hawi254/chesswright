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
    python3 desktop_app.py --run-worker [worker.py flags...]
                                        # analysis-only, no GUI/browser --
                                          the real max-throughput path for
                                          a packaged (frozen) install; see
                                          run_worker_mode() below.

Split (largest-file modularization, 2026-07-17) into two sibling
modules -- desktop_preflight.py (CPU-compat + CI smoke-import checks,
plus resource_dir() and the WEBVIEW2_URL/ISSUES_URL constants -- see
that file's own docstring for why those live there and not here) and
desktop_server.py (Streamlit server subprocess management) -- this file
keeps resource_dir's own single genuinely-local caller
(ensure_user_data), the NativeApi class, run_worker_mode(), and main(),
importing the two new siblings normally (this file IS chesswright.spec's
literal Analysis(["desktop_app.py"]) entry point, so PyInstaller's
static analysis traces these imports automatically -- no spec change
needed, unlike worker.py/analytics.py's siblings).
"""
import json
import os
import shutil
import subprocess
import sys
import pathlib
import webbrowser

from desktop_preflight import (
    resource_dir, run_check_imports, run_preflight_imports,
    check_cpu_compat, check_webview2,
)
from desktop_server import free_port, wait_for_server, run_server_mode, launch_server_subprocess

USER_DATA_DIR = pathlib.Path.home() / ".chesswright"

RELEASES_URL = "https://github.com/Hawi254/chesswright/releases/latest"


def ensure_user_data():
    """First-launch setup: copies the bundled config.yaml template into
    USER_DATA_DIR and points its database.path at that same directory.
    The copy itself is a no-op on every later launch (config.yaml already
    exists -- never overwritten, since it may hold a real configured
    username/settings by then), but backfill_missing_keys() still runs
    every launch to pick up any config key a later release added to the
    template after this user's config.yaml was first created -- see its
    own docstring for why that's necessary even though the copy isn't."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    user_config = USER_DATA_DIR / "config.yaml"
    sys.path.insert(0, str(resource_dir()))
    import config as config_module
    if not user_config.exists():
        shutil.copy(resource_dir() / "config.yaml", user_config)
        config_module.set_database_path(str(USER_DATA_DIR / "chess.db"), path=user_config)
    config_module.backfill_missing_keys(path=user_config)
    return user_config


class NativeApi:
    """Exposed to the Streamlit page's JS via create_window(js_api=...).

    Live-verified (BRIEF.md §6h): window.top.pywebview.api.<method>(),
    called from JS inside a Streamlit custom-component iframe
    (dashboard/components/native_file_picker/), reaches these methods
    even though that page is served by the separate server subprocess,
    not this launcher process -- js_api is bound to the window, not to
    whichever process served the page's HTML.

    Each method hardcodes its own dialog type/filter server-side --
    nothing about which dialog opens or what it filters to is ever
    chosen from the JS/web-content side, deliberately, since that
    content originates from a page this app renders (not truly
    untrusted), but there's no reason to give it more control than it
    needs. Only ever returns a path string, never file bytes -- the
    existing copy-into-this-app's-data-dir step at each call site stays
    responsible for that, unchanged.
    """

    def pick_engine_file(self):
        # Local import, not module-level: matches main()'s own deferred
        # `import webview` (kept out of the --server-mode subprocess,
        # which has no GUI and no reason to need GTK/webview at all).
        import webview
        result = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG)
        return result[0] if result else None

    def pick_database_file(self):
        import webview
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("SQLite database (*.db)", "All files (*.*)"),
        )
        return result[0] if result else None


def run_worker_mode():
    """chesswright --run-worker [any worker.py flag: --max-games/--depth/...]
    -- runs an analysis batch directly, no Streamlit/pywebview boot at all.
    The actual max-throughput path for a PACKAGED user (unlike the
    Analysis Jobs page's CLI-throughput tip, which only works from a
    source checkout where python3 worker.py exists as a real script) --
    see BRIEF.md for the finding that motivated this. Reuses run_server_mode()'s
    exact CHESSWRIGHT_CONFIG_PATH env-var mechanism (config.py already reads
    it) so worker.main()'s own --config=None default resolves to this
    user's real ~/.chesswright/config.yaml, not a meaningless bundle-relative
    path -- zero new config-resolution plumbing needed.

    Ordering caveat found live (not in the original sketch of this
    function): config.DEFAULT_CONFIG_PATH is a plain module-level constant,
    resolved from CHESSWRIGHT_CONFIG_PATH once at config.py's *first*
    import in this process, not re-read later. ensure_user_data() itself
    is what imports `config` for the first time -- so the env var has to
    be set BEFORE calling it, not after, or worker.main()'s --config=None
    default silently resolves to the bundled read-only template instead
    of this user's real config. USER_DATA_DIR/"config.yaml" is exactly the
    path ensure_user_data() computes and returns internally, so it can be
    set here without waiting on that call."""
    user_config = USER_DATA_DIR / "config.yaml"
    os.environ["CHESSWRIGHT_CONFIG_PATH"] = str(user_config)
    ensure_user_data()
    sys.path.insert(0, str(resource_dir()))
    import worker
    idx = sys.argv.index("--run-worker")
    worker_argv = sys.argv[idx + 1:]
    try:
        worker.main(worker_argv)
    except RuntimeError as e:
        # Covers joblock.LockHeldError (a GUI batch or another --run-worker
        # is already running -- joblock.acquire() inside worker.run() raises
        # this) and the "no Stockfish found" case worker.run() also raises
        # as a bare RuntimeError -- both already carry a clean, human-
        # readable message (see joblock.LockHeldError.__str__ and worker.run()'s
        # own raise site), so a packaged user sees that message on stderr and
        # a clean non-zero exit, not a raw Python traceback.
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if "--check-imports" in sys.argv:
        run_check_imports()
        return
    if "--preflight-imports" in sys.argv:
        run_preflight_imports()
        return
    if "--server-mode" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
        config_path = sys.argv[sys.argv.index("--config") + 1]
        run_server_mode(port, config_path)
        return
    if "--run-worker" in sys.argv:
        run_worker_mode()
        return

    check_cpu_compat()
    check_webview2()
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
        from webview.menu import Menu, MenuAction, MenuSeparator

        window = webview.create_window(
            "Chesswright", url, width=1280, height=860,
            # Matches dashboard/theme.py's BG / .streamlit/config.toml's
            # backgroundColor -- avoids a plain-white paint showing through
            # before Streamlit's own CSS loads.
            background_color="#14181F",
            # Below this, the sidebar + wide multi-column layout (e.g. the
            # Overview page's 4-tile metric row) has nowhere to go.
            min_size=(1000, 650),
            # Bridges dashboard/components/native_file_picker/ to a real
            # native OS file dialog -- see NativeApi's docstring.
            js_api=NativeApi(),
        )

        def go_to(url_path):
            """Drives real navigation via the same MPA url_path routing
            dashboard/app.py's st.switch_page uses internally -- just
            triggered from the launcher process instead of from a widget
            inside the page. Known, accepted gap: no guard against firing
            mid-operation (e.g. a DB import or engine validation in
            flight) -- not worth new cross-process synchronization for a
            menu-click edge case without evidence anyone hits it."""
            window.evaluate_js(f"window.top.location.href = {json.dumps(url + '/' + url_path)}")

        menu = [
            Menu("File", [
                MenuAction("Sync Games", lambda: go_to("setup")),
                MenuAction("Settings", lambda: go_to("settings")),
                MenuSeparator(),
                MenuAction("Quit", window.destroy),
            ]),
            Menu("Help", [
                # Always the system browser, never evaluate_js navigation --
                # the webview itself should never load a non-127.0.0.1 origin.
                MenuAction("Check for Updates", lambda: webbrowser.open(RELEASES_URL)),
            ]),
        ]

        webview.start(
            # Default (private_mode=True) discards local storage on every
            # launch -- confirmed via pywebview's own start() docstring --
            # so any UI state Streamlit's frontend keeps client-side
            # (e.g. sidebar collapsed/expanded) resets every time the app
            # opens instead of persisting like an installed app would.
            # Stored alongside this app's other per-user state.
            private_mode=False,
            storage_path=str(USER_DATA_DIR / "webview_data"),
            menu=menu,
        )
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
