#!/usr/bin/env python3
"""
Cross-process lock for `worker.py` batch runs (BRIEF.md's "Phase D--before"
deferred gap, closed here): the Analysis Jobs dashboard view's whole job is
managing run lifecycle, so this is the right moment to actually detect "a
worker.run() batch is already running somewhere" instead of letting a second
one start and silently compete for CPU against the first (both are safe
against the same queue_order-ordered table -- confirmed by reading
worker.fetch_next_game()'s query -- just wasteful, not corrupting).

The lock is held via an OS-level exclusive file lock (fcntl.flock on POSIX,
msvcrt.locking on Windows) rather than PID-file content alone. This closes
the classic TOCTOU race the previous design had between reading the PID file
and writing a new one: two processes that both see no live lock can now only
one of them win the OS lock -- the loser gets an immediate OSError, not a
silent race win. The lock is also released automatically on process crash,
because the OS closes all open file descriptors when a process exits.

The lock FILE still stores the owning PID and start time so that the UI
(analysis_jobs_view.py, app.py) can display informative "running since..."
status -- reading that content is pure status reporting, not the locking
mechanism itself.
"""
import ctypes
import dataclasses
import datetime
import os
import pathlib
import sys

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

import config

LOCK_PATH = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent / "worker.lock"

# File descriptor kept open for as long as THIS process holds the OS lock.
# None means this process has not called acquire() (or has called release()).
_lock_fd = None


@dataclasses.dataclass
class LockInfo:
    pid: int
    started_at: str
    alive: bool


class LockHeldError(RuntimeError):
    def __init__(self, info: LockInfo):
        self.info = info
        super().__init__(
            f"Another analysis run is already in progress (pid {info.pid}, "
            f"started {info.started_at}).")


def _pid_alive(pid: int) -> bool:
    """No new dependency (e.g. psutil) for just this -- os.kill's signal-0
    trick is the standard POSIX liveness check, but Windows' os.kill only
    understands CTRL_C_EVENT/CTRL_BREAK_EVENT/SIGTERM, not signal 0, so it
    needs its own real check via OpenProcess rather than being silently
    wrong there."""
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else
    return True


def _os_lock(fd) -> bool:
    """Try to acquire an exclusive non-blocking OS-level lock on fd.
    Returns True on success, False if another process already holds it."""
    try:
        if sys.platform == "win32":
            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _os_unlock(fd) -> None:
    try:
        if sys.platform == "win32":
            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def status() -> LockInfo | None:
    """Returns None if no lock file exists. Otherwise reports whether the
    PID it names is still actually alive -- a lock file surviving a crash
    (no clean release) is exactly the case the UI needs to tell apart from
    a real still-running batch, so this never assumes the file's mere
    existence means "still running"."""
    if not LOCK_PATH.exists():
        return None
    try:
        pid_line, started_line = LOCK_PATH.read_text().splitlines()[:2]
        pid = int(pid_line)
    except (ValueError, IndexError):
        return None  # malformed/empty lock file -- treat as no lock, not a crash
    return LockInfo(pid=pid, started_at=started_line, alive=_pid_alive(pid))


def acquire():
    """Acquires the lock, raising LockHeldError if a live process already
    holds it.

    The OS-level flock/msvcrt lock is acquired atomically before writing
    the PID to the file, so two concurrent acquire() calls are resolved
    by the OS rather than by a TOCTOU-prone status()-then-write sequence.
    The winning process then overwrites the file with its own PID and
    timestamp for informational display; the losing process reads the
    winner's info from the file and raises LockHeldError with it.
    """
    global _lock_fd
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch(exist_ok=True)  # create if absent; no-op if already there

    fd = open(LOCK_PATH, "r+")
    if not _os_lock(fd):
        fd.close()
        info = status()
        raise LockHeldError(info or LockInfo(pid=-1, started_at="unknown", alive=True))

    # We hold the OS lock -- overwrite the file with our own PID and timestamp.
    fd.seek(0)
    fd.truncate()
    fd.write(f"{os.getpid()}\n{datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
    fd.flush()
    _lock_fd = fd


def release():
    """Releases the OS lock, closes the file descriptor, and removes the
    lock file. Only acts if this process actually holds the lock (_lock_fd
    is set) -- a spurious release() call with no prior acquire() is a
    no-op rather than accidentally removing another process's lock file."""
    global _lock_fd
    if _lock_fd is not None:
        _os_unlock(_lock_fd)
        _lock_fd.close()
        _lock_fd = None
        LOCK_PATH.unlink(missing_ok=True)


def force_release():
    """Explicit UI escape hatch for a diagnosed-stale lock (status().alive
    is False). The OS lock was already released when the dead process
    exited, so only the lock FILE needs removing here.

    Never call this on a lock that's still alive without the caller having
    confirmed that itself -- the same "diagnosed, not waived" discipline
    BRIEF.md already applies to its other deferred exceptions."""
    LOCK_PATH.unlink(missing_ok=True)
