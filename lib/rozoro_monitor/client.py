"""Synchronous protocol-v1 producer client with durable atomic spool fallback."""

from __future__ import annotations

import fcntl
import json
import os
import socket
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import protocol

DEFAULT_TIMEOUT = 2.0


class ClientError(RuntimeError):
    """The event was not proven durably accepted (and was spooled)."""


class UnsafePathError(ClientError):
    """A client state path failed ownership, type, or permission checks."""


def _directory(path: Path, *, create: bool = True) -> Path:
    if create:
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise UnsafePathError(f"cannot create private directory {path}: {exc}") from exc
    try:
        info = path.lstat()
    except OSError as exc:
        raise UnsafePathError(f"cannot inspect directory {path}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise UnsafePathError(f"refusing non-directory or symlink path: {path}")
    if info.st_uid != os.geteuid():
        raise UnsafePathError(f"refusing directory not owned by current user: {path}")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise UnsafePathError(f"refusing group/world-accessible directory: {path}")
    return path


def resolve_home(home: str | os.PathLike[str] | None = None) -> Path:
    raw = Path(home) if home is not None else Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    return _directory(raw)


def _open_private_regular(path: Path, flags: int, mode: int = 0o600) -> int:
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, mode)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise UnsafePathError(f"refusing unsafe state file: {path}")
        return fd
    except Exception:
        if "fd" in locals():
            os.close(fd)
        raise


def allocate_producer_seq(session_id: str, home: str | os.PathLike[str] | None = None) -> int:
    """Atomically allocate the next positive sequence for one validated session ID."""
    # Reuse protocol's identifier rules without making filesystem assumptions.
    probe = {"v": 1, "type": "session.end", "event_id": "probe", "producer_seq": 1,
             "session_id": session_id, "harness": "pi", "role": "crew", "task_id": "probe"}
    protocol.validate(probe)
    state = _directory(resolve_home(home) / "producer-seq")
    path = state / f"{session_id}.seq"
    fd = _open_private_regular(path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = os.read(fd, 64)
        if raw:
            try:
                previous = int(raw.decode("ascii"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise UnsafePathError(f"invalid producer sequence state: {path}") from exc
        else:
            previous = 0
        value = previous + 1
        if value > protocol.MAX_INTEGER:
            raise ClientError(f"producer sequence exhausted for {session_id}")
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(value).encode("ascii"))
        os.ftruncate(fd, len(str(value)))
        os.fsync(fd)
        return value
    finally:
        os.close(fd)


def prepare_event(event: Mapping[str, Any], home: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Copy and validate an event, allocating producer_seq only when the schema requires it and it's absent."""
    prepared = dict(event)
    message_type = prepared.get("type")
    if isinstance(message_type, str) and protocol.requires_producer_seq(message_type) and "producer_seq" not in prepared:
        session_id = prepared.get("session_id")
        if not isinstance(session_id, str):
            protocol.validate(prepared)  # raises the contract's deterministic error
        prepared["producer_seq"] = allocate_producer_seq(session_id, home)
    protocol.validate(prepared)
    if "event_id" not in prepared:
        raise protocol.ProtocolError("invalid-event", "producer events require event_id", "event_id")
    return prepared


def _event_bytes(event: Mapping[str, Any]) -> bytes:
    return protocol.encode(dict(event)).encode("utf-8")


def spool_event(event: Mapping[str, Any], home: str | os.PathLike[str] | None = None) -> Path:
    """Durably preserve exactly one canonical copy, without replacing evidence."""
    validated = dict(event)
    protocol.validate(validated)
    data = _event_bytes(validated)
    root = resolve_home(home)
    spool = _directory(root / "spool")
    destination = spool / f"{validated['event_id']}.json"

    # A prior uncertain attempt is success only when it preserves identical bytes.
    try:
        fd = _open_private_regular(destination, os.O_RDONLY)
    except FileNotFoundError:
        fd = -1
    if fd >= 0:
        try:
            existing = os.read(fd, protocol.MAX_FRAME_BYTES + 1)
        finally:
            os.close(fd)
        if existing != data:
            raise ClientError(f"spool collision for event_id {validated['event_id']}")
        return destination

    fd, temporary = tempfile.mkstemp(prefix=".event-", suffix=".tmp", dir=spool)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        # The fully fsynced temporary becomes visible in one atomic rename.
        os.replace(temp_path, destination)
        directory_fd = os.open(spool, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return destination
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


class ProducerClient:
    def __init__(self, home: str | os.PathLike[str] | None = None, *, socket_path: str | os.PathLike[str] | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.home = resolve_home(home)
        self.socket_path = Path(socket_path) if socket_path is not None else self.home / "monitor.sock"
        self.timeout = timeout

    def send(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Send once; return ACK, or spool the same event and raise ClientError."""
        prepared = prepare_event(event, self.home)
        try:
            ack = self._exchange(prepared)
        except Exception as exc:
            path = spool_event(prepared, self.home)
            raise ClientError(f"durable ACK uncertain; event retained at {path}: {exc}") from exc
        return ack

    def _exchange(self, event: Mapping[str, Any]) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(self.socket_path))
            connection.sendall(_event_bytes(event))
            chunks = bytearray()
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    raise ClientError("connection closed before durable ACK")
                chunks.extend(chunk)
                if len(chunks) > protocol.MAX_FRAME_BYTES:
                    raise ClientError("daemon reply exceeds frame limit")
                newline = chunks.find(b"\n")
                if newline >= 0:
                    if newline != len(chunks) - 1:
                        raise ClientError("daemon sent multiple or trailing reply data")
                    break
            reply = protocol.decode(bytes(chunks))
            if reply.get("type") != "ack" or reply.get("event_id") != event["event_id"]:
                raise ClientError("daemon reply is not the matching durable ACK")
            return reply
