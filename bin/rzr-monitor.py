#!/usr/bin/env python3
"""Lifecycle and diagnostic CLI for the local Rozoro monitor."""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.rozoro_monitor import protocol


def home_path() -> Path:
    return Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser().absolute()


def down(home: Path, error: str | None = None) -> dict:
    return {"running": False, "socket": str(home / "monitor.sock"), "schema_version": 0,
            "last_durable_seq": 0, "last_durable_time": None, "clients": 0,
            "task_count": 0, "driver_count": 0, "generation": 0,
            "delivered_generation": 0, "acked_generation": 0, "pending_count": 0,
            "spool_backlog": spool_count(home), "spool_errors": 0,
            "last_spool_error": error}


def spool_count(home: Path) -> int:
    try:
        return sum(name != ".lock" for name in os.listdir(home / "spool"))
    except OSError:
        return 0


def health(home: Path, timeout: float = 1.0) -> dict:
    request = {"v": 1, "type": "health", "request_id": "cli-" + uuid.uuid4().hex}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(home / "monitor.sock"))
            connection.sendall(protocol.encode(request).encode())
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = connection.recv(65536)
                if not chunk:
                    raise RuntimeError("socket closed before health response")
                data.extend(chunk)
                if len(data) > protocol.MAX_FRAME_BYTES:
                    raise RuntimeError("health response is oversized")
        result = protocol.decode(bytes(data))
        if result.get("type") != "health.result" or result.get("request_id") != request["request_id"]:
            raise RuntimeError("invalid health response")
        result.pop("v", None); result.pop("type", None); result.pop("request_id", None)
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
    if value.get("last_spool_error"):
        print(f"diagnostic: {value['last_spool_error']}")


def start(home: Path) -> int:
    current = health(home)
    if current["running"]:
        print("monitor already running", file=sys.stderr)
        return 0
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    log_fd = os.open(home / "monitor.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(log_fd, 0o600)
    log = os.fdopen(log_fd, "ab", buffering=0)
    try:
        subprocess.Popen([sys.executable, str(ROOT / "bin" / "rozorod.py"), "--home", str(home)],
                         cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True, close_fds=True)
    finally:
        log.close()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = health(home, 0.25)
        if result["running"]:
            print("monitor started")
            return 0
        time.sleep(0.05)
    print("monitor failed to become healthy; inspect monitor.log", file=sys.stderr)
    return 1


def proven_owner(home: Path) -> int:
    before = health(home)
    if not before["running"]:
        raise RuntimeError("monitor is not running")
    socket_info = (home / "monitor.sock").lstat()
    lock = json.loads((home / "monitor.lock").read_text())
    if (int(lock["socket_dev"]), int(lock["socket_ino"])) != (socket_info.st_dev, socket_info.st_ino):
        raise RuntimeError("lock does not prove ownership of the live socket")
    pid = int(lock["pid"])
    if pid <= 1:
        raise RuntimeError("invalid monitor owner pid")
    after = health(home)
    second_info = (home / "monitor.sock").lstat()
    if not after["running"] or (second_info.st_dev, second_info.st_ino) != (socket_info.st_dev, socket_info.st_ino):
        raise RuntimeError("monitor ownership changed during proof")
    return pid


def stop(home: Path) -> int:
    try:
        pid = proven_owner(home)
    except Exception as exc:
        print(f"monitor stop refused: {exc}", file=sys.stderr)
        return 1
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print("monitor stopped")
            return 0
        if not health(home, 0.2)["running"]:
            print("monitor stopped")
            return 0
        time.sleep(0.05)
    print("monitor did not stop after SIGTERM", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="rozoro monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    sub.add_parser("start")
    status_parser = sub.add_parser("status"); status_parser.add_argument("--json", action="store_true")
    sub.add_parser("stop")
    args = parser.parse_args()
    home = home_path()
    if args.command == "run":
        os.execv(sys.executable, [sys.executable, str(ROOT / "bin" / "rozorod.py"), "--home", str(home)])
    if args.command == "start": return start(home)
    if args.command == "stop": return stop(home)
    result = health(home); print_status(result, args.json)
    return 0 if result["running"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
