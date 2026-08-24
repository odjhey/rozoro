#!/usr/bin/env python3
"""Lifecycle and diagnostic CLI for the local Rozoro monitor."""
import sys

MIN_PYTHON = (3, 11)
PYTHON_ERROR = "Rozoro monitor requires Python >=3.11 (Python 3.10 is not yet supported; EOL Python 3.9 is out of policy); install Homebrew Python with `brew install python` and ensure its python3 precedes older interpreters on PATH"

if sys.version_info < MIN_PYTHON:
    print(f"monitor unavailable: {PYTHON_ERROR} (found {sys.version.split()[0]} at {sys.executable})", file=sys.stderr)
    raise SystemExit(2)

import argparse
import fcntl
import json
import os
import socket
import stat
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.rozoro_monitor import protocol
from lib.rozoro_monitor.client import _open_home


def home_path() -> Path:
    return Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser().absolute()


def down(home: Path, error: str | None = None) -> dict:
    return {"running": False, "socket": str(home / "monitor.sock"), "pid": None, "schema_version": 0,
            "last_durable_seq": 0, "last_durable_time": None, "clients": 0,
            "task_count": 0, "driver_count": 0, "generation": 0,
            "delivered_generation": 0, "acked_generation": 0, "pending_count": 0,
            "spool_backlog": spool_count(home), "spool_errors": 0,
            "last_spool_error": error, "herdr_connected": False,
            "herdr_last_error": "monitor down", "herdr_inventory_errors": 0,
            "herdr_task_count": 0, "drivers": [], "health_state": "down"}


def spool_count(home: Path) -> int:
    try:
        return sum(name != ".lock" for name in os.listdir(home / "spool"))
    except OSError:
        return 0


def exchange(home: Path, request: dict, timeout: float = 1.0) -> dict:
    _, home_fd = _open_home(home, create=False)
    try:
        before = os.stat("monitor.sock", dir_fd=home_fd, follow_symlinks=False)
        if (not stat.S_ISSOCK(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o077):
            raise RuntimeError("monitor.sock must be an owner-private socket")
        identity = (before.st_dev, before.st_ino)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(home / "monitor.sock"))
            connection.sendall(protocol.encode(request).encode())
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = connection.recv(65536)
                if not chunk:
                    raise RuntimeError("socket closed before response")
                data.extend(chunk)
                if len(data) > protocol.MAX_FRAME_BYTES:
                    raise RuntimeError("response is oversized")
        result = protocol.decode(bytes(data))
        stop_completed = (
            request.get("type") == "monitor.stop"
            and result == {"v": 1, "type": "ok", "request_id": request.get("request_id")}
        )
        if stop_completed:
            # Deterministic process-test seam: model a client descheduled after
            # receiving OK while the daemon completes socket cleanup.
            delay = float(os.environ.get("ROZORO_MONITOR_TEST_STOP_POST_RESPONSE_DELAY", "0"))
            if delay > 0:
                time.sleep(delay)
        try:
            after = os.stat("monitor.sock", dir_fd=home_fd, follow_symlinks=False)
        except FileNotFoundError:
            if not stop_completed:
                raise RuntimeError("monitor.sock disappeared during exchange")
        else:
            if (after.st_dev, after.st_ino) != identity:
                raise RuntimeError("monitor.sock was replaced during exchange")
        return result
    finally:
        os.close(home_fd)


def health(home: Path, timeout: float = 1.0) -> dict:
    request = {"v": 1, "type": "health", "request_id": "cli-" + uuid.uuid4().hex}
    try:
        result = exchange(home, request, timeout)
        if result.get("type") != "health.result" or result.get("request_id") != request["request_id"]:
            raise RuntimeError("invalid health response")
        if result.get("socket") != str(home / "monitor.sock"):
            raise RuntimeError("health response names a different monitor socket")
        result.pop("v", None); result.pop("type", None); result.pop("request_id", None)
        result["health_state"] = "healthy" if result.get("herdr_connected") else "disconnected"
        return result
    except Exception as exc:
        return down(home, str(exc)[:128])


