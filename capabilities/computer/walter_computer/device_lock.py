"""One nonblocking interprocess lock per configured device, held for one call."""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat

DEFAULT_LOCK = Path('/run/walter-computer/main-mac.lock')


def configured_lock_path():
    config_path = Path('/opt/walter-computer/config.json')
    if config_path.exists():
        return Path(json.loads(config_path.read_text()).get('device_lock_path', str(DEFAULT_LOCK)))
    return DEFAULT_LOCK


class DeviceCallLock:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else configured_lock_path()
        if not self.path.is_absolute():
            raise ValueError('device lock path must be absolute')

    def _open(self):
        parent = self.path.parent
        info = parent.stat()
        if parent.resolve() != parent or not stat.S_ISDIR(info.st_mode):
            raise PermissionError('device lock parent must be a real directory')
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise PermissionError('device lock parent must be private and owned by this service')
        flags = os.O_CLOEXEC | getattr(os, 'O_NOFOLLOW', 0)
        try:
            # flock on an existing read-only descriptor needs no filesystem write.
            fd = os.open(self.path, os.O_RDONLY | flags)
        except FileNotFoundError:
            try:
                fd = os.open(self.path, os.O_RDONLY | os.O_CREAT | os.O_EXCL | flags, 0o600)
            except FileExistsError:
                fd = os.open(self.path, os.O_RDONLY | flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise PermissionError('device lock must be a trusted regular file')
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise PermissionError('device lock permissions must be private')
        except BaseException:
            os.close(fd)
            raise
        return fd

    @contextmanager
    def hold(self):
        fd = self._open()
        acquired = False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
            yield acquired
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
