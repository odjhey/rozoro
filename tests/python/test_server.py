import concurrent.futures
import errno
import json
import os
import resource
import select
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

    def start(self, wait=True, env=None, nofile=None):
        def limit_files():
            if nofile is not None:
                resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
        process = subprocess.Popen(
            [sys.executable, str(DAEMON), "--home", str(self.home)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **(env or {})}, preexec_fn=limit_files if nofile else None,
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
        conflict = self.exchange({**event(1), "task_id": "task-conflict"})
        self.assertEqual(conflict, {"v": 1, "type": "event.error",
                                    "event_id": "event-1", "code": "invalid-event"})
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

    def test_validation_errors_preserve_only_safe_correlation_and_deep_json_recovers(self):
        self.start()
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(3)
        connection.connect(str(self.socket_path))
        invalid_event = {**event(1)}
        del invalid_event["task_id"]
        connection.sendall((json.dumps(invalid_event) + "\n").encode())
        self.assertEqual(protocol.decode(connection.recv(4096)),
                         {"v": 1, "type": "event.error", "event_id": "event-1",
                          "code": "invalid-event"})
        connection.sendall(b'{"v":1,"type":"health","request_id":"req-safe","event_id":"injected","extra":1}\n')
        self.assertEqual(protocol.decode(connection.recv(4096)),
                         {"v": 1, "type": "request.error", "request_id": "req-safe",
                          "code": "invalid-field"})
        connection.sendall(b'{"v":1,"type":"future","event_id":"evt-injected","request_id":"req-injected"}\n')
        ambiguous = protocol.decode(connection.recv(4096))
        self.assertEqual(ambiguous, {"v": 1, "type": "frame.error", "code": "unsupported-type"})
        connection.sendall((b"[" * 2000) + b"0" + (b"]" * 2000) + b"\n")
        self.assertIn(protocol.decode(connection.recv(4096))["code"],
                      {"invalid-json", "invalid-message"})
        self.assertEqual(self.exchange(
            {"v": 1, "type": "health", "request_id": "after-deep"}, connection
        )["type"], "health.result")
        connection.close()

    def test_idle_deadline_and_client_cap_refuse_deterministically(self):
        self.start(env={"ROZORO_MONITOR_MAX_CLIENTS": "3",
                        "ROZORO_MONITOR_READ_TIMEOUT": "0.25"})
        idle = []
        for _ in range(3):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(str(self.socket_path))
            idle.append(client)
        refused = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        refused.settimeout(2)
        try:
            refused.connect(str(self.socket_path))
        except ConnectionRefusedError:
            pass
        else:
            self.assertIn(protocol.decode(refused.recv(4096))["code"],
                          {"server-busy", "read-timeout"})
        finally:
            refused.close()
        for client in idle:
            self.assertEqual(protocol.decode(client.recv(4096))["code"], "read-timeout")
            client.close()
        self.assertEqual(self.health()["type"], "health.result")

    def test_low_fd_limit_reserves_capacity_and_refuses_before_emfile(self):
        self.start(env={"ROZORO_MONITOR_READ_TIMEOUT": "0.2"}, nofile=24)
        clients = []
        refused = False
        try:
            for _ in range(8):
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(2)
                try:
                    client.connect(str(self.socket_path))
                except OSError as exc:
                    self.assertIn(exc.errno, {errno.EAGAIN, errno.ECONNREFUSED})
                    refused = True
                    client.close()
                    break
                clients.append(client)
            replies = [protocol.decode(client.recv(4096)) for client in clients]
            refused = refused or any(reply.get("code") == "server-busy" for reply in replies)
            self.assertTrue(refused)
        finally:
            for client in clients:
                client.close()
        self.assertEqual(self.health()["type"], "health.result")

    def test_sigterm_closes_idle_transports_without_waiting_for_read_deadline(self):
        process = self.start(env={"ROZORO_MONITOR_READ_TIMEOUT": "30"})
        idle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        idle.connect(str(self.socket_path))
        time.sleep(0.05)
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=2), 0)
        self.assertLess(time.monotonic() - started, 1.0)
        idle.close()

    def test_sigterm_cleans_socket_and_sigkill_restart_recovers_stale_socket(self):
        process = self.start()
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertFalse(self.socket_path.exists())

        killed = self.start()
        accepted = self.exchange(event(91))
        self.assertEqual(accepted["type"], "ack")
        database = sqlite3.connect(self.home / "monitor.db")
        try:
            self.assertEqual(database.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        finally:
            database.close()
        killed.kill()
        killed.wait(timeout=5)
        self.assertTrue(self.socket_path.exists())
        if sys.platform == "darwin":
            refused = self.start(wait=False)
            self.assertEqual(refused.wait(timeout=5), 2)
            self.socket_path.unlink()  # explicit operator/supervisor stale cleanup
        restarted = self.start()
        self.assertEqual(self.health()["type"], "health.result")
        retried = self.exchange(event(91))
        self.assertEqual(retried["durable_seq"], accepted["durable_seq"])
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
        stale_info = self.socket_path.lstat()
        (self.home / "monitor.lock").write_text(json.dumps(
            {"pid": 99999999, "socket_dev": stale_info.st_dev, "socket_ino": stale_info.st_ino}
        ) + "\n")
        os.chmod(self.home / "monitor.lock", 0o600)
        if sys.platform == "darwin":
            refused = self.start(wait=False)
            self.assertEqual(refused.wait(timeout=5), 2)
            self.socket_path.unlink()
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

    def test_symlink_and_non_socket_entries_never_touch_external_targets(self):
        for entry in ("monitor.lock", "monitor.db", "monitor.db-wal", "monitor.db-shm", "monitor.sock"):
            with self.subTest(entry=entry):
                case_home = Path(self.temp.name) / f"home-{entry}"
                case_home.mkdir(mode=0o700)
                external = Path(self.temp.name) / f"external-{entry}"
                external.write_text("sentinel")
                os.chmod(external, 0o644)
                (case_home / entry).symlink_to(external)
                process = subprocess.Popen(
                    [sys.executable, str(DAEMON), "--home", str(case_home)], cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.processes.append(process)
                self.assertNotEqual(process.wait(timeout=5), 0)
                self.assertEqual(external.read_text(), "sentinel")
                self.assertEqual(stat.S_IMODE(external.stat().st_mode), 0o644)
                self.assertTrue((case_home / entry).is_symlink())

        case_home = Path(self.temp.name) / "home-regular-socket"
        case_home.mkdir(mode=0o700)
        regular = case_home / "monitor.sock"
        regular.write_text("do-not-unlink")
        process = subprocess.Popen([sys.executable, str(DAEMON), "--home", str(case_home)],
                                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        self.assertNotEqual(process.wait(timeout=5), 0)
        self.assertEqual(regular.read_text(), "do-not-unlink")

    def test_backlog_full_or_timeout_probe_is_treated_as_live(self):
        self.home.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        listener.listen(1)
        fillers = []
        backlog_full = False
        backlog_refused = False
        try:
            # Fill the tiny accept queue; whether the next connect times out or
            # succeeds, the daemon must conservatively preserve this live socket.
            for _ in range(4):
                filler = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                filler.settimeout(0.05)
                try:
                    filler.connect(str(self.socket_path))
                    fillers.append(filler)
                except OSError as exc:
                    backlog_full = True
                    backlog_refused = isinstance(exc, ConnectionRefusedError)
                    filler.close()
                    break
            self.assertTrue(fillers, "backlog test requires a proven queued connection")
            self.assertTrue(backlog_full, "backlog must be demonstrably full")
            if sys.platform == "darwin":
                self.assertTrue(backlog_refused, "Darwin full backlog must produce ECONNREFUSED")
            live_info = self.socket_path.lstat()
            (self.home / "monitor.lock").write_text(json.dumps({
                "pid": 99999999, "socket_dev": live_info.st_dev, "socket_ino": live_info.st_ino,
            }) + "\n")
            os.chmod(self.home / "monitor.lock", 0o600)
            process = self.start(wait=False)
            self.assertEqual(process.wait(timeout=5), 2)
            self.assertTrue(self.socket_path.exists())
            retry = self.start(wait=False)
            self.assertEqual(retry.wait(timeout=5), 2)
            self.assertTrue(self.socket_path.exists())
        finally:
            for filler in fillers:
                filler.close()
            listener.close()

    def test_dead_pid_record_for_different_socket_inode_cannot_authorize_unlink(self):
        self.home.mkdir(mode=0o700)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.socket_path))
        stale.close()
        info = self.socket_path.lstat()
        (self.home / "monitor.lock").write_text(json.dumps(
            {"pid": 99999999, "socket_dev": info.st_dev, "socket_ino": info.st_ino + 1}
        ) + "\n")
        os.chmod(self.home / "monitor.lock", 0o600)
        process = self.start(wait=False)
        self.assertEqual(process.wait(timeout=5), 2)
        self.assertEqual((self.socket_path.lstat().st_dev, self.socket_path.lstat().st_ino),
                         (info.st_dev, info.st_ino))

    def test_registration_is_correlated_and_same_session_reconnect_invalidates_old_socket(self):
        self.start()
        producer = {"v": 1, "type": "session.register", "event_id": "crew-register",
                    "producer_seq": 1, "session_id": "crew-session", "harness": "claude",
                    "role": "crew", "task_id": "task-1"}
        self.assertEqual(self.exchange(producer)["type"], "ack")

        clients = []
        streams = []
        try:
            for request_id in ("register-1", "register-2"):
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(3)
                client.connect(str(self.socket_path))
                stream = client.makefile("rwb", buffering=0)
                clients.append(client); streams.append(stream)
                stream.write(protocol.encode({"v": 1, "type": "watchtower.register",
                    "request_id": request_id, "session_id": "same-session",
                    "harness": "pi", "driver_id": "driver-1"}).encode())
                correlated = protocol.decode(stream.readline())
                self.assertEqual(correlated, {"v": 1, "type": "ok", "request_id": request_id})
                poll_id = f"poll-open-{request_id}"
                stream.write(protocol.encode({"v": 1, "type": "notification.pending",
                    "request_id": poll_id, "driver_id": "driver-1"}).encode())
                self.assertEqual(protocol.decode(stream.readline()),
                                 {"v": 1, "type": "ok", "request_id": poll_id})
                time.sleep(0.36)
                poll_id = f"poll-due-{request_id}"
                stream.write(protocol.encode({"v": 1, "type": "notification.pending",
                    "request_id": poll_id, "driver_id": "driver-1"}).encode())
                self.assertEqual(protocol.decode(stream.readline()),
                                 {"v": 1, "type": "ok", "request_id": poll_id})
                self.assertEqual(protocol.decode(stream.readline())["type"], "notification")

            streams[0].write(protocol.encode({"v": 1, "type": "reconcile", "request_id": "stale",
                "driver_id": "driver-1", "through": 1}).encode())
            self.assertEqual(protocol.decode(streams[0].readline()),
                             {"v": 1, "type": "request.error", "request_id": "stale", "code": "invalid-field"})
            streams[1].write(protocol.encode({"v": 1, "type": "notification.delivered",
                "request_id": "delivered", "driver_id": "driver-1", "generation": 1}).encode())
            self.assertEqual(protocol.decode(streams[1].readline()),
                             {"v": 1, "type": "ok", "request_id": "delivered"})
        finally:
            for stream in streams: stream.close()
            for client in clients: client.close()

    def _crew_register(self, task, seq=1, kind="session.register", eid=None, **extra):
        message = {"v": 1, "type": kind, "event_id": eid or f"{kind}-{task}",
                   "producer_seq": seq, "session_id": f"crew-{task}", "harness": "claude",
                   "role": "crew", "task_id": task}
        message.update(extra)
        return message

    def _offer_and_confirm(self, stream, client, generation):
        # notification.pending only creates an offer once the coalescer's delay is
        # due, so poll until the notification frame actually arrives (each poll
        # replies ok, then optionally a notification once due).
        notification = None
        for attempt in range(40):
            request_id = f"poll-{generation}-{attempt}"
            stream.write(protocol.encode({"v": 1, "type": "notification.pending",
                "request_id": request_id, "driver_id": "driver-1"}).encode())
            self.assertEqual(protocol.decode(stream.readline()),
                             {"v": 1, "type": "ok", "request_id": request_id})
            if select.select([client], [], [], 0.3)[0]:
                notification = protocol.decode(stream.readline())
                break
            time.sleep(0.05)
        self.assertIsNotNone(notification, "daemon never offered a notification")
        self.assertEqual((notification["type"], notification["generation"]),
                         ("notification", generation))
        confirm_id = f"delivered-{generation}"
        stream.write(protocol.encode({"v": 1, "type": "notification.delivered",
            "request_id": confirm_id, "driver_id": "driver-1", "generation": generation}).encode())
        self.assertEqual(protocol.decode(stream.readline()),
                         {"v": 1, "type": "ok", "request_id": confirm_id})

    def test_reconcile_pending_scope_selects_delta_or_full_snapshot(self):
        self.start()
        # Two crew registrations produce generation 1 (task-1) and 2 (task-2).
        self.assertEqual(self.exchange(self._crew_register("task-1"))["type"], "ack")
        self.assertEqual(self.exchange(self._crew_register("task-2"))["type"], "ack")

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3)
        client.connect(str(self.socket_path))
        stream = client.makefile("rwb", buffering=0)
        try:
            stream.write(protocol.encode({"v": 1, "type": "watchtower.register",
                "request_id": "register-1", "session_id": "watch-session",
                "harness": "pi", "driver_id": "driver-1"}).encode())
            self.assertEqual(protocol.decode(stream.readline()),
                             {"v": 1, "type": "ok", "request_id": "register-1"})

            self._offer_and_confirm(stream, client, 2)
            # Unacked (since 0): delta and full both span every changed task.
            first = self.exchange({"v": 1, "type": "reconcile.pending",
                "request_id": "rec-1", "driver_id": "driver-1"})
            self.assertEqual(first["through"], 2)
            self.assertEqual(sorted(r["task_id"] for r in first["reports"]), ["task-1", "task-2"])
            self.assertEqual((first["since"], first["unchanged_count"]), (0, 0))
            self.assertEqual(self.exchange({"v": 1, "type": "reconcile.ack",
                "request_id": "ack-1", "driver_id": "driver-1", "through": 2})["type"], "ok")

            # generation 3 changes only task-1.
            self.assertEqual(self.exchange(self._crew_register(
                "task-1", seq=2, kind="turn.start", eid="turn-1", turn_id="turn-1"))["type"], "ack")
            self._offer_and_confirm(stream, client, 3)

            delta = self.exchange({"v": 1, "type": "reconcile.pending",
                "request_id": "rec-2", "driver_id": "driver-1"})
            self.assertEqual(delta["through"], 3)
            self.assertEqual([r["task_id"] for r in delta["reports"]], ["task-1"])
            self.assertEqual((delta["since"], delta["unchanged_count"]), (2, 1))

            full = self.exchange({"v": 1, "type": "reconcile.pending",
                "request_id": "rec-3", "driver_id": "driver-1", "scope": "full"})
            self.assertEqual(sorted(r["task_id"] for r in full["reports"]), ["task-1", "task-2"])
            self.assertEqual(full["unchanged_count"], 0)
        finally:
            stream.close()
            client.close()

    def test_connectable_socket_is_never_unlinked_when_lock_is_available(self):
        self.home.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        listener.listen()
        try:
            process = self.start(wait=False)
            self.assertEqual(process.wait(timeout=5), 2)
            self.assertIn("refusing live or indeterminate", process.stderr.read().decode())
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.connect(str(self.socket_path))
            probe.close()
        finally:
            listener.close()


if __name__ == "__main__":
    unittest.main()