def print_status(value: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return
    state = "running" if value["running"] else "down"
    print(f"monitor: {state}")
    print(f"socket: {value['socket']}")
    print(f"schema: {value['schema_version']}  last durable seq: {value['last_durable_seq']}")
    print(f"clients: {value['clients']}  tasks: {value['task_count']}  drivers: {value['driver_count']}")
    print(f"generation: {value['generation']}  delivered: {value['delivered_generation']}  ack: {value['acked_generation']}")
    print(f"pending: {value['pending_count']}  spool: {value['spool_backlog']}  spool errors: {value['spool_errors']}")
    for driver in value.get("drivers", []):
        print(f"driver {driver['driver_id']}: adapter={driver['adapter_state']} delivery={driver['delivery_state']} pending={driver['pending']} delivered-unacked={driver['delivered_unacked']} retrying={driver['retrying']} error={driver.get('last_error') or 'none'}")
    if value.get("last_spool_error"):
        print(f"diagnostic: {value['last_spool_error']}")


def start(home: Path) -> int:
    try:
        _, home_fd = _open_home(home)
    except Exception as exc:
        print(f"monitor start refused: {exc}", file=sys.stderr)
        return 1
    current = health(home)
    if current["running"]:
        os.close(home_fd)
        print("monitor already running", file=sys.stderr)
        return 0
    try:
        log_fd = os.open("monitor.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NONBLOCK
                         | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=home_fd)
        info = os.fstat(log_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            os.close(log_fd)
            raise RuntimeError("monitor.log must be an owner-private regular file")
        os.fchmod(log_fd, 0o600)
        log = os.fdopen(log_fd, "ab", buffering=0)
        try:
            subprocess.Popen([sys.executable, str(ROOT / "bin" / "rozorod.py"), "--home", str(home)],
                             cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, close_fds=True)
        finally:
            log.close()
    except Exception as exc:
        print(f"monitor start refused: {exc}", file=sys.stderr)
        return 1
    finally:
        os.close(home_fd)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = health(home, 0.25)
        if result["running"]:
            print("monitor started")
            return 0
        time.sleep(0.05)
    print("monitor failed to become healthy; inspect monitor.log", file=sys.stderr)
    return 1


def proven_owner(home: Path) -> tuple[int, dict]:
    _, home_fd = _open_home(home, create=False)
    try:
        lock_fd = os.open("monitor.lock", os.O_RDONLY | os.O_NONBLOCK
                          | getattr(os, "O_NOFOLLOW", 0), dir_fd=home_fd)
        info = os.fstat(lock_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise RuntimeError("monitor.lock is not an owner-private regular file")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            raise RuntimeError("monitor.lock is not actively held")
        raw = os.read(lock_fd, 512)
        lock = json.loads(raw)
        socket_info = os.stat("monitor.sock", dir_fd=home_fd, follow_symlinks=False)
        if (not stat.S_ISSOCK(socket_info.st_mode) or socket_info.st_uid != os.geteuid()
                or stat.S_IMODE(socket_info.st_mode) & 0o077):
            raise RuntimeError("monitor.sock is not the owner-private socket")
        before = health(home)
        expected = (socket_info.st_dev, socket_info.st_ino)
        if (not before["running"] or int(lock["pid"]) != before["pid"]
                or (int(lock["socket_dev"]), int(lock["socket_ino"])) != expected):
            raise RuntimeError("lock record does not identify the live endpoint owner")
        second = os.stat("monitor.sock", dir_fd=home_fd, follow_symlinks=False)
        if (second.st_dev, second.st_ino) != expected:
            raise RuntimeError("monitor ownership changed during proof")
        os.close(home_fd)
        return lock_fd, before
    except BaseException:
        if 'lock_fd' in locals(): os.close(lock_fd)
        os.close(home_fd)
        raise


def reset(home: Path, force: bool) -> int:
    """Remove only daemon-owned event-bus state for an explicit schema rollback."""
    if not force:
        print("monitor reset requires --force; task folders are preserved", file=sys.stderr)
        return 1
    lock_fd = None
    try:
        _, home_fd = _open_home(home, create=False)
    except FileNotFoundError:
        print("monitor state already absent")
        return 0
    try:
        lock_fd = os.open("monitor.lock", os.O_RDWR | os.O_CREAT | os.O_NONBLOCK
                          | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=home_fd)
        lock_info = os.fstat(lock_fd)
        if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != os.geteuid()
                or stat.S_IMODE(lock_info.st_mode) & 0o077):
            raise RuntimeError("monitor.lock is not an owner-private regular file")
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("monitor daemon owner lock is held") from exc

        # Preflight every entry before mutating any, preventing partial reset if
        # a later WAL/SHM path is unsafe.
        present = []
        for name in ("monitor.db", "monitor.db-wal", "monitor.db-shm"):
            try:
                info = os.stat(name, dir_fd=home_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise RuntimeError(f"refusing unsafe state entry: {name}")
            present.append(name)
        for name in present:
            os.unlink(name, dir_fd=home_fd)
    except Exception as exc:
        print(f"monitor reset refused: {exc}", file=sys.stderr)
        return 1
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(home_fd)
    print("event-bus database reset; task folders preserved")
    return 0


def stop(home: Path) -> int:
    lock_fd = None
    try:
        lock_fd, _owner = proven_owner(home)
        request = {"v": 1, "type": "monitor.stop", "request_id": "stop-" + uuid.uuid4().hex}
        reply = exchange(home, request)
        if reply != {"v": 1, "type": "ok", "request_id": request["request_id"]}:
            raise RuntimeError("endpoint did not acknowledge shutdown")
    except Exception as exc:
        print(f"monitor stop refused: {exc}", file=sys.stderr)
        return 1
    finally:
        if lock_fd is not None: os.close(lock_fd)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not health(home, 0.2)["running"]:
            print("monitor stopped")
            return 0
        time.sleep(0.05)
    print("monitor endpoint remained healthy after shutdown request", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="rozoro monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    sub.add_parser("start")
    status_parser = sub.add_parser("status"); status_parser.add_argument("--json", action="store_true")
    sub.add_parser("stop")
    reset_parser = sub.add_parser("reset")
    reset_parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    home = home_path()
    if args.command == "run":
        os.execv(sys.executable, [sys.executable, str(ROOT / "bin" / "rozorod.py"), "--home", str(home)])
    if args.command == "start": return start(home)
    if args.command == "stop": return stop(home)
    if args.command == "reset": return reset(home, args.force)
    result = health(home); print_status(result, args.json)
    return 0 if result["running"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
