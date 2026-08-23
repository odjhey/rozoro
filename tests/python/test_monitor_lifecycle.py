import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from lib.rozoro_monitor import protocol
from lib.rozoro_monitor.server import MonitorServer
from lib.rozoro_monitor.store import EventStore

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
