"""A file lock that works on every system (fcntl on macOS and Linux, msvcrt on Windows): held by an
open file descriptor, freed when it closes."""
from __future__ import annotations

import os

if os.name == "nt":
    import msvcrt

    def try_lock(fd: int) -> bool:
        """Take the lock now, or False when another program holds it."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def unlock(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def try_lock(fd: int) -> bool:
        """Take the lock now, or False when another program holds it."""
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
