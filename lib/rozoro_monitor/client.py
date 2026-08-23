"""Synchronous protocol-v1 producer client with a durable outbox spool."""

from __future__ import annotations

import fcntl
import os
import socket
import stat
from pathlib import Path
from typing import Any, Mapping

from . import protocol

DEFAULT_TIMEOUT = 2.0
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class ClientError(RuntimeError):
    """The event was not proven durably accepted."""


class UnsafePathError(ClientError):
    """A client state path failed ownership, type, or permission checks."""


def _check_private(info: os.stat_result, label: str, *, directory: bool) -> None:
    wanted = stat.S_ISDIR if directory else stat.S_ISREG
    if not wanted(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise UnsafePathError(f"refusing unsafe {'directory' if directory else 'file'}: {label}")


def _trusted_directory(info: os.stat_result, label: str) -> None:
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise UnsafePathError(f"refusing untrusted ancestor directory: {label}")


def _is_trusted_path(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not stat.S_IMODE(info.st_mode) & 0o022


def _is_strictly_private_path(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not stat.S_IMODE(info.st_mode) & 0o077


def _create_home_from_trusted_ancestor(path: Path) -> int:
    """Create or repair components durably, holding dirfds throughout.

    Every descendant link is parent-fsynced even when it already exists. That
    makes retry repair a link whose first creation succeeded but parent fsync
    failed before durability was known.
    """
    path = path.absolute()
    if ".." in path.parts:
        raise UnsafePathError(f"refusing parent traversal in ROZORO_HOME: {path}")

    # Climb to the first existing, trusted ancestor. It is a pass-through
    # trust boundary and may be an ordinary owner-controlled directory (e.g.
    # 0755); everything below it is client-managed and must be strictly
    # private, so it must not be swept into the strict per-component check.
    ancestor = path
    while not _is_trusted_path(ancestor):
        if ancestor.parent == ancestor:
            raise UnsafePathError(f"no existing trusted ancestor for ROZORO_HOME: {path}")
        ancestor = ancestor.parent
    # Keep climbing through already-existing, strictly private ancestors: a
    # 0700 directory always passes the strict per-component check below, so
    # re-sweeping it is safe and lets retries repair an uncertain link left
    # by an earlier failed fsync higher up the client-managed chain. Stop at
    # the first ancestor that is merely a lenient pass-through boundary.
    while _is_strictly_private_path(ancestor) and ancestor.parent != ancestor and _is_trusted_path(ancestor.parent):
        ancestor = ancestor.parent
    relative = path.relative_to(ancestor).parts

    fd = os.open(ancestor, _DIR_FLAGS)
    try:
        _trusted_directory(os.fstat(fd), str(ancestor))
        for name in relative:
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child_fd = os.open(name, _DIR_FLAGS, dir_fd=fd)
            try:
                _check_private(os.fstat(child_fd), name, directory=True)
                # Always repair the link: an earlier mkdir may have survived a
                # failed fsync and cannot otherwise be distinguished on retry.
                os.fsync(fd)
            except BaseException:
                os.close(child_fd)
                raise
            os.close(fd)
            fd = child_fd
        _check_private(os.fstat(fd), str(path), directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_home(home: str | os.PathLike[str] | None, *, create: bool = True) -> tuple[Path, int]:
    path = Path(home) if home is not None else Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    path = path.absolute()
    if create:
        try:
            fd = _create_home_from_trusted_ancestor(path)
        except OSError as exc:
            raise UnsafePathError(f"cannot create private directory {path}: {exc}") from exc
        return path, fd
    fd = os.open(path, _DIR_FLAGS)
    try:
        _check_private(os.fstat(fd), str(path), directory=True)
        return path, fd
    except BaseException:
        os.close(fd)
        raise


def resolve_home(home: str | os.PathLike[str] | None = None) -> Path:
    path, fd = _open_home(home)
    os.close(fd)
    return path


def _open_subdir(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    try:
        _check_private(os.fstat(fd), name, directory=True)
        # Existing may mean a prior creation whose parent fsync failed.
        os.fsync(parent_fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_file(directory_fd: int, name: str, flags: int, mode: int = 0o600) -> int:
    fd = os.open(name, flags | _FILE_NOFOLLOW, mode, dir_fd=directory_fd)
    try:
        _check_private(os.fstat(fd), name, directory=False)
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_file(directory_fd: int, name: str) -> bytes | None:
    try:
        fd = _open_file(directory_fd, name, os.O_RDONLY)
    except FileNotFoundError:
        return None
    try:
        chunks = bytearray()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return bytes(chunks)
            chunks.extend(chunk)
            if len(chunks) > protocol.MAX_FRAME_BYTES:
                raise ClientError(f"state file is oversized: {name}")
    finally:
        os.close(fd)


def _producer_event(event: Mapping[str, Any], *, allow_missing_seq: bool) -> dict[str, Any]:
    prepared = dict(event)
    message_type = prepared.get("type")
    if not isinstance(message_type, str) or not protocol.requires_producer_seq(message_type):
        raise protocol.ProtocolError("invalid-event", "client accepts producer lifecycle events only", "type")
    if allow_missing_seq and "producer_seq" not in prepared:
        probe = dict(prepared, producer_seq=1)
        protocol.validate(probe)
    else:
        protocol.validate(prepared)
    return prepared


def _same_logical_event(candidate: Mapping[str, Any], reserved: Mapping[str, Any]) -> bool:
    candidate_without_seq = {key: value for key, value in candidate.items() if key != "producer_seq"}
    reserved_without_seq = {key: value for key, value in reserved.items() if key != "producer_seq"}
    if candidate_without_seq != reserved_without_seq:
        return False
    return "producer_seq" not in candidate or candidate["producer_seq"] == reserved["producer_seq"]


def _write_temp(directory_fd: int, data: bytes) -> str:
    # tempfile has no dirfd API. Create unpredictable names relative to the held
    # directory descriptor, never by resolving the directory pathname again.
    for _ in range(100):
        name = f".event-{os.getpid()}-{os.urandom(12).hex()}.tmp"
        try:
            fd = _open_file(directory_fd, name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError:
            continue
    else:
        raise ClientError("could not allocate spool temporary")
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    return name


def _publish_locked(spool_fd: int, event: Mapping[str, Any]) -> None:
    """Publish under the spool lock; differing content can never be replaced."""
    name = f"{event['event_id']}.json"
    data = protocol.encode(dict(event)).encode("utf-8")
    existing = _read_file(spool_fd, name)
    if existing is not None:
        if existing != data:
            raise ClientError(f"spool collision for event_id {event['event_id']}")
        return
    temporary = _write_temp(spool_fd, data)
    try:
        # All publishers hold .lock, making check+atomic rename no-clobber.
        os.rename(temporary, name, src_dir_fd=spool_fd, dst_dir_fd=spool_fd)
        os.fsync(spool_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=spool_fd)
        except FileNotFoundError:
            pass


def _locked_fd(directory_fd: int, name: str) -> int:
    try:
        fd = _open_file(directory_fd, name, os.O_RDWR | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        fd = _open_file(directory_fd, name, os.O_RDWR)
    try:
        # Repair uncertain first creation before relying on this inode.
        os.fsync(directory_fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_counter(fd: int, label: str) -> int:
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, 64)
    if not raw:
        return 0
    try:
        value = int(raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsafePathError(f"invalid producer sequence state: {label}") from exc
    if not 0 <= value <= protocol.MAX_INTEGER:
        raise UnsafePathError(f"invalid producer sequence state: {label}")
    return value


def _save_counter(fd: int, value: int) -> None:
    data = str(value).encode("ascii")
    os.lseek(fd, 0, os.SEEK_SET)
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]
    os.ftruncate(fd, len(data))
    os.fsync(fd)


def _max_spooled_seq(spool_fd: int, session_id: str) -> int:
    """Recover reservations published before a crashed counter update."""
    maximum = 0
    for name in os.listdir(spool_fd):
        if not name.endswith(".json"):
            continue
        data = _read_file(spool_fd, name)
        if data is None:
            continue
        try:
            reserved = protocol.decode(data)
            _producer_event(reserved, allow_missing_seq=False)
        except (protocol.ProtocolError, UnicodeError) as exc:
            raise ClientError(f"malformed spool evidence must be repaired: {name}") from exc
        if reserved["session_id"] == session_id:
            maximum = max(maximum, reserved["producer_seq"])
    return maximum


def prepare_event(event: Mapping[str, Any], home: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Durably reserve an envelope before it can be sent.

    Repeating an event_id returns its original envelope and producer_seq. The
    spool publication precedes advancement of the sequence cursor, so a crash
    cannot leave an unpublished permanent reducer gap.
    """
    candidate = _producer_event(event, allow_missing_seq=True)
    root, home_fd = _open_home(home)
    del root
    try:
        spool_fd = _open_subdir(home_fd, "spool")
        try:
            sequence_fd = _open_subdir(home_fd, "producer-seq")
        except Exception:
            os.close(spool_fd)
            raise
        try:
            spool_lock = _locked_fd(spool_fd, ".lock")
            try:
                existing_data = _read_file(spool_fd, f"{candidate['event_id']}.json")
                if existing_data is not None:
                    existing = protocol.decode(existing_data)
                    _producer_event(existing, allow_missing_seq=False)
                    if not _same_logical_event(candidate, existing):
                        raise ClientError(f"spool collision for event_id {candidate['event_id']}")
                    return existing

                session_id = candidate["session_id"]
                counter_fd = _locked_fd(sequence_fd, f"{session_id}.seq")
                try:
                    previous = max(
                        _read_counter(counter_fd, session_id),
                        _max_spooled_seq(spool_fd, session_id),
                    )
                    supplied = candidate.get("producer_seq")
                    if supplied is None:
                        value = previous + 1
                    else:
                        value = supplied
                        if value != previous + 1:
                            raise ClientError("supplied producer_seq is not a new reservation")
                    if value > protocol.MAX_INTEGER:
                        raise ClientError(f"producer sequence exhausted for {session_id}")
                    prepared = dict(candidate, producer_seq=value)
                    _producer_event(prepared, allow_missing_seq=False)
                    _publish_locked(spool_fd, prepared)
                    _save_counter(counter_fd, value)
                    return prepared
                finally:
                    os.close(counter_fd)
            finally:
                os.close(spool_lock)
        finally:
            os.close(sequence_fd)
            os.close(spool_fd)
    finally:
        os.close(home_fd)


def spool_event(event: Mapping[str, Any], home: str | os.PathLike[str] | None = None) -> Path:
    """Idempotently verify/publish a fully allocated producer envelope."""
    validated = _producer_event(event, allow_missing_seq=False)
    root, home_fd = _open_home(home)
    try:
        spool_fd = _open_subdir(home_fd, "spool")
        try:
            lock_fd = _locked_fd(spool_fd, ".lock")
            try:
                _publish_locked(spool_fd, validated)
            finally:
                os.close(lock_fd)
        finally:
            os.close(spool_fd)
    finally:
        os.close(home_fd)
    return root / "spool" / f"{validated['event_id']}.json"


def _remove_reserved(event: Mapping[str, Any], home: str | os.PathLike[str]) -> None:
    _, home_fd = _open_home(home, create=False)
    try:
        spool_fd = _open_subdir(home_fd, "spool")
        try:
            lock_fd = _locked_fd(spool_fd, ".lock")
            try:
                name = f"{event['event_id']}.json"
                data = _read_file(spool_fd, name)
                if data is None:
                    return
                expected = protocol.encode(dict(event)).encode("utf-8")
                if data != expected:
                    raise ClientError(f"spool identity changed before ACK cleanup: {event['event_id']}")
                os.unlink(name, dir_fd=spool_fd)
                os.fsync(spool_fd)
            finally:
                os.close(lock_fd)
        finally:
            os.close(spool_fd)
    finally:
        os.close(home_fd)


class ProducerClient:
    def __init__(self, home: str | os.PathLike[str] | None = None, *, socket_path: str | os.PathLike[str] | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.home = resolve_home(home)
        self.socket_path = Path(socket_path) if socket_path is not None else self.home / "monitor.sock"
        self.timeout = timeout

    def send(self, event: Mapping[str, Any]) -> dict[str, Any]:
        """Reserve before send; retain reservation unless a matching ACK arrives."""
        prepared = prepare_event(event, self.home)
        try:
            ack = self._exchange(prepared)
        except Exception as exc:
            raise ClientError(f"durable ACK uncertain; event retained in spool: {exc}") from exc
        _remove_reserved(prepared, self.home)
        return ack

    def _exchange(self, event: Mapping[str, Any]) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(self.socket_path))
            connection.sendall(protocol.encode(dict(event)).encode("utf-8"))
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
