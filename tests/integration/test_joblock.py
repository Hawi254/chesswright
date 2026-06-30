"""Integration tests for joblock.py — OS-level lock, TOCTOU safety, force release."""
import os
import pathlib
import pytest

import joblock


@pytest.fixture(autouse=True)
def isolate_lock(tmp_path, monkeypatch):
    """Redirect the global LOCK_PATH to a per-test temp file so tests
    are fully isolated from each other and from any running worker."""
    lock_path = tmp_path / "test_worker.lock"
    monkeypatch.setattr(joblock, "LOCK_PATH", lock_path)
    monkeypatch.setattr(joblock, "_lock_fd", None)
    yield
    joblock.release()  # ensure cleanup even if test fails mid-acquire


@pytest.mark.integration
class TestAcquireRelease:
    def test_acquire_creates_lock_file(self):
        joblock.acquire()
        assert joblock.LOCK_PATH.exists()

    def test_release_removes_lock_file(self):
        joblock.acquire()
        joblock.release()
        assert not joblock.LOCK_PATH.exists()

    def test_lock_file_contains_pid(self):
        joblock.acquire()
        content = joblock.LOCK_PATH.read_text()
        assert str(os.getpid()) in content

    def test_release_without_acquire_is_noop(self):
        joblock.release()  # should not raise

    def test_double_release_is_noop(self):
        joblock.acquire()
        joblock.release()
        joblock.release()  # should not raise


@pytest.mark.integration
class TestDoubleAcquire:
    def test_second_acquire_raises_lock_held_error(self):
        joblock.acquire()
        with pytest.raises(joblock.LockHeldError) as exc_info:
            joblock.acquire()
        assert exc_info.value.info.pid == os.getpid()

    def test_lock_held_error_has_info_attribute(self):
        joblock.acquire()
        try:
            joblock.acquire()
        except joblock.LockHeldError as e:
            assert hasattr(e, "info")
            assert isinstance(e.info, joblock.LockInfo)


@pytest.mark.integration
class TestStatus:
    def test_status_none_when_no_lock_file(self):
        assert joblock.status() is None

    def test_status_alive_when_held(self):
        joblock.acquire()
        info = joblock.status()
        assert info is not None
        assert info.alive is True
        assert info.pid == os.getpid()

    def test_status_reports_dead_for_nonexistent_pid(self, tmp_path):
        # Write a lock file with a PID that definitely doesn't exist
        joblock.LOCK_PATH.write_text("99999999\n2025-01-01T00:00:00+00:00\n")
        info = joblock.status()
        assert info is not None
        # PID 99999999 doesn't exist (99m is above Linux's max PID)
        assert info.alive is False

    def test_status_after_release_returns_none(self):
        joblock.acquire()
        joblock.release()
        assert joblock.status() is None


@pytest.mark.integration
class TestForceRelease:
    def test_force_release_removes_stale_file(self):
        joblock.LOCK_PATH.write_text("99999999\nstale\n")
        joblock.force_release()
        assert not joblock.LOCK_PATH.exists()

    def test_force_release_when_no_file_is_noop(self):
        assert not joblock.LOCK_PATH.exists()
        joblock.force_release()  # should not raise
