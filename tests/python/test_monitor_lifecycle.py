import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from lib.rozoro_monitor import protocol
from lib.rozoro_monitor.server import MonitorServer
from lib.rozoro_monitor.store import EventStore
from tests.test_helper import process_cleanup

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "bin" / "rozorod.py"
CLI = ROOT / "bin" / "rozoro"


def envelope(kind, event_id, seq):
    base = {"v": 1, "type": kind, "event_id": event_id, "producer_seq": seq,
            "session_id": "session-spool", "harness": "claude", "role": "crew",
            "task_id": "task-spool"}
    if kind == "turn.start": base["turn_id"] = "turn-spool"
    if kind == "turn.stop": base["background_active"] = False
    return base


class MonitorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rzr6-")
        self.home = Path(self.temp.name) / "h"
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
            if process.stdout is not None: process.stdout.close()
            if process.stderr is not None: process.stderr.close()
        self.temp.cleanup()

    def env(self, **extra):
        return {**os.environ, "ROZORO_HOME": str(self.home), **extra}

    def cli(self, *args, check=False, **extra):
        return subprocess.run([str(CLI), "monitor", *args], cwd=ROOT, env=self.env(**extra),
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=12, check=check)

    def start_daemon(self, interval="0.05"):
        process = subprocess.Popen([sys.executable, str(DAEMON), "--home", str(self.home)],
                                   cwd=ROOT, env=self.env(ROZORO_MONITOR_SPOOL_INTERVAL=interval),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        process_cleanup.register(process, self.home)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.cli("status", "--json")
            if result.returncode == 0: return process
            if process.poll() is not None: self.fail(process.stderr.read().decode())
            time.sleep(.02)
        self.fail("daemon did not start")

    def write_spool(self, message, name=None):
        spool = self.home / "spool"; spool.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.home, 0o700); os.chmod(spool, 0o700)
        path = spool / (name or f"{message['event_id']}.json")
        path.write_text(protocol.encode(message)); os.chmod(path, 0o600)
        return path

    def test_startup_shuffled_register_last_and_retry_is_one_logical_event(self):
        start = envelope("turn.start", "evt-start", 1)
        stop = envelope("turn.stop", "evt-stop", 2)
        register = envelope("session.register", "evt-register", 3)
        # Deliberately filename-shuffled; producer order, not directory order, wins.
        self.write_spool(stop); self.write_spool(register); self.write_spool(start)
        self.start_daemon()
        db = sqlite3.connect(self.home / "monitor.db")
        try:
            self.assertEqual(db.execute("select count(*) from events").fetchone()[0], 3)
            self.assertEqual(db.execute("select availability from sessions").fetchone()[0], "quiescent")
        finally: db.close()
        self.assertFalse(list((self.home / "spool").glob("*.json")))
        # ACK-loss replay with the exact envelope deduplicates to one row.
        self.write_spool(start)
        deadline = time.monotonic() + 3
        while (self.home / "spool" / "evt-start.json").exists() and time.monotonic() < deadline:
            time.sleep(.03)
        db = sqlite3.connect(self.home / "monitor.db")
        try: self.assertEqual(db.execute("select count(*) from events where event_id='evt-start'").fetchone()[0], 1)
        finally: db.close()

    def test_commit_before_unlink_crash_replay_is_idempotent(self):
        message = envelope("session.register", "evt-commit-crash", 1)
        evidence = self.write_spool(message)
        server = MonitorServer(self.home)
        real_store = EventStore(self.home / "monitor.db")
        class CrashAfterCommit:
            def accept_event(inner, value):
                real_store.accept_event(value)
                raise RuntimeError("simulated crash after commit before unlink")
        server._store = CrashAfterCommit()
        server._import_spool()
        self.assertTrue(evidence.exists())
        server._store = real_store
        server._import_spool()
        self.assertFalse(evidence.exists())
        db = sqlite3.connect(self.home / "monitor.db")
        try: self.assertEqual(db.execute("select count(*) from events where event_id='evt-commit-crash'").fetchone()[0], 1)
        finally: db.close()
        real_store.close(); os.close(server._home_fd); server._home_fd = -1

    def test_periodic_import_and_malformed_temp_evidence_health(self):
        self.start_daemon()
        good = self.write_spool(envelope("session.register", "evt-periodic", 1))
        malformed = self.home / "spool" / "broken.json"; malformed.write_text("{partial"); os.chmod(malformed, 0o600)
        temporary = self.home / "spool" / ".event-crash.tmp"; temporary.write_text("partial"); os.chmod(temporary, 0o600)
        deadline = time.monotonic() + 3
        while good.exists() and time.monotonic() < deadline: time.sleep(.03)
        value = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(value["last_durable_seq"], 1)
        self.assertEqual(value["spool_backlog"], 2)
        self.assertGreaterEqual(value["spool_errors"], 2)
        self.assertTrue(malformed.exists()); self.assertTrue(temporary.exists())

    def test_start_rejects_home_and_log_symlinks_without_touching_targets(self):
        external_home = Path(self.temp.name) / "external-home"
        external_home.mkdir(mode=0o700)
        linked_home = Path(self.temp.name) / "linked-home"
        linked_home.symlink_to(external_home, target_is_directory=True)
        result = subprocess.run([str(CLI), "monitor", "start"], cwd=ROOT,
                                env={**os.environ, "ROZORO_HOME": str(linked_home)},
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((external_home / "monitor.log").exists())

        self.home.mkdir(mode=0o700)
        external_log = Path(self.temp.name) / "external.log"; external_log.write_text("sentinel")
        os.chmod(external_log, 0o644)
        (self.home / "monitor.log").symlink_to(external_log)
        result = self.cli("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(external_log.read_text(), "sentinel")
        self.assertEqual(oct(external_log.stat().st_mode & 0o777), "0o644")

    def test_spool_special_entries_never_block_start_periodic_health_or_sigterm(self):
        spool = self.home / "spool"; spool.mkdir(parents=True, mode=0o700)
        os.chmod(self.home, 0o700)
        os.mkfifo(spool / "fifo.json", 0o600)
        (spool / "directory.json").mkdir(mode=0o700)
        external = Path(self.temp.name) / "external-evidence"; external.write_text("sentinel")
        (spool / "symlink.json").symlink_to(external)
        process = self.start_daemon()
        value = json.loads(self.cli("status", "--json").stdout)
        self.assertGreaterEqual(value["spool_errors"], 3)
        self.assertTrue((spool / "fifo.json").exists())
        periodic = spool / "periodic-fifo.json"; os.mkfifo(periodic, 0o600)
        time.sleep(.12)
        self.assertTrue(json.loads(self.cli("status", "--json").stdout)["running"])
        started = time.monotonic(); process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=2), 0)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(external.read_text(), "sentinel")

    def test_health_rejects_endpoint_claiming_a_different_socket_path(self):
        self.home.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.home / "monitor.sock")); os.chmod(self.home / "monitor.sock", 0o600)
        listener.listen()
        def serve():
            connection, _ = listener.accept()
            try:
                data = b""
                while not data.endswith(b"\n"): data += connection.recv(4096)
                request = protocol.decode(data)
                reply = {"v": 1, "type": "health.result", "request_id": request["request_id"],
                         "running": True, "socket": "/tmp/different-monitor.sock", "pid": os.getpid(),
                         "schema_version": 3, "last_durable_seq": 0, "last_durable_time": None,
                         "clients": 1, "task_count": 0, "driver_count": 0, "generation": 0,
                         "delivered_generation": 0, "acked_generation": 0, "pending_count": 0,
                         "spool_backlog": 0, "spool_errors": 0, "last_spool_error": None}
                connection.sendall(protocol.encode(reply).encode())
            finally: connection.close(); listener.close()
        thread = threading.Thread(target=serve); thread.start()
        result = self.cli("status", "--json")
        thread.join(timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["running"])

    def test_cross_home_socket_symlink_never_adopts_or_stops_foreign_daemon(self):
        foreign_home = self.home
        self.start_daemon()
        other = Path(self.temp.name) / "other"; other.mkdir(mode=0o700)
        (other / "monitor.sock").symlink_to(foreign_home / "monitor.sock")
        env = {**os.environ, "ROZORO_HOME": str(other)}
        def other_cli(*args):
            return subprocess.run([str(CLI), "monitor", *args], cwd=ROOT, env=env,
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=12)
        status_result = other_cli("status", "--json")
        self.assertNotEqual(status_result.returncode, 0)
        self.assertFalse(json.loads(status_result.stdout)["running"])
        self.assertNotEqual(other_cli("stop").returncode, 0)
        self.assertNotEqual(other_cli("start").returncode, 0)
        self.assertTrue(json.loads(self.cli("status", "--json").stdout)["running"])

    def test_stop_refuses_unlocked_corrupt_and_reused_pid_records_without_signal(self):
        # FIFO stale locks must not block before their non-regular type is rejected.
        self.home.mkdir(mode=0o700)
        os.mkfifo(self.home / "monitor.lock", 0o600)
        started = time.monotonic()
        self.assertNotEqual(self.cli("stop").returncode, 0)
        self.assertLess(time.monotonic() - started, 1.0)
        (self.home / "monitor.lock").unlink()

        # A protocol-compatible foreign socket plus matching mutable JSON is not
        # enough: the lock must be actively held.
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.home / "monitor.sock")); listener.listen()
        socket_info = (self.home / "monitor.sock").lstat()
        (self.home / "monitor.lock").write_text(json.dumps({"pid": os.getpid(),
            "socket_dev": socket_info.st_dev, "socket_ino": socket_info.st_ino}))
        os.chmod(self.home / "monitor.lock", 0o600)
        try:
            refused = self.cli("stop")
            self.assertNotEqual(refused.returncode, 0)
        finally:
            listener.close(); (self.home / "monitor.sock").unlink(); (self.home / "monitor.lock").unlink()

        self.start_daemon()
        lock_path = self.home / "monitor.lock"; real = lock_path.read_text()
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.processes.append(unrelated)
        record = json.loads(real); record["pid"] = unrelated.pid
        lock_path.write_text(json.dumps(record)); os.chmod(lock_path, 0o600)
        self.assertNotEqual(self.cli("stop").returncode, 0)
        self.assertIsNone(unrelated.poll())
        lock_path.write_text("corrupt"); os.chmod(lock_path, 0o600)
        self.assertNotEqual(self.cli("stop").returncode, 0)
        self.assertIsNone(unrelated.poll())
        lock_path.write_text(real); os.chmod(lock_path, 0o600)
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertIsNone(unrelated.poll())

    def test_stop_succeeds_when_socket_unlinks_after_ok_before_client_postcheck(self):
        process = self.start_daemon()
        started = time.monotonic()
        stopped = self.cli("stop", ROZORO_MONITOR_TEST_STOP_POST_RESPONSE_DELAY="0.3")
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertGreaterEqual(time.monotonic() - started, 0.3)
        self.assertEqual(process.wait(timeout=2), 0)
        self.assertFalse((self.home / "monitor.sock").exists())
        self.assertFalse(json.loads(self.cli("status", "--json").stdout)["running"])

    def test_detached_start_status_stop_and_foreign_owner_refusal(self):
        started = self.cli("start")
        self.assertEqual(started.returncode, 0, started.stderr)
        status = json.loads(self.cli("status", "--json").stdout)
        self.assertTrue(status["running"]); self.assertIn("schema_version", status)
        lock_path = self.home / "monitor.lock"
        real = lock_path.read_text()
        record = json.loads(real); record["socket_ino"] += 1
        lock_path.write_text(json.dumps(record)); os.chmod(lock_path, 0o600)
        refused = self.cli("stop")
        self.assertNotEqual(refused.returncode, 0)
        self.assertTrue(json.loads(self.cli("status", "--json").stdout)["running"])
        lock_path.write_text(real); os.chmod(lock_path, 0o600)
        stopped = self.cli("stop")
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        down = self.cli("status", "--json")
        self.assertEqual(down.returncode, 1)
        self.assertFalse(json.loads(down.stdout)["running"])


if __name__ == "__main__": unittest.main()
