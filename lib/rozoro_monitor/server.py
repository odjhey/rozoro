"""Foreground, resource-bounded, single-owner AF_UNIX protocol-v1 server."""

from __future__ import annotations

import asyncio
import errno
import fcntl
import json
import os
import resource
import socket
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import protocol
from .client import _open_home
from .store import EventStore

MAX_CLIENTS = int(os.environ.get("ROZORO_MONITOR_MAX_CLIENTS", "64"))
READ_TIMEOUT = float(os.environ.get("ROZORO_MONITOR_READ_TIMEOUT", "5.0"))
if MAX_CLIENTS < 2 or READ_TIMEOUT <= 0:
    raise RuntimeError("invalid monitor resource limits")
# asyncio pauses each transport at twice its StreamReader limit. The client cap
# therefore makes aggregate userspace input buffering finite and auditable.
MAX_BUFFERED_BYTES = MAX_CLIENTS * 2 * (protocol.MAX_FRAME_BYTES + 1)


class AlreadyRunningError(RuntimeError):
    pass


class UnsafeStateError(RuntimeError):
    pass


class MonitorServer:
    """One foreground daemon. Detached lifecycle and importing are later phases."""

    def __init__(self, home: str | os.PathLike[str] | None = None):
        self.home, self._home_fd = _open_home(home)
        self.socket_path = self.home / "monitor.sock"
        self.db_path = self.home / "monitor.db"
        self._home_identity = self._fd_identity(self._home_fd)
        self._lock_fd: int | None = None
        self._store: EventStore | None = None
        self._server: asyncio.AbstractServer | None = None
        self._socket_identity: tuple[int, int] | None = None
        self._clients = 0
        try:
            soft_fds = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
            open_fds = len(os.listdir("/dev/fd"))
            # Reserve descriptors for SQLite sidecars, listener, lock, health,
            # logging/runtime internals, and one transient accept.
            fd_budget = max(2, int(soft_fds) - open_fds - 16)
        except (OSError, ValueError):
            fd_budget = MAX_CLIENTS
        self._client_limit = min(MAX_CLIENTS, fd_budget)

    @staticmethod
    def _fd_identity(fd: int) -> tuple[int, int]:
        info = os.fstat(fd)
        return info.st_dev, info.st_ino

    def _entry(self, name: str) -> os.stat_result | None:
        try:
            return os.stat(name, dir_fd=self._home_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None

    @contextmanager
    def _anchored_cwd(self):
        """Anchor pathname-only stdlib APIs to the already verified home fd."""
        previous = os.open(".", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fchdir(self._home_fd)
            yield
        finally:
            os.fchdir(previous)
            os.close(previous)

    def _assert_home_anchor(self) -> None:
        current = os.stat(self.home, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != self._home_identity or not stat.S_ISDIR(current.st_mode):
            raise UnsafeStateError("ROZORO_HOME pathname no longer names the held private directory")

    def _acquire_lock(self) -> None:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open("monitor.lock", flags, 0o600, dir_fd=self._home_fd)
        except OSError as exc:
            raise UnsafeStateError("refusing unsafe monitor.lock") from exc
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise UnsafeStateError("monitor.lock must be an owner-private regular file")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise AlreadyRunningError("another rozorod owns monitor.lock") from exc
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
            os.fsync(fd)
            self._lock_fd = fd
        except BaseException:
            os.close(fd)
            raise

    def _socket_definitively_stale(self) -> bool:
        """Only ECONNREFUSED is stale; timeout/backlog/other ambiguity is live."""
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(str(self.socket_path))
            return False
        except OSError as exc:
            return exc.errno == errno.ECONNREFUSED
        finally:
            probe.close()

    def _prepare_entries(self) -> None:
        socket_info = self._entry("monitor.sock")
        if socket_info is not None:
            if not stat.S_ISSOCK(socket_info.st_mode):
                raise UnsafeStateError("monitor.sock exists but is not a socket")
            if not self._socket_definitively_stale():
                raise AlreadyRunningError("refusing live or indeterminate monitor.sock")
            # Lock is held and the exact no-follow entry was proven to be a stale socket.
            os.unlink("monitor.sock", dir_fd=self._home_fd)

        db_info = self._entry("monitor.db")
        if db_info is not None and (
            not stat.S_ISREG(db_info.st_mode) or db_info.st_uid != os.geteuid()
            or stat.S_IMODE(db_info.st_mode) & 0o077
        ):
            raise UnsafeStateError("monitor.db must be an owner-private regular file")
        for suffix in ("monitor.db-wal", "monitor.db-shm"):
            info = self._entry(suffix)
            if info is not None and (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
            ):
                raise UnsafeStateError(f"{suffix} must be an owner-private regular file")

    async def start(self) -> None:
        self._acquire_lock()
        try:
            self._assert_home_anchor()
            self._prepare_entries()
            # sqlite3 and AF_UNIX bind expose pathname-only APIs. Anchor both
            # synchronously, restore cwd, and only then yield to asyncio.
            listener: socket.socket | None = None
            with self._anchored_cwd():
                self._store = EventStore("monitor.db")
                db_info = self._entry("monitor.db")
                if db_info is None or not stat.S_ISREG(db_info.st_mode):
                    raise UnsafeStateError("database creation escaped private home")
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                old_umask = os.umask(0o177)
                try:
                    listener.bind("monitor.sock")
                    listener.listen(self._client_limit)
                    listener.setblocking(False)
                except BaseException:
                    listener.close()
                    raise
                finally:
                    os.umask(old_umask)
            self._assert_home_anchor()
            info = self._entry("monitor.sock")
            if info is None or not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                listener.close()
                raise UnsafeStateError("socket creation escaped private home")
            os.chmod("monitor.sock", 0o600, dir_fd=self._home_fd, follow_symlinks=False)
            self._socket_identity = (info.st_dev, info.st_ino)
            try:
                self._server = await asyncio.start_unix_server(
                    self._handle_client, sock=listener, limit=protocol.MAX_FRAME_BYTES + 1
                )
            except BaseException:
                listener.close()
                raise
        except BaseException:
            await self.close()
            raise

    @staticmethod
    def _frame_error(code: str) -> dict[str, Any]:
        return {"v": 1, "type": "frame.error", "code": code}

    @staticmethod
    def _correlated_error(frame: bytes, error: protocol.ProtocolError) -> dict[str, Any]:
        """Retain a validated safe correlation ID; never echo an unchecked value."""
        try:
            raw = json.loads(frame)
        except (ValueError, UnicodeError, RecursionError):
            return MonitorServer._frame_error(error.code)
        if not isinstance(raw, dict):
            return MonitorServer._frame_error(error.code)
        code = error.code
        if code in {"invalid-event", "invalid-field", "unsupported-type"} and "event_id" in raw:
            candidate = {"v": 1, "type": "event.error", "event_id": raw["event_id"], "code": code}
        elif code in {"invalid-message", "invalid-field", "unsupported-type"} and "request_id" in raw:
            candidate = {"v": 1, "type": "request.error", "request_id": raw["request_id"], "code": code}
        else:
            return MonitorServer._frame_error(code)
        try:
            protocol.validate(candidate)
            return candidate
        except protocol.ProtocolError:
            return MonitorServer._frame_error(code)

    async def _send(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        writer.write(protocol.encode(message).encode("utf-8"))
        await asyncio.wait_for(writer.drain(), READ_TIMEOUT)

    async def _discard_oversized(self, reader: asyncio.StreamReader) -> None:
        while True:
            try:
                await asyncio.wait_for(reader.readuntil(b"\n"), READ_TIMEOUT)
                return
            except asyncio.LimitOverrunError as exc:
                await reader.readexactly(exc.consumed)
            except (asyncio.IncompleteReadError, TimeoutError):
                return

    async def _read_frame(self, reader: asyncio.StreamReader) -> bytes | None:
        try:
            return await asyncio.wait_for(reader.readuntil(b"\n"), READ_TIMEOUT)
        except asyncio.IncompleteReadError as exc:
            if exc.partial:
                raise protocol.ProtocolError("invalid-json", "unterminated frame")
            return None
        except asyncio.LimitOverrunError:
            await self._discard_oversized(reader)
            raise protocol.ProtocolError("frame-too-large", "frame exceeds limit")
        except TimeoutError as exc:
            raise protocol.ProtocolError("read-timeout", "client read deadline exceeded") from exc

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._clients >= self._client_limit:
            try:
                await self._send(writer, self._frame_error("server-busy"))
            except Exception:
                pass
            writer.close()
            return
        self._clients += 1
        try:
            while True:
                frame = b""
                try:
                    read = await self._read_frame(reader)
                    if read is None:
                        return
                    frame = read
                    message = protocol.decode(frame)
                    if message["type"] == "health":
                        assert self._store is not None
                        reply = {"v": 1, "type": "health.result", "request_id": message["request_id"],
                                 "schema_version": self._store.schema_version, "clients": self._clients}
                    elif "event_id" in message and protocol.requires_producer_seq(message["type"]):
                        assert self._store is not None
                        try:
                            accepted = self._store.accept_event(message)
                        except ValueError:
                            reply = {"v": 1, "type": "event.error",
                                     "event_id": message["event_id"], "code": "invalid-event"}
                        except Exception:
                            reply = self._frame_error("internal-error")
                        else:
                            # Store returns only after COMMIT; conflicts and failures are never ACKed.
                            reply = {"v": 1, "type": "ack", "event_id": message["event_id"],
                                     "durable_seq": accepted.durable_seq}
                    else:
                        raise protocol.ProtocolError("unsupported-type", "request is not served yet")
                except protocol.ProtocolError as exc:
                    reply = self._correlated_error(frame, exc) if frame else self._frame_error(exc.code)
                except (MemoryError, RecursionError):
                    reply = self._frame_error("internal-error")
                await self._send(writer, reply)
                if reply.get("code") == "read-timeout":
                    return
        except (BrokenPipeError, ConnectionResetError, ConnectionError, TimeoutError):
            pass
        finally:
            self._clients -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionError):
                pass

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._store is not None:
            self._store.close()
            self._store = None
        if self._socket_identity is not None:
            info = self._entry("monitor.sock")
            if info is not None and (info.st_dev, info.st_ino) == self._socket_identity:
                os.unlink("monitor.sock", dir_fd=self._home_fd)
            self._socket_identity = None
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        if self._home_fd >= 0:
            os.close(self._home_fd)
            self._home_fd = -1
