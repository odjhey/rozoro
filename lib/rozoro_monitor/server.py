"""Foreground, single-owner AF_UNIX server for protocol-v1 events."""

from __future__ import annotations

import asyncio
import fcntl
import os
import socket
import stat
from pathlib import Path
from typing import Any

from . import protocol
from .client import resolve_home
from .store import EventStore


class AlreadyRunningError(RuntimeError):
    pass


class MonitorServer:
    """One foreground daemon. Lifecycle supervision intentionally lives elsewhere."""

    def __init__(self, home: str | os.PathLike[str] | None = None):
        self.home = resolve_home(home)
        self.socket_path = self.home / "monitor.sock"
        self.lock_path = self.home / "monitor.lock"
        self.db_path = self.home / "monitor.db"
        self._lock_fd: int | None = None
        self._store: EventStore | None = None
        self._server: asyncio.AbstractServer | None = None
        self._socket_identity: tuple[int, int] | None = None
        self._clients = 0

    def _acquire_lock(self) -> None:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.lock_path, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise RuntimeError("monitor lock is not an owner-controlled regular file")
            os.fchmod(fd, 0o600)
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

    def _socket_is_live(self) -> bool:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(str(self.socket_path))
            return True
        except (ConnectionRefusedError, FileNotFoundError, TimeoutError, OSError):
            return False
        finally:
            probe.close()

    async def start(self) -> None:
        self._acquire_lock()
        try:
            if os.path.lexists(self.socket_path):
                if self._socket_is_live():
                    raise AlreadyRunningError("refusing connectable monitor.sock")
                # Only the process holding monitor.lock may declare this stale.
                self.socket_path.unlink()
            self._store = EventStore(self.db_path)
            old_umask = os.umask(0o177)
            try:
                self._server = await asyncio.start_unix_server(
                    self._handle_client, path=str(self.socket_path), limit=protocol.MAX_FRAME_BYTES + 1
                )
            finally:
                os.umask(old_umask)
            os.chmod(self.socket_path, 0o600)
            info = self.socket_path.lstat()
            self._socket_identity = (info.st_dev, info.st_ino)
        except BaseException:
            await self.close()
            raise

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    @staticmethod
    def _error_message(error: protocol.ProtocolError) -> dict[str, Any]:
        return {"v": 1, "type": "frame.error", "code": error.code}

    async def _send(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        writer.write(protocol.encode(message).encode("utf-8"))
        await writer.drain()

    async def _discard_oversized(self, reader: asyncio.StreamReader) -> None:
        """Consume exactly through the oversized frame's newline, not beyond it."""
        while True:
            try:
                await reader.readuntil(b"\n")
                return
            except asyncio.LimitOverrunError as exc:
                await reader.readexactly(exc.consumed)
            except asyncio.IncompleteReadError:
                return

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients += 1
        try:
            while True:
                try:
                    frame = await reader.readuntil(b"\n")
                except asyncio.IncompleteReadError as exc:
                    if exc.partial:
                        await self._send(writer, self._error_message(
                            protocol.ProtocolError("invalid-json", "unterminated frame")
                        ))
                    return
                except asyncio.LimitOverrunError:
                    await self._discard_oversized(reader)
                    await self._send(writer, self._error_message(
                        protocol.ProtocolError("frame-too-large", "frame exceeds limit")
                    ))
                    continue

                try:
                    message = protocol.decode(frame)
                    if message["type"] == "health":
                        assert self._store is not None
                        reply = {"v": 1, "type": "health.result", "request_id": message["request_id"],
                                 "schema_version": self._store.schema_version, "clients": self._clients}
                    elif "event_id" in message and protocol.requires_producer_seq(message["type"]):
                        assert self._store is not None
                        accepted = self._store.accept_event(message)
                        # accept_event returns only after its transaction COMMIT.
                        reply = {"v": 1, "type": "ack", "event_id": message["event_id"],
                                 "durable_seq": accepted.durable_seq}
                    else:
                        raise protocol.ProtocolError("unsupported-type", "request is not served yet")
                except protocol.ProtocolError as exc:
                    reply = self._error_message(exc)
                except Exception:
                    # Persistence/reducer failures are uncertain and must never be ACKed.
                    return
                await self._send(writer, reply)
        except (BrokenPipeError, ConnectionResetError, ConnectionError):
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
            try:
                info = self.socket_path.lstat()
                if (info.st_dev, info.st_ino) == self._socket_identity:
                    self.socket_path.unlink()
            except FileNotFoundError:
                pass
            self._socket_identity = None
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
