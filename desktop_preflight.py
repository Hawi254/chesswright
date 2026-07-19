"""Launch preflights (BRIEF S6z/S6aa): CPU-compatibility probing (the
compiled-dep SSE4.2/x86-64-v2 baseline check) and the CI smoke-import
check -- two of the two sibling modules split out of desktop_app.py
(largest-file modularization, 2026-07-17). Also holds resource_dir()
(needed by this file, desktop_server.py, AND desktop_app.py itself --
see this task's plan header for why it can't stay in desktop_app.py
without creating a circular import) and WEBVIEW2_URL/ISSUES_URL (each
used only inside a function that moved here, not by anything that stays
in desktop_app.py).
"""
import importlib
import os
import platform
import subprocess
import sys
import pathlib
import webbrowser

WEBVIEW2_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"

ISSUES_URL = "https://github.com/Hawi254/chesswright/issues"

# Every compiled dependency whose import can hard-crash (not raise) on a
# CPU below the SSE4.2/x86-64-v2 baseline. pyarrow is the known offender
# (Arrow's official wheels require SSE4.2 and die with SIGILL, which an
# in-process try/except can NEVER catch -- the process just dies); duckdb's
# floor is undocumented, so it's probed rather than assumed safe. numpy
# first: its failure mode is a readable RuntimeError, so if the whole
# baseline is missing the probe's stderr says so in plain words.
PREFLIGHT_MODULES = ("numpy", "pyarrow", "duckdb", "pandas")


