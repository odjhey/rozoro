import concurrent.futures
import json
import os
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from lib.rozoro_monitor import protocol

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "bin" / "rozorod.py"


def event(number, session=None):
    session = session or f"session-{number}"
    return {"v": 1, "type": "turn.start", "event_id": f"event-{number}",
            "producer_seq": 1, "session_id": session, "harness": "claude",
            "role": "crew", "task_id": f"task-{number}", "turn_id": f"turn-{number}"}


class ServerProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        self.temp.cleanup()

    @property
    def socket_path(self):
        return self.home / "monitor.sock"

    def start(self, wait=True):
        process = subprocess.Popen(
            [sys.executable, str(DAEMON), "--home", str(self.home)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.processes.append(process)
        if wait:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.socket_path.exists():
                    try:
                        self.health()
                        return process
                    except (ConnectionRefusedError, FileNotFoundError):
                        pass
                if process.poll() is not None:
                    raise AssertionError(process.stderr.read().decode())
                time.sleep(0.02)
            self.fail("daemon socket did not appear")
        return process

    def exchange(self, message, connection=None):
        own = connection is None
        connection = connection or socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if own:
                connection.settimeout(3)
                connection.connect(str(self.socket_path))
            connection.sendall(protocol.encode(message).encode())
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = connection.recv(65536)
                if not chunk:
                    self.fail("daemon closed before response")
                data.extend(chunk)
            return protocol.decode(bytes(data))
        finally:
            if own:
                connection.close()

    def health(self):
        return self.exchange({"v": 1, "type": "health", "request_id": "health-1"})

    def test_concurrent_clients_duplicate_retry_and_commit_before_ack(self):
        self.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            replies = list(pool.map(lambda n: self.exchange(event(n)), range(1, 21)))
        self.assertEqual({reply["durable_seq"] for reply in replies}, set(range(1, 21)))
        duplicate = self.exchange(event(1))
        self.assertEqual(duplicate["durable_seq"], next(r["durable_seq"] for r in replies
                                                        if r["event_id"] == "event-1"))
        # Receipt of ACK proves the transaction is visible to an independent connection.
        db = sqlite3.connect(self.home / "monitor.db")
        try:
            self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 20)
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE event_id='event-1'").fetchone()[0], 1)
        finally:
            db.close()

    def test_malformed_and_oversized_frames_are_client_local_and_recoverable(self):
        self.start()
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(5)
        connection.connect(str(self.socket_path))
        connection.sendall(b"{bad json}\n")
        malformed = protocol.decode(connection.recv(4096))
        self.assertEqual((malformed["type"], malformed["code"]), ("frame.error", "invalid-json"))
        connection.sendall(b" " * (protocol.MAX_FRAME_BYTES + 10) + b"\n")
        oversized = protocol.decode(connection.recv(4096))
        self.assertEqual((oversized["type"], oversized["code"]), ("frame.error", "frame-too-large"))
        healthy = self.exchange({"v": 1, "type": "health", "request_id": "after-errors"}, connection)
        self.assertEqual(healthy["type"], "health.result")
        connection.close()
        self.assertEqual(self.health()["type"], "health.result")

    def test_sigterm_cleans_socket_and_sigkill_restart_recovers_stale_socket(self):
        process = self.start()
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertFalse(self.socket_path.exists())

        killed = self.start()
        killed.kill()
        killed.wait(timeout=5)
        self.assertTrue(self.socket_path.exists())
        restarted = self.start()
        self.assertEqual(self.health()["type"], "health.result")
        database = sqlite3.connect(self.home / "monitor.db")
        try:
            self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0],
                             self.health()["schema_version"])
        finally:
            database.close()
        restarted.send_signal(signal.SIGTERM)
        self.assertEqual(restarted.wait(timeout=5), 0)

    def test_stale_socket_permissions_and_second_daemon_refusal(self):
        self.home.mkdir(mode=0o700)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.socket_path))
        stale.close()
        process = self.start()
        self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.socket_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.home / "monitor.lock").stat().st_mode), 0o600)
        second = self.start(wait=False)
        self.assertEqual(second.wait(timeout=5), 2)
        self.assertIn("another rozorod owns", second.stderr.read().decode())
        self.assertEqual(self.health()["type"], "health.result")
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)

    def test_connectable_socket_is_never_unlinked_when_lock_is_available(self):
        self.home.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        listener.listen()
        try:
            process = self.start(wait=False)
            self.assertEqual(process.wait(timeout=5), 2)
            self.assertIn("refusing connectable", process.stderr.read().decode())
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.connect(str(self.socket_path))
            probe.close()
        finally:
            listener.close()


if __name__ == "__main__":
    unittest.main()
