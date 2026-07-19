import engine_status


class _FakeEngineService:
    def __init__(self, dead, version):
        self._dead = dead
        self._engine_version = version


def test_get_engine_status_summary_when_never_started(monkeypatch):
    monkeypatch.setattr(engine_status, "_service_started", False)

    def _fail_if_called():
        raise AssertionError("get_engine_service() must not be called when the engine was never started")

    monkeypatch.setattr(engine_status, "get_engine_service", _fail_if_called)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": False, "version": None}


def test_get_engine_status_summary_when_no_engine_detected(monkeypatch):
    monkeypatch.setattr(engine_status, "_service_started", True)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: None)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": False, "version": None}


def test_get_engine_status_summary_when_engine_connected(monkeypatch):
    fake = _FakeEngineService(dead=False, version="Stockfish 16")
    monkeypatch.setattr(engine_status, "_service_started", True)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: fake)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": True, "version": "Stockfish 16"}


def test_get_engine_status_summary_when_engine_dead(monkeypatch):
    fake = _FakeEngineService(dead=True, version="Stockfish 16")
    monkeypatch.setattr(engine_status, "_service_started", True)
    monkeypatch.setattr(engine_status, "get_engine_service", lambda: fake)
    result = engine_status.get_engine_status_summary()
    assert result == {"connected": False, "version": "Stockfish 16"}


def test_get_engine_service_caches_a_none_result(monkeypatch):
    """A legitimate None (Stockfish not found) must be cached too, not
    recomputed on every call -- the whole reason _UNSET (not None) is the
    sentinel."""
    engine_status.clear_engine_service_cache()
    call_count = {"n": 0}

    class _FakeConfig:
        def get(self, *_a, **_k):
            return {}

    def _fake_load_config():
        call_count["n"] += 1
        return _FakeConfig()

    monkeypatch.setattr(engine_status.config, "load_config", _fake_load_config)
    monkeypatch.setattr(engine_status.worker, "find_engine_path", lambda *_a, **_k: None)

    result1 = engine_status.get_engine_service()
    result2 = engine_status.get_engine_service()
    assert result1 is None
    assert result2 is None
    assert call_count["n"] == 1
    engine_status.clear_engine_service_cache()
