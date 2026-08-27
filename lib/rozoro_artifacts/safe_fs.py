"""Directory-fd based filesystem access for owner-private operator artifacts."""
from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path

DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class UnsafePath(RuntimeError):
    """A path could not be traversed without following links or losing ownership."""


def trusted_source_metadata(before: os.stat_result, info: os.stat_result, uid: int) -> bool:
    """Pure metadata predicate, exposed for deterministic wrong-owner tests."""
    return ((before.st_dev, before.st_ino) == (info.st_dev, info.st_ino)
            and stat.S_ISREG(info.st_mode) and info.st_uid == uid
            and info.st_nlink == 1 and not stat.S_IMODE(info.st_mode) & 0o022)


def _component(value: str) -> str:
    if value in {"", ".", ".."} or "/" in value or "\x00" in value:
        raise UnsafePath(f"unsafe path component: {value!r}")
    return value


def _open_child(parent_fd: int, name: str) -> int:
    try:
        return os.open(_component(name), DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise UnsafePath(f"refusing symlink or non-directory path component: {name}") from exc
        raise


@dataclass
class SafeDirectory:
    """An opened directory used only through descriptor-relative operations."""

    fd: int
    path: Path

    @classmethod
    def open_path(
        cls,
        path: str | os.PathLike[str],
        *,
        create: bool,
        require_owner: bool = True,
        private: bool = False,
    ) -> "SafeDirectory":
        absolute = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
        parts = absolute.parts
        if not absolute.is_absolute() or not parts:
            raise UnsafePath(f"path must resolve lexically to an absolute path: {path}")
        current = os.open(parts[0], DIR_FLAGS)
        try:
            for part in parts[1:]:
                try:
                    child = _open_child(current, part)
                except FileNotFoundError as exc:
                    if not create:
                        raise UnsafePath(f"required directory does not exist: {absolute}") from exc
                    try:
                        os.mkdir(_component(part), 0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                    child = _open_child(current, part)
                os.close(current)
                current = child
            info = os.fstat(current)
            if require_owner and info.st_uid != os.geteuid():
                raise UnsafePath(f"directory is not owned by the current user: {absolute}")
            if private:
                os.fchmod(current, 0o700)
                if stat.S_IMODE(os.fstat(current).st_mode) != 0o700:
                    raise UnsafePath(f"directory is not owner-private: {absolute}")
            return cls(current, absolute)
        except (OSError, UnsafePath):
            os.close(current)
            raise

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> "SafeDirectory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def stat(self) -> os.stat_result:
        return os.fstat(self.fd)

    def list_names(self) -> list[str]:
        try:
            return os.listdir(self.fd)
        except OSError as exc:
            raise UnsafePath(f"cannot scan directory: {self.path}") from exc

    def open_child(self, name: str, *, require_owner: bool = True, private: bool = False) -> "SafeDirectory":
        child = _open_child(self.fd, name)
        try:
            info = os.fstat(child)
            if require_owner and info.st_uid != os.geteuid():
                raise UnsafePath(f"child directory is not owned by the current user: {name}")
            if private:
                os.fchmod(child, 0o700)
                if stat.S_IMODE(os.fstat(child).st_mode) != 0o700:
                    raise UnsafePath(f"child directory is not owner-private: {name}")
            return SafeDirectory(child, self.path / name)
        except (OSError, UnsafePath):
            os.close(child)
            raise

    def open_or_create_private_child(self, name: str, *, exclusive: bool = False) -> "SafeDirectory":
        name = _component(name)
        try:
            os.mkdir(name, 0o700, dir_fd=self.fd)
        except FileExistsError:
            if exclusive:
                raise
        child = self.open_child(name, require_owner=True, private=True)
        os.fsync(self.fd)
        return child

    def read_regular(self, name: str) -> tuple[str, bytes | None]:
        """Read an owned regular file without following links."""
        name = _component(name)
        try:
            before = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return "missing", None
        except OSError:
            return "unreadable", None
        if stat.S_ISLNK(before.st_mode):
            return "unsafe", None
        try:
            file_fd = os.open(name, FILE_FLAGS, dir_fd=self.fd)
        except FileNotFoundError:
            return "missing", None
        except OSError as exc:
            return ("unsafe" if exc.errno in {errno.ELOOP, errno.ENOTDIR} else "unreadable"), None
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                return "unsafe", None
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return "regular", b"".join(chunks)
        except OSError:
            return "unreadable", None
        finally:
            os.close(file_fd)

    def read_source_regular(self, name: str) -> bytes:
        """Read a VCS policy source with owned/single-link/non-writable guarantees."""
        name = _component(name)
        try:
            before = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            fd = os.open(name, FILE_FLAGS, dir_fd=self.fd)
        except OSError as exc:
            raise UnsafePath(f"unsafe repository source: {name}") from exc
        try:
            info = os.fstat(fd)
            if not trusted_source_metadata(before, info, os.geteuid()):
                raise UnsafePath(f"unsafe repository source: {name}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def write_exclusive(self, name: str, data: bytes) -> None:
        name = _component(name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(name, flags, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(file_fd, view) :]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
        os.fsync(self.fd)