def resource_dir():
    """Where the bundled (read-only) app resources live: the PyInstaller
    bundle's extraction directory when frozen, or this file's own
    directory when running from source. Safe to define here rather than
    in desktop_app.py: it only ever computes the PARENT directory of
    whichever file it's defined in, and desktop_app.py/desktop_preflight.py/
    desktop_server.py are all siblings in the same directory, so the
    result is identical regardless of which of the three holds this
    function."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).resolve().parent


def run_check_imports():
    """CI smoke mode: import every module the dashboard loads at runtime,
    inside THIS (in CI: frozen) interpreter, and exit non-zero if any is
    missing/unimportable.

    This is the direct guard against the recurring frozen-bundle failure
    class (BRIEF §6n): a backend module dropped from chesswright.spec's
    BACKEND_MODULES list, or a third-party dependency never collected,
    builds cleanly and only crashes when dashboard/app.py's own top-level
    imports run at first page load -- which the build matrix's path-grep
    can't see and, historically, a pilot tester found first. dashboard/
    app.py itself is deliberately NOT imported (it runs st.navigation/
    pg.run() at module scope, which needs a live Streamlit runtime); every
    module app.py imports IS, plus the whole backend and the data package,
    so a missing bundled file surfaces here as ImportError instead of at
    runtime.

    The module set is discovered by scanning the bundled tree (root *.py =
    backend, dashboard/*.py = views/helpers), not hardcoded, so a newly
    added view is covered automatically without editing this check."""
    root = resource_dir()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "dashboard"))
    # Some modules read config at import; point at the bundled read-only
    # copy so that resolves rather than falling back unpredictably.
    os.environ.setdefault("CHESSWRIGHT_CONFIG_PATH", str(root / "config.yaml"))

    # desktop_app: this launcher itself (already running). app: needs a
    # live Streamlit runtime at import (pg.run()), tested by the live-boot
    # smoke check instead.
    skip = {"desktop_app", "app"}
    backend = sorted(p.stem for p in root.glob("*.py") if p.stem not in skip)
    views = sorted(p.stem for p in (root / "dashboard").glob("*.py")
                   if p.stem not in skip)
    targets = backend + views + ["data", "claude_narrative"]  # packages the *.py glob above can't see

    failures = []
    for name in targets:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 -- report every failure, not just ImportError
            failures.append((name, f"{type(exc).__name__}: {exc}"))

    if failures:
        print("FAIL: frozen-bundle import check found unimportable modules:",
              file=sys.stderr)
        for name, err in failures:
            print(f"  - {name}: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: all {len(targets)} runtime modules imported cleanly "
          f"({len(backend)} backend, {len(views)} dashboard, 1 data package).")
    sys.exit(0)


def run_preflight_imports():
    """Internal mode (--preflight-imports): imports each compiled dep the
    dashboard needs, then exits 0. Run as a SUBPROCESS by
    check_cpu_compat() -- an unsupported-CPU crash here is a SIGILL /
    STATUS_ILLEGAL_INSTRUCTION that kills the whole process, which is
    exactly why it must happen in a child the launcher can observe, not
    in the launcher itself."""
    for name in PREFLIGHT_MODULES:
        __import__(name)
    print("OK: compiled-dependency preflight imports succeeded.")
    sys.exit(0)


def _sse42_confirmed():
    """Best-effort fast path: True only when this CPU DEFINITELY has
    SSE4.2 (the load-bearing x86-64-v2 feature for pyarrow's wheels), so
    the subprocess probe can be skipped on the ~every-modern-machine
    case. Anything uncertain returns False and pays the probe instead --
    a few seconds on launch beats a silent dead process."""
    try:
        if platform.machine().lower() not in ("x86_64", "amd64"):
            return True  # arm64 etc.: the x86 baseline question doesn't apply
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo") as fh:
                for line in fh:
                    if line.startswith("flags"):
                        return " sse4_2" in line
            return False
        if sys.platform == "win32":
            import ctypes
            # PF_SSE4_2_INSTRUCTIONS_AVAILABLE = 38. Only recognized from
            # Windows 10 20H1 on; older Windows returns FALSE for unknown
            # feature ids, which lands on the safe run-the-probe path.
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(38))
        return False
    except Exception:
        return False


def _preflight_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--preflight-imports"]
    return [sys.executable, str(resource_dir() / "desktop_app.py"),
            "--preflight-imports"]


def check_cpu_compat():
    """Preflight for the v0.1.16 Windows pilot crash class: compiled deps
    built against a CPU baseline (x86-64-v2 / SSE4.2) the machine lacks.

    Two layers, because the failure modes differ:
    - numpy raises a readable RuntimeError at import -- catchable
      in-process, checked directly below. Pinned to 1.26.4 (old
      baseline) in requirements.txt, so this should never fire unless
      the pin is lifted.
    - pyarrow (required by pandas 3, imported at pandas import time) and
      possibly duckdb hard-crash with an ILLEGAL INSTRUCTION on a
      pre-SSE4.2 CPU -- that kills the process outright, so it can only
      be observed from OUTSIDE: a --preflight-imports subprocess, run
      only when the fast CPU-flag check can't confirm SSE4.2. If the
      probe dies, one retry with ARROW_USER_SIMD_LEVEL=NONE (pyarrow's
      documented no-SIMD mode) -- if that survives, the app runs in
      compatibility mode instead of refusing; if not, one readable
      message instead of a vanishing window."""
    try:
        import numpy  # noqa: F401
    except RuntimeError as exc:
        if "baseline" not in str(exc).lower():
            raise
        print(
            "Chesswright cannot run on this computer: its processor does "
            "not support the CPU instructions this build was compiled "
            f"with.\n(Details: {exc})\n"
            f"Please report this at {ISSUES_URL} so we know "
            "which hardware to support.",
            file=sys.stderr,
        )
        sys.exit(1)

    if _sse42_confirmed():
        return

    cmd = _preflight_cmd()
    try:
        probe = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception:
        return  # the probe mechanism itself failing is not a verdict on the CPU
    if probe.returncode == 0:
        return

    retry = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180,
        env=dict(os.environ, ARROW_USER_SIMD_LEVEL="NONE"),
    )
    if retry.returncode == 0:
        # Inherited by the server subprocess via launch_server_subprocess.
        os.environ["ARROW_USER_SIMD_LEVEL"] = "NONE"
        print(
            "Note: this processor predates some CPU features this build "
            "was compiled with; running in a slower compatibility mode."
        )
        return

    stderr_tail = "\n".join((retry.stderr or probe.stderr or "").splitlines()[-4:])
    print(
        "Chesswright cannot run on this computer: its processor does not "
        "support the CPU instructions (SSE4.2 / x86-64-v2) some of this "
        "build's components were compiled with.\n"
        f"(Details: preflight import check failed; {stderr_tail})\n"
        f"Please report this at {ISSUES_URL} so we know "
        "which hardware to support.",
        file=sys.stderr,
    )
    sys.exit(1)


def check_webview2():
    """Windows-only preflight: pywebview needs the Edge WebView2 runtime,
    and when it's absent it does NOT error -- it silently falls back to
    MSHTML (the Internet Explorer engine, confirmed in webview/platforms/
    winforms.py's own renderer selection), which renders a modern
    Streamlit app as a broken blank window. Present by default on
    up-to-date Windows 10/11, but a pre-2020 Windows 10 install may lack
    it. Mirrors the same EdgeUpdate registry keys pywebview's
    _is_chromium() reads; on any unexpected detection failure this
    deliberately does nothing (fail-open) rather than blocking a machine
    that might actually work."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key_id = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        for hive in ("HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER"):
            for prefix in (r"SOFTWARE\WOW6432Node", "SOFTWARE"):
                try:
                    with winreg.OpenKey(
                        getattr(winreg, hive),
                        rf"{prefix}\Microsoft\EdgeUpdate\Clients\{key_id}",
                    ) as k:
                        pv, _ = winreg.QueryValueEx(k, "pv")
                        if str(pv) not in ("", "0.0.0.0"):
                            return
                except OSError:
                    continue
    except Exception:
        return
    print(
        "Chesswright needs Microsoft's WebView2 runtime, which this "
        "Windows machine doesn't have yet (without it the app window "
        "would open blank). It's a small, free, one-time install from "
        f"Microsoft -- opening the download page now:\n  {WEBVIEW2_URL}\n"
        "Install the \"Evergreen Bootstrapper\", then start Chesswright "
        "again.",
        file=sys.stderr,
    )
    webbrowser.open(WEBVIEW2_URL)
    sys.exit(1)
