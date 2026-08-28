"""Follow-up delivery: the store ledger, and the daemon that acts on it."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from lib.rozoro_monitor import protocol
from lib.rozoro_monitor.store import EventStore

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "bin" / "rozorod.py"
FAKE_HERDR = ROOT / "tests" / "test_helper" / "fake_herdr_daemon.py"


class PendingSendStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = EventStore(Path(self.temp.name) / "private" / "monitor.db")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_enqueue_records_a_pending_follow_up_with_a_deadline(self):
        self.store.enqueue_pending_send("send-1", "task-1", "look again", 120_000)
        row = self.store.pending_send("task-1")
        self.assertEqual((row["send_id"], row["state"], row["payload"]),
                         ("send-1", "pending", "look again"))
        self.assertGreater(row["deadline_at"], row["created_at"])
        self.assertIsNone(row["resolved_at"])

    def test_newer_follow_up_supersedes_the_one_still_waiting(self):
        self.store.enqueue_pending_send("send-1", "task-1", "stale intent", 120_000)
        self.store.enqueue_pending_send("send-2", "task-1", "current intent", 120_000)
        rows = {row["send_id"]: row for row in self.store._connection.execute(
            "SELECT * FROM pending_sends")}
        self.assertEqual(rows["send-1"]["state"], "cancelled")
        self.assertEqual(rows["send-1"]["error"], "superseded")
        self.assertEqual(rows["send-2"]["state"], "pending")
        # Only the newest text may reach the crew.
        claimed = self.store.claim_pending_send("task-1")
        self.assertEqual(claimed["payload"], "current intent")

    def test_a_follow_up_can_be_claimed_exactly_once(self):
        self.store.enqueue_pending_send("send-1", "task-1", "text", 120_000)
        self.assertEqual(self.store.claim_pending_send("task-1")["send_id"], "send-1")
        # A second observer racing the first must come away with nothing, or the
        # same text would be delivered into the crew's context twice.
        self.assertIsNone(self.store.claim_pending_send("task-1"))
        self.assertEqual(self.store.pending_send("task-1")["state"], "delivering")

    def test_two_follow_ups_cannot_be_open_for_one_task(self):
        self.store.enqueue_pending_send("send-1", "task-1", "text", 120_000)
        with self.assertRaises(Exception):
            self.store._connection.execute(
                """INSERT INTO pending_sends(send_id,task_id,payload,deadline_at)
                   VALUES('send-2','task-1','other','2099-01-01T00:00:00.000Z')""")

    def test_resolution_is_restricted_to_terminal_states(self):
        self.store.enqueue_pending_send("send-1", "task-1", "text", 120_000)
        self.store.claim_pending_send("task-1")
        self.store.resolve_pending_send("send-1", "delivered")
        row = self.store.pending_send("task-1")
        self.assertEqual(row["state"], "delivered")
        self.assertIsNotNone(row["resolved_at"])
        with self.assertRaises(ValueError):
            self.store.resolve_pending_send("send-1", "delivering")

    def test_sweep_expires_only_follow_ups_past_their_deadline(self):
        self.store.enqueue_pending_send("late", "task-late", "text", -1_000)
        self.store.enqueue_pending_send("early", "task-early", "text", 600_000)
        self.assertEqual(self.store.expired_pending_send_tasks(), ["task-late"])
        swept = {row["send_id"] for row in self.store.sweep_expired_pending_sends()}
        self.assertEqual(swept, {"late"})
        self.assertEqual(self.store.pending_send("task-late")["state"], "failed")
        self.assertEqual(self.store.pending_send("task-late")["error"], "timeout")
        self.assertEqual(self.store.pending_send("task-early")["state"], "pending")

    def test_a_delivery_abandoned_by_a_crash_fails_rather_than_retrying(self):
        self.store.enqueue_pending_send("send-1", "task-1", "text", 600_000)
        self.store.claim_pending_send("task-1")
        # Still 'delivering' long after it was claimed: the daemon died mid-flight
        # and the text may already have landed, so it must never be re-sent.
        self.assertEqual([row["send_id"] for row in
                          self.store.sweep_expired_pending_sends(stale_delivering_seconds=0)],
                         ["send-1"])
        row = self.store.pending_send("task-1")
        self.assertEqual(row["state"], "failed")
        self.assertIn("mid-delivery", row["error"])

    def test_a_delivery_still_in_flight_is_left_alone(self):
        self.store.enqueue_pending_send("send-1", "task-1", "text", 600_000)
        self.store.claim_pending_send("task-1")
        self.assertEqual(self.store.sweep_expired_pending_sends(stale_delivering_seconds=3600), [])
        self.assertEqual(self.store.pending_send("task-1")["state"], "delivering")


class PendingSendDaemonTests(unittest.TestCase):
    """The daemon end to end: a real rozorod against a live fake Herdr socket."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir(parents=True)
        os.chmod(self.home, 0o700)
        self.state = self.home / "state"
        self.state.mkdir()
        os.chmod(self.state, 0o700)
        self.herdr_root = Path(self.temp.name) / "herdr"
        self.herdr_root.mkdir()
        self.herdr_socket = Path(self.temp.name) / "herdr.sock"
        self.prompt_log = Path(self.temp.name) / "prompts.log"
        self.prompt_log.touch()
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        self.temp.cleanup()

    def set_status(self, pane, status):
        (self.herdr_root / f"status.{pane}").write_text(status + "\n")

    def write_task(self, task_id, pane):
        (self.state / f"{task_id}.meta").write_text(f"pane={pane}\n")

    def prompts(self):
        return [line.split("\t", 1) for line in
                self.prompt_log.read_text().splitlines() if line]

    def start_fake_herdr(self):
        process = subprocess.Popen(
            [sys.executable, str(FAKE_HERDR), str(self.herdr_socket),
             str(self.herdr_root), str(self.prompt_log)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.processes.append(process)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.herdr_socket.exists():
                return
            time.sleep(0.02)
        self.fail("fake herdr socket did not appear")

    def start_daemon(self, **env):
        process = subprocess.Popen(
            [sys.executable, str(DAEMON), "--home", str(self.home)], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "ROZORO_HERDR_SOCKET": str(self.herdr_socket),
                 "ROZORO_STATE_DIR": str(self.state),
                 "ROZORO_HERDR_SCAN_INTERVAL": "30",
                 "ROZORO_MONITOR_PENDING_SEND_SWEEP_INTERVAL": "0.2", **env})
        self.processes.append(process)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (self.home / "monitor.sock").exists():
                try:
                    self.exchange({"v": 1, "type": "health", "request_id": "h-1"})
                    return process
                except (ConnectionRefusedError, FileNotFoundError):
                    pass
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            time.sleep(0.02)
        self.fail("daemon socket did not appear")

    def exchange(self, message):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(5)
            connection.connect(str(self.home / "monitor.sock"))
            connection.sendall(protocol.encode(message).encode())
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = connection.recv(65536)
                if not chunk:
                    self.fail("daemon closed before response")
                data.extend(chunk)
            return protocol.decode(bytes(data))
        finally:
            connection.close()

    def enqueue(self, task_id, payload, timeout_ms=120_000):
        return self.exchange({"v": 1, "type": "send.enqueue", "request_id": "s-1",
                              "task_id": task_id, "payload": payload,
                              "timeout_ms": timeout_ms})

    def send_status(self, task_id):
        return self.exchange({"v": 1, "type": "send.status", "request_id": "q-1",
                              "task_id": task_id})

    def wait_for_state(self, task_id, state, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            reply = self.send_status(task_id)
            if reply.get("state") == state:
                return reply
            time.sleep(0.05)
        self.fail(f"{task_id} never reached {state}: {self.send_status(task_id)}")

    def test_an_idle_crew_receives_its_follow_up_in_the_same_round_trip(self):
        self.write_task("task-1", "p1")
        self.set_status("p1", "idle")
        self.start_fake_herdr()
        self.start_daemon()
        reply = self.enqueue("task-1", "look again")
        self.assertEqual(reply["state"], "delivered")
        self.assertEqual(self.prompts(), [["p1", "look again"]])

    def test_a_working_crew_is_not_interrupted_and_is_served_when_it_settles(self):
        self.write_task("task-1", "p1")
        self.set_status("p1", "working")
        self.start_fake_herdr()
        self.start_daemon()
        reply = self.enqueue("task-1", "look again")
        # The caller is released immediately, and nothing has reached the pane.
        self.assertEqual(reply["state"], "pending")
        self.assertEqual(self.prompts(), [])
        self.set_status("p1", "idle")
        self.wait_for_state("task-1", "delivered")
        self.assertEqual(self.prompts(), [["p1", "look again"]])

    def test_only_the_newest_follow_up_reaches_a_crew_that_was_busy(self):
        self.write_task("task-1", "p1")
        self.set_status("p1", "working")
        self.start_fake_herdr()
        self.start_daemon()
        self.assertEqual(self.enqueue("task-1", "stale intent")["state"], "pending")
        self.assertEqual(self.enqueue("task-1", "current intent")["state"], "pending")
        self.set_status("p1", "idle")
        self.wait_for_state("task-1", "delivered")
        self.assertEqual(self.prompts(), [["p1", "current intent"]])

    def test_an_overdue_follow_up_is_delivered_if_the_crew_is_in_fact_idle(self):
        # The deadline can lapse before any status edge arrives; a last live
        # check must run before the follow-up is written off as timed out.
        self.write_task("task-1", "p1")
        self.set_status("p1", "working")
        self.start_fake_herdr()
        self.start_daemon(ROZORO_HERDR_SCAN_INTERVAL="3600")
        self.assertEqual(self.enqueue("task-1", "look again", timeout_ms=1)["state"], "pending")
        # Change the pane out from under the subscription's notice.
        (self.herdr_root / "status.p1").write_text("idle\n")
        self.wait_for_state("task-1", "delivered")
        self.assertEqual(self.prompts(), [["p1", "look again"]])

    def test_a_follow_up_expires_when_the_crew_stays_busy(self):
        self.write_task("task-1", "p1")
        self.set_status("p1", "working")
        self.start_fake_herdr()
        self.start_daemon()
        self.assertEqual(self.enqueue("task-1", "look again", timeout_ms=1)["state"], "pending")
        reply = self.wait_for_state("task-1", "failed")
        self.assertEqual(reply["error"], "timeout")
        self.assertEqual(self.prompts(), [])

    def test_enqueue_is_refused_for_a_task_with_no_pane(self):
        self.start_fake_herdr()
        self.start_daemon()
        reply = self.enqueue("task-unknown", "look again")
        self.assertEqual(reply["state"], "failed")
        self.assertIn("no known pane", reply["error"])

    def test_send_status_reports_nothing_for_a_task_never_sent_to(self):
        self.write_task("task-1", "p1")
        self.set_status("p1", "idle")
        self.start_fake_herdr()
        self.start_daemon()
        self.assertEqual(self.send_status("task-1")["found"], False)


if __name__ == "__main__":
    unittest.main()
