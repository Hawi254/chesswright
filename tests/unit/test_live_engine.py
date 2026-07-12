import live_engine


class _FakeEngineService:
    def __init__(self, dead, version):
        self._dead = dead
        self._engine_version = version


def test_get_engine_status_summary_when_no_engine_detected(monkeypatch):
    monkeypatch.setattr(live_engine, "get_engine_service", lambda: None)
    result = live_engine.get_engine_status_summary()
    assert result == {"connected": False, "version": None}


def test_get_engine_status_summary_when_engine_connected(monkeypatch):
    fake = _FakeEngineService(dead=False, version="Stockfish 16")
    monkeypatch.setattr(live_engine, "get_engine_service", lambda: fake)
    result = live_engine.get_engine_status_summary()
    assert result == {"connected": True, "version": "Stockfish 16"}


def test_get_engine_status_summary_when_engine_dead(monkeypatch):
    fake = _FakeEngineService(dead=True, version="Stockfish 16")
    monkeypatch.setattr(live_engine, "get_engine_service", lambda: fake)
    result = live_engine.get_engine_status_summary()
    assert result == {"connected": False, "version": "Stockfish 16"}
