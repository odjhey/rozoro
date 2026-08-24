"""Foreground, resource-bounded, single-owner AF_UNIX protocol-v1 server."""

from __future__ import annotations

import asyncio
import errno
import fcntl
import json
import os
import resource
import socket
import sqlite3
import stat
import sys
from pathlib import Path
from typing import Any

from . import protocol
from .notify import Coalescer, DeliveryResult, DeliveryStatus
from .client import _open_home
from .store import EventStore
from .herdr import (
    EmptySubscription, MembershipMonitor, PaneLevel, UnixHerdrSubscription,
    herdr_rpc, inventory, read_pane_level,
)

MAX_CLIENTS = int(os.environ.get("ROZORO_MONITOR_MAX_CLIENTS", "64"))
READ_TIMEOUT = float(os.environ.get("ROZORO_MONITOR_READ_TIMEOUT", "5.0"))
SPOOL_INTERVAL = float(os.environ.get("ROZORO_MONITOR_SPOOL_INTERVAL", "2.0"))
if MAX_CLIENTS < 2 or READ_TIMEOUT <= 0 or SPOOL_INTERVAL <= 0:
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
        self._previous_owner_dead = False
        self._previous_socket_identity: tuple[int, int] | None = None
        self._store: EventStore | None = None
        self._listener: socket.socket | None = None
        self._accept_task: asyncio.Task[None] | None = None
        self._spool_task: asyncio.Task[None] | None = None
        self._herdr: MembershipMonitor | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self._capacity = asyncio.Event()
        self._capacity.set()
        self._socket_identity: tuple[int, int] | None = None
        self._clients = 0
        self._active_drivers: dict[str, int] = {}
        self.shutdown_requested = asyncio.Event()
        self._spool_backlog = 0
        self._spool_errors = 0
        self._last_spool_error: str | None = None
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
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                previous = json.loads(os.read(fd, 512))
                previous_pid = int(previous["pid"])
                self._previous_socket_identity = (
                    int(previous["socket_dev"]), int(previous["socket_ino"])
                )
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                previous_pid = None
            if previous_pid is not None:
                try:
                    os.kill(previous_pid, 0)
                except ProcessLookupError:
                    self._previous_owner_dead = True
                except PermissionError:
                    pass
            self._lock_fd = fd
        except BaseException:
            os.close(fd)
            raise

    def _record_owner(self) -> None:
        assert self._lock_fd is not None and self._socket_identity is not None
        record = json.dumps({"pid": os.getpid(), "socket_dev": self._socket_identity[0],
                             "socket_ino": self._socket_identity[1]},
                            sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
        os.ftruncate(self._lock_fd, 0)
        os.lseek(self._lock_fd, 0, os.SEEK_SET)
        os.write(self._lock_fd, record)
        os.fsync(self._lock_fd)

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
            identity = (socket_info.st_dev, socket_info.st_ino)
            # Darwin reports ECONNREFUSED for a genuinely full live AF_UNIX
            # backlog. User-writable metadata cannot disambiguate that result,
            # so automatic deletion is never safe there.
            if (sys.platform == "darwin" or not self._previous_owner_dead
                    or self._previous_socket_identity != identity
                    or not self._socket_definitively_stale()):
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
            explicit_state = os.environ.get("ROZORO_STATE_DIR")
            state_dir = Path(explicit_state or str(self.home / "state"))
            try: state_dir.mkdir(mode=0o700)
            except FileExistsError: pass
            state_info = state_dir.lstat()
            if (not stat.S_ISDIR(state_info.st_mode) or state_info.st_uid != os.geteuid()
                    or state_dir.is_symlink()):
                raise UnsafeStateError("state must be an owner-private directory")
            if stat.S_IMODE(state_info.st_mode) & 0o077:
                if explicit_state: raise UnsafeStateError("external state directory must already be owner-private")
                os.chmod(state_dir,0o700,follow_symlinks=False)
            herdr_socket = os.environ.get("ROZORO_HERDR_SOCKET")
            if not herdr_socket:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "herdr", "session", "list", "--json", stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL)
                    stdout, _ = await asyncio.wait_for(proc.communicate(), 3.0)
                    sessions = json.loads(stdout).get("sessions", []) if proc.returncode == 0 else []
                    wanted = os.environ.get("RZR_SESSION")
                    selected = (next((item for item in sessions if item.get("name") == wanted), None)
                                if wanted else next((item for item in sessions if item.get("default") is True), None))
                    herdr_socket = None if selected is None else selected.get("socket_path")
                except (OSError, ValueError, TimeoutError): herdr_socket = None
            migration_inventory = None
            if self.db_path.exists():
                probe = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                try: existing_version = int(probe.execute("PRAGMA user_version").fetchone()[0])
                finally: probe.close()
                if existing_version == 6:
                    if not herdr_socket:
                        raise RuntimeError("schema 7 migration requires exact Herdr inventory availability")
                    metadata = inventory(state_dir)
                    if metadata.errors:
                        raise RuntimeError("schema 7 migration requires valid task metadata")
                    response = await herdr_rpc(herdr_socket, "agent.list", {}, timeout=3.0)
                    result = response.get("result") or {}
                    agents = result.get("agents", result if isinstance(result, list) else [])
                    panes = {item.get("pane_id") or item.get("target") for item in agents if isinstance(item, dict)}
                    migration_inventory = {task: member.pane_id for task, member in metadata.members.items()
                                           if member.pane_id in panes}
            spool_backlog = 0
            for spool in (self.home / "spool", *(self.home / "pi-producers").glob("*/spool")):
                try:
                    spool_backlog += sum(name != ".lock" for name in os.listdir(spool))
                except FileNotFoundError:
                    pass
            self._store = EventStore(self.db_path, state_dir=state_dir, spool_backlog=spool_backlog,
                                     migration_herdr_inventory=migration_inventory)
            self._import_spool()
            db_info = self._entry("monitor.db")
            if db_info is None or not stat.S_ISREG(db_info.st_mode):
                raise UnsafeStateError("database creation escaped private home")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                listener.bind(str(self.socket_path))
                listener.listen(self._client_limit)
                listener.setblocking(False)
            except BaseException:
                listener.close()
                raise
            self._assert_home_anchor()
            info = self._entry("monitor.sock")
            if info is None or not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                listener.close()
                raise UnsafeStateError("socket creation escaped private home")
            os.chmod("monitor.sock", 0o600, dir_fd=self._home_fd, follow_symlinks=False)
            self._socket_identity = (info.st_dev, info.st_ino)
            self._record_owner()
            self._listener = listener
            self._accept_task = asyncio.create_task(self._accept_loop())
            self._spool_task = asyncio.create_task(self._spool_loop())
            if herdr_socket:
                async def level_reader(pane_id: str) -> PaneLevel:
                    return await read_pane_level(
                        herdr_socket, pane_id,
                        timeout=float(os.environ.get("ROZORO_HERDR_RPC_TIMEOUT", "3")))

                async def reconcile(task_id: str, level: PaneLevel) -> None:
                    assert self._store is not None
                    self._store.reconcile_herdr_liveness(task_id, pane_exists=level.exists)

                async def activate(task_id: str) -> None:
                    assert self._store is not None
                    self._store.activate_task_membership(task_id)

                async def retire(task_id: str) -> None:
                    assert self._store is not None
                    self._store.retire_task_membership(task_id)

                self._herdr = MembershipMonitor(
                    state_dir, lambda panes: (UnixHerdrSubscription(herdr_socket, panes)
                                              if panes else EmptySubscription()),
                    level_reader, reconcile, activate=activate, retire=retire,
                    scan_interval=float(os.environ.get("ROZORO_HERDR_SCAN_INTERVAL", "30")),
                    hint_interval=float(os.environ.get("ROZORO_HERDR_HINT_INTERVAL", ".2")),
                    debounce=float(os.environ.get("ROZORO_HERDR_DEBOUNCE", ".15")))
                await self._herdr.start()
        except BaseException:
            await self.close()
            raise

    def _import_spool(self) -> None:
        """Import complete spool envelopes; COMMIT always precedes unlink."""
        assert self._store is not None
        try:
            os.mkdir("spool", 0o700, dir_fd=self._home_fd)
        except FileExistsError:
            pass
        spool_fd = os.open("spool", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                           | getattr(os, "O_NOFOLLOW", 0), dir_fd=self._home_fd)
        try:
            info = os.fstat(spool_fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise UnsafeStateError("spool must be an owner-private directory")
            lock_fd = os.open(".lock", os.O_RDWR | os.O_CREAT
                              | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=spool_fd)
            try:
                lock_info = os.fstat(lock_fd)
                if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                        or stat.S_IMODE(lock_info.st_mode) & 0o077):
                    raise UnsafeStateError("spool lock must be an owner-private regular file")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                names = [name for name in os.listdir(spool_fd) if name != ".lock"]
                self._spool_backlog = len(names)
                errors: list[str] = []
                valid: list[tuple[int, str, bytes, dict[str, Any]]] = []
                for name in names:
                    if not name.endswith(".json"):
                        errors.append(f"incomplete spool evidence retained: {name}")
                        continue
                    try:
                        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK
                                     | getattr(os, "O_NOFOLLOW", 0), dir_fd=spool_fd)
                        try:
                            file_info = os.fstat(fd)
                            if (not stat.S_ISREG(file_info.st_mode) or file_info.st_uid != os.geteuid()
                                    or stat.S_IMODE(file_info.st_mode) & 0o077):
                                raise ValueError("unsafe entry")
                            data = os.read(fd, protocol.MAX_FRAME_BYTES + 1)
                        finally:
                            os.close(fd)
                        if len(data) > protocol.MAX_FRAME_BYTES:
                            raise ValueError("oversized envelope")
                        message = protocol.decode(data)
                        if not protocol.requires_producer_seq(message["type"]):
                            raise ValueError("not a lifecycle event")
                        if name != f"{message['event_id']}.json":
                            raise ValueError("filename/event identity mismatch")
                        valid.append((message["producer_seq"], name, data, message))
                    except (OSError, ValueError, UnicodeError, protocol.ProtocolError) as exc:
                        errors.append(f"malformed spool evidence retained: {name}: {exc}")
                for _, name, original, message in sorted(valid, key=lambda item: (item[0], item[1])):
                    try:
                        self._store.accept_event(message)  # returns only after COMMIT
                        check_fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK
                                           | getattr(os, "O_NOFOLLOW", 0), dir_fd=spool_fd)
                        try:
                            current = os.read(check_fd, protocol.MAX_FRAME_BYTES + 1)
                        finally:
                            os.close(check_fd)
                        if current != original:
                            raise ValueError("evidence changed after commit")
                        os.unlink(name, dir_fd=spool_fd)
                        os.fsync(spool_fd)
                        self._spool_backlog -= 1
                    except Exception as exc:
                        errors.append(f"spool import retained {name}: {exc}")
                self._spool_errors = len(errors)
                self._last_spool_error = errors[-1][:128] if errors else None
            finally:
                os.close(lock_fd)
        finally:
            os.close(spool_fd)

    async def _spool_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(SPOOL_INTERVAL)
                try:
                    self._import_spool()
                except Exception as exc:
                    self._spool_errors += 1
                    self._last_spool_error = f"spool scan failed: {exc}"[:128]
        except asyncio.CancelledError:
            pass

    async def _accept_loop(self) -> None:
        assert self._listener is not None
        loop = asyncio.get_running_loop()
        reserve = os.open(os.devnull, os.O_RDONLY)
        try:
            while True:
                if self._clients >= self._client_limit:
                    self._capacity.clear()
                    await self._capacity.wait()
                    continue
                try:
                    connection, _ = await loop.sock_accept(self._listener)
                except OSError as exc:
                    if exc.errno not in {errno.EMFILE, errno.ENFILE}:
                        raise
                    os.close(reserve)
                    reserve = -1
                    try:
                        connection, _ = self._listener.accept()
                        connection.close()
                    except (BlockingIOError, OSError):
                        pass
                    reserve = os.open(os.devnull, os.O_RDONLY)
                    await asyncio.sleep(0.05)
                    continue
                self._clients += 1
                reader, writer = await asyncio.open_connection(
                    sock=connection, limit=protocol.MAX_FRAME_BYTES + 1
                )
                self._writers.add(writer)
                task = asyncio.create_task(self._handle_client(reader, writer))
                self._client_tasks.add(task)
                task.add_done_callback(self._client_tasks.discard)
        except asyncio.CancelledError:
            pass
        finally:
            if reserve >= 0:
                os.close(reserve)

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
        message_type = raw.get("type")
        # Direction comes only from a recognized type, never attacker-selected
        # presence of event_id/request_id on an ambiguous frame.
        if isinstance(message_type, str) and protocol.requires_producer_seq(message_type):
            if code not in {"invalid-event", "invalid-field", "unsupported-type"} or "event_id" not in raw:
                return MonitorServer._frame_error(code)
            candidate = {"v": 1, "type": "event.error", "event_id": raw["event_id"], "code": code}
        elif message_type in {"health", "task.status", "driver.snapshot", "driver.disable", "driver.authority", "reconcile.pending", "reconcile.ack",
                              "monitor.stop", "watchtower.register", "watchtower.availability", "notification.pending", "notification.delivered", "reconcile", "ack-generation"}:
            if code not in {"invalid-message", "invalid-field", "unsupported-type"} or "request_id" not in raw:
                return MonitorServer._frame_error(code)
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
        registered_driver: tuple[str, str, int] | None = None
        pending_coalescer: Coalescer | None = None
        try:
            while True:
                frame = b""
                request_shutdown = False
                notification: dict[str, Any] | None = None
                try:
                    read = await self._read_frame(reader)
                    if read is None:
                        return
                    frame = read
                    message = protocol.decode(frame)
                    if message["type"] == "health":
                        assert self._store is not None
                        snapshot = self._store.health_snapshot()
                        for driver in snapshot.get("drivers", []):
                            driver["adapter_state"] = "connected" if driver["driver_id"] in self._active_drivers else "disconnected"
                        reply = {"v": 1, "type": "health.result", "request_id": message["request_id"],
                                 "running": True, "socket": str(self.socket_path),
                                 "clients": self._clients, **snapshot,
                                 "spool_backlog": self._spool_backlog,
                                 "spool_errors": self._spool_errors, "pid": os.getpid(),
                                 "last_spool_error": self._last_spool_error,
                                 **(self._herdr.health() if self._herdr else {
                                     "herdr_connected": False,
                                     "herdr_last_error": "Herdr socket unavailable",
                                     "herdr_inventory_errors": 0,
                                     "herdr_task_count": 0})}
                    elif message["type"] == "task.status":
                        assert self._store is not None
                        projection = self._store.task_projection(message["task_id"])
                        reply = {"v": 1, "type": "task.status.result", "request_id": message["request_id"],
                                 "task_id": message["task_id"], "found": projection is not None}
                        if projection is not None:
                            detail = json.loads(projection["projection_json"])
                            reply.update({"availability": projection["availability"],
                                          "foreground": detail.get("foreground", "unknown"),
                                          "background": detail.get("background", "unknown"),
                                          "background_count": detail.get("background_count"),
                                          "report_state": projection["report_state"],
                                          "verdict": projection["verdict"],
                                          "actionable_reason": projection["actionable_reason"]})
                    elif message["type"] == "driver.snapshot":
                        assert self._store is not None
                        reply = {"v": 1, "type": "driver.snapshot.result", "request_id": message["request_id"],
                                 "driver_id": message["driver_id"], **self._store.driver_snapshot(message["driver_id"])}
                    elif message["type"] == "driver.disable":
                        assert self._store is not None
                        self._store.disable_driver_authority(message["driver_id"])
                        reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
                    elif message["type"] == "driver.authority":
                        assert self._store is not None
                        reply = {"v": 1, "type": "driver.authority.result", "request_id": message["request_id"],
                                 "driver_id": message["driver_id"],
                                 "authority": self._store.driver_authority(message["driver_id"])}
                    elif message["type"] == "reconcile.pending":
                        assert self._store is not None
                        through, reports = self._store.reconcile_delivered(message["driver_id"])
                        reply = {"v": 1, "type": "reconcile.pending.result",
                                 "request_id": message["request_id"], "through": through, "reports": reports}
                    elif message["type"] == "reconcile.ack":
                        assert self._store is not None
                        self._store.ack_delivered(message["driver_id"], message["through"])
                        reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
                    elif message["type"] == "monitor.stop":
                        reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
                        request_shutdown = True
                    elif message["type"] == "watchtower.register":
                        assert self._store is not None
                        registration = self._store.register_driver(
                            message["driver_id"], message["session_id"], message["harness"])
                        registered_driver = (message["driver_id"], message["session_id"], registration["epoch"])
                        self._active_drivers[message["driver_id"]] = self._active_drivers.get(message["driver_id"], 0) + 1
                        pending_coalescer = Coalescer(
                            self._store, *registered_driver,
                            actuator=lambda _notification: DeliveryResult(DeliveryStatus.DEFERRED),
                        )
                        reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
                    elif message["type"] in {"watchtower.availability", "notification.pending", "notification.delivered", "reconcile", "ack-generation"}:
                        assert self._store is not None
                        if registered_driver is None or registered_driver[0] != message["driver_id"]:
                            raise protocol.ProtocolError("invalid-field", "request is not bound to this driver session")
                        driver_id, session_id, epoch = registered_driver
                        if message["type"] == "watchtower.availability":
                            reply = {"v": 1, "type": "watchtower.availability.result",
                                     "request_id": message["request_id"], "driver_id": driver_id,
                                     "availability": self._store.watchtower_availability(driver_id, session_id, epoch)}
                        elif message["type"] == "notification.pending":
                            if pending_coalescer is None:
                                raise protocol.ProtocolError("invalid-field", "pending poll has no coalescer")
                            offered = pending_coalescer.offer_pending()
                            reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
                            if offered is not None:
                                notification = {"v": 1, "type": "notification",
                                                "generation": offered.generation,
                                                "priority": offered.priority,
                                                "task_count": offered.task_count}
                        elif message["type"] == "notification.delivered":
                            self._store.confirm_delivery(driver_id, session_id, epoch, message["generation"])
                            reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
                        elif message["type"] == "reconcile":
                            reports = self._store.reconcile(driver_id, session_id, epoch, message["through"])
                            reply = {"v": 1, "type": "reconcile.result", "request_id": message["request_id"],
                                     "through": message["through"], "reports": reports}
                        else:
                            self._store.ack_generation(driver_id, session_id, epoch, message["through"])
                            reply = {"v": 1, "type": "ok", "request_id": message["request_id"]}
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
                except ValueError:
                    error = protocol.ProtocolError("invalid-field", "ledger request conflicts with durable state")
                    reply = self._correlated_error(frame, error) if frame else self._frame_error(error.code)
                except (MemoryError, RecursionError):
                    reply = self._frame_error("internal-error")
                await self._send(writer, reply)
                if notification is not None:
                    await self._send(writer, notification)
                if request_shutdown:
                    self.shutdown_requested.set()
                    return
                if reply.get("code") == "read-timeout":
                    return
        except (BrokenPipeError, ConnectionResetError, ConnectionError, TimeoutError):
            pass
        finally:
            if registered_driver is not None:
                driver = registered_driver[0]
                remaining = self._active_drivers.get(driver, 1) - 1
                if remaining > 0: self._active_drivers[driver] = remaining
                else: self._active_drivers.pop(driver, None)
            self._clients -= 1
            self._writers.discard(writer)
            self._capacity.set()
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionError):
                pass

    async def close(self) -> None:
        if self._herdr is not None:
            await self._herdr.close()
            self._herdr = None
        if self._spool_task is not None:
            self._spool_task.cancel()
            await asyncio.gather(self._spool_task, return_exceptions=True)
            self._spool_task = None
        if self._accept_task is not None:
            self._accept_task.cancel()
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._accept_task is not None:
            await asyncio.gather(self._accept_task, return_exceptions=True)
            self._accept_task = None
        # Close transports before waiting for handlers, so idle read deadlines
        # never delay SIGTERM shutdown.
        for writer in tuple(self._writers):
            writer.close()
        if self._client_tasks:
            await asyncio.gather(*tuple(self._client_tasks), return_exceptions=True)
        self._client_tasks.clear()
        self._writers.clear()
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
