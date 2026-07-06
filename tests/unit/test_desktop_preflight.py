"""Unit tests for desktop_app.py's launch preflights (BRIEF S6z/S6aa):
the compiled-dep CPU probe (numpy readable-error path, subprocess probe
for the pyarrow-SIGILL class an in-process try/except can never catch)
and the Windows WebView2 check's non-Windows no-op."""
import pathlib
import subprocess
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def test_preflight_imports_mode_exits_zero():
    """--preflight-imports run as a real subprocess (exactly how
    check_cpu_compat() invokes it) imports every compiled dep and exits 0
    on supported hardware."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "desktop_app.py"), "--preflight-imports"],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0
    assert "OK" in proc.stdout


def test_probe_skipped_when_sse42_confirmed(monkeypatch):
    import desktop_app
    monkeypatch.setattr(desktop_app, "_sse42_confirmed", lambda: True)

    def boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("probe subprocess must not run on a confirmed CPU")
    monkeypatch.setattr(desktop_app.subprocess, "run", boom)
    desktop_app.check_cpu_compat()  # no exit, no probe


def test_probe_failure_then_simd_none_retry_success(monkeypatch):
    """First probe dies (as a pyarrow SIGILL would); the retry with
    ARROW_USER_SIMD_LEVEL=NONE survives -> the env var must be exported
    for the server subprocess and launch must continue."""
    import desktop_app
    monkeypatch.setattr(desktop_app, "_sse42_confirmed", lambda: False)
    monkeypatch.delenv("ARROW_USER_SIMD_LEVEL", raising=False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(kwargs.get("env"))
        rc = 0 if kwargs.get("env") and \
            kwargs["env"].get("ARROW_USER_SIMD_LEVEL") == "NONE" else -4
        return types.SimpleNamespace(returncode=rc, stdout="", stderr="")
    monkeypatch.setattr(desktop_app.subprocess, "run", fake_run)

    desktop_app.check_cpu_compat()
    assert len(calls) == 2
    assert desktop_app.os.environ.get("ARROW_USER_SIMD_LEVEL") == "NONE"
    monkeypatch.delenv("ARROW_USER_SIMD_LEVEL", raising=False)


def test_probe_failure_both_ways_exits_readably(monkeypatch, capsys):
    import desktop_app
    monkeypatch.setattr(desktop_app, "_sse42_confirmed", lambda: False)

    def fake_run(cmd, **kwargs):
        return types.SimpleNamespace(returncode=-4, stdout="",
                                     stderr="Illegal instruction")
    monkeypatch.setattr(desktop_app.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        desktop_app.check_cpu_compat()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "processor" in err and "SSE4.2" in err


def test_check_webview2_is_noop_off_windows():
    import desktop_app
    if sys.platform == "win32":
        pytest.skip("non-Windows no-op test")
    desktop_app.check_webview2()  # must neither raise nor exit
