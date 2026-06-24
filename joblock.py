#!/usr/bin/env python3
"""
Cross-process lock for `worker.py` batch runs (BRIEF.md's "Phase D--before"
deferred gap, closed here): the Analysis Jobs dashboard view's whole job is
managing run lifecycle, so this is the right moment to actually detect "a
worker.run() batch is already running somewhere" instead of letting a
second one start and silently compete for CPU against the first (both are
safe against the same queue_order-ordered table -- confirmed by reading
worker.fetch_next_game()'s query -- just wasteful, not corrupting).

A single PID file at <config dir>/worker.lock, holding the owning
process's PID and start time. In-process duplicate prevention (the
dashboard's own background-thread registry) is a separate, cheaper layer
that this complements, not replaces -- this one also catches a second
`python3 worker.py` run launched from a terminal alongside the dashboard.
"""
import ctypes
import dataclasses
import datetime
import os
import pathlib
import sys

import config

LOCK_PATH = pathlib.Path(config.DEFAULT_CONFIG_PATH).parent / "worker.lock"


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
    """Raises LockHeldError if a live process already holds the lock.
    A lock file left behind by a dead process is treated as stale and
    silently reclaimed -- its liveness was just actually checked above,
    not assumed, so this isn't a blind override of someone else's run."""
    existing = status()
    if existing is not None and existing.alive:
        raise LockHeldError(existing)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(f"{os.getpid()}\n{datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")


def release():
    """Only removes the lock file if it still names OUR pid -- guards
    against a race where this process's lock was already judged stale and
    reclaimed by a newer run before this (slower) process got to its own
    cleanup."""
    info = status()
    if info is not None and info.pid == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)


def force_release():
    """Explicit UI escape hatch for a diagnosed-stale lock (status().alive
    is False) -- never call this on a lock that's still alive without the
    caller having confirmed that itself, the same "diagnosed, not waived"
    discipline BRIEF.md already applies to its other deferred exceptions."""
    LOCK_PATH.unlink(missing_ok=True)
