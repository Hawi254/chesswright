"""Regression test for dashboard/live_engine.py's get_engine_service --
the four behavioral tests for get_engine_status_summary moved to
tests/unit/test_engine_status.py when that logic moved to
dashboard/engine_status.py (2026-07-13). This file now only pins the one
thing that's specific to live_engine.py itself: that .clear() on its
thin wrapper actually clears engine_status.py's real cache, not a second,
independently-stale one -- the exact behavior dashboard/settings_view.py's
existing live_engine.get_engine_service.clear() call sites depend on.
"""
import engine_status
import live_engine


def test_get_engine_service_clear_delegates_to_engine_status(monkeypatch):
    calls = {"n": 0}

    def _fake_clear():
        calls["n"] += 1

    monkeypatch.setattr(engine_status, "clear_engine_service_cache", _fake_clear)
    live_engine.get_engine_service.clear()
    assert calls["n"] == 1


def test_get_engine_service_delegates_to_engine_status(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: sentinel)
    assert live_engine.get_engine_service() is sentinel
