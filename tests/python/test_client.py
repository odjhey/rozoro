from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import tempfile
import threading
import traceback
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from unittest import mock

from rozoro_monitor import client, protocol
from rozoro_monitor.client import ClientError, ProducerClient, UnsafePathError, prepare_event, spool_event


def event(event_id="evt-1", turn_id="turn-1", session_id="session-1"):
    return {"v": 1, "type": "turn.start", "event_id": event_id,
            "session_id": session_id, "harness": "claude", "role": "crew",
            "task_id": "task-1", "turn_id": turn_id}


class FakeServer:
    def __init__(self, path, reply=None):
        self.path = str(path); self.reply = reply; self.received = None
        self.ready = threading.Event(); self.thread = threading.Thread(target=self.run, daemon=True)

    def __enter__(self):
        self.thread.start(); self.ready.wait(2); return self

    def __exit__(self, *_):
        self.thread.join(2)

    def run(self):
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(self.path); server.listen(1); self.ready.set()
            conn, _ = server.accept()
            with conn:
                data = b""
                while not data.endswith(b"\n"):
                    data += conn.recv(4096)
                self.received = protocol.decode(data)
                if self.reply is not None:
                    conn.sendall(self.reply(self.received))


def reserve_worker(home, start, count, output):
    try:
        values = [prepare_event(event(f"event-{start + i}", session_id="shared-session"), home)["producer_seq"] for i in range(count)]
        output.put(("ok", values))
    except Exception:
        output.put(("error", traceback.format_exc()))


def collision_worker(home, turn_id, ready, go, output):
    ready.put(True); go.wait()
    try:
        reserved = prepare_event(event("same-id", turn_id=turn_id), home)
        output.put(("ok", reserved["turn_id"]))
    except Exception as exc:
        output.put(("error", type(exc).__name__))


def crash_before_send_worker(home):
    prepare_event(event("crash"), home)
    os._exit(23)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"; self.home.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def spooled(self):
        spool = self.home / "spool"
        return [] if not spool.exists() else list(spool.glob("*.json"))

    def test_matching_ack_removes_durable_reservation(self):
        path = self.home / "server.sock"
        reply = lambda got: protocol.encode({"v": 1, "type": "ack", "event_id": got["event_id"], "durable_seq": 9}).encode()
        with FakeServer(path, reply) as server:
            result = ProducerClient(self.home, socket_path=path).send(event())
        self.assertEqual(9, result["durable_seq"])
        self.assertEqual(1, server.received["producer_seq"])
        self.assertEqual([], self.spooled())

    def test_ack_loss_keeps_one_copy_and_raw_retry_reuses_envelope(self):
        path = self.home / "server.sock"
        with FakeServer(path):
            with self.assertRaises(ClientError):
                ProducerClient(self.home, socket_path=path).send(event())
        first = protocol.decode(self.spooled()[0].read_bytes())
        path.unlink()
        with FakeServer(path) as server:
            with self.assertRaises(ClientError):
                ProducerClient(self.home, socket_path=path).send(event())
        self.assertEqual(first, server.received)
        self.assertEqual(first, protocol.decode(self.spooled()[0].read_bytes()))
        self.assertEqual(1, len(self.spooled()))

    def test_malformed_event_and_response_direction_consume_no_sequence(self):
        malformed = event("bad"); malformed["turn_id"] = []
        with self.assertRaises(protocol.ProtocolError):
            prepare_event(malformed, self.home)
        with self.assertRaises(protocol.ProtocolError):
            prepare_event({"v": 1, "type": "ack", "event_id": "ack-1", "durable_seq": 1}, self.home)
        reserved = prepare_event(event("good"), self.home)
        self.assertEqual(1, reserved["producer_seq"])

    def test_crash_before_send_and_before_counter_update_are_recoverable(self):
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=crash_before_send_worker, args=(str(self.home),))
        process.start(); process.join(10)
        self.assertEqual(23, process.exitcode)
        first = protocol.decode((self.home / "spool/crash.json").read_bytes())
        # Also simulate death after atomic spool publication but before cursor fsync.
        (self.home / "producer-seq/session-1.seq").write_text("0")
        second = prepare_event(event("next"), self.home)
        self.assertEqual((1, 2), (first["producer_seq"], second["producer_seq"]))
        self.assertEqual({"crash.json", "next.json"}, {path.name for path in self.spooled()})

    def test_spool_pathname_swap_cannot_redirect_dirfd_relative_publication(self):
        moved = self.home / "spool-held"
        outside = Path(self.temp.name) / "outside"; outside.mkdir(mode=0o700)
        original_write = client._write_temp
        swapped = False

        def swap_then_write(directory_fd, data):
            nonlocal swapped
            if not swapped:
                (self.home / "spool").rename(moved)
                (self.home / "spool").symlink_to(outside, target_is_directory=True)
                swapped = True
            return original_write(directory_fd, data)

        with mock.patch.object(client, "_write_temp", side_effect=swap_then_write):
            reserved = prepare_event(event("race"), self.home)
        self.assertEqual(reserved, protocol.decode((moved / "race.json").read_bytes()))
        self.assertEqual([], list(outside.iterdir()))

    def test_malformed_and_mismatched_replies_retain_evidence(self):
        replies = [b"not-json\n", protocol.encode({"v": 1, "type": "ack", "event_id": "other", "durable_seq": 1}).encode()]
        for index, reply in enumerate(replies):
            path = self.home / f"server-{index}.sock"
            with FakeServer(path, lambda _got, reply=reply: reply):
                with self.assertRaises(ClientError):
                    ProducerClient(self.home, socket_path=path).send(event(f"evt-{index}"))
        self.assertEqual({"evt-0.json", "evt-1.json"}, {p.name for p in self.spooled()})

    def test_path_traversal_rejected_before_sequence_state(self):
        for bad in ("../escape", "/tmp/escape", "a/b", ".."):
            with self.assertRaises(protocol.ProtocolError):
                prepare_event(event(bad), self.home)
        reserved = prepare_event(event("valid"), self.home)
        self.assertEqual(1, reserved["producer_seq"])

    def test_spool_refuses_symlink_and_permissive_directories(self):
        target = Path(self.temp.name) / "target"; target.mkdir(mode=0o700)
        (self.home / "spool").symlink_to(target, target_is_directory=True)
        with self.assertRaises((UnsafePathError, OSError)):
            prepare_event(event(), self.home)
        (self.home / "spool").unlink(); (self.home / "spool").mkdir(mode=0o755)
        with self.assertRaises(UnsafePathError):
            prepare_event(event(), self.home)

    def test_concurrent_processes_reserve_unique_contiguous_sequences(self):
        context = multiprocessing.get_context("spawn"); output = context.Queue()
        processes = [context.Process(target=reserve_worker, args=(str(self.home), n * 20, 20, output)) for n in range(5)]
        for process in processes: process.start()
        results = [output.get(timeout=15) for _ in processes]
        for process in processes: process.join(15); self.assertEqual(0, process.exitcode)
        self.assertTrue(all(status == "ok" for status, _ in results), results)
        values = [value for _, group in results for value in group]
        self.assertEqual(list(range(1, 101)), sorted(values))
        self.assertEqual(100, len(self.spooled()))

    def test_concurrent_differing_payloads_never_clobber_same_event_id(self):
        context = multiprocessing.get_context("spawn")
        ready, output, go = context.Queue(), context.Queue(), context.Event()
        processes = [context.Process(target=collision_worker, args=(str(self.home), turn, ready, go, output))
                     for turn in ("turn-a", "turn-b")]
        for process in processes: process.start()
        for _ in processes: ready.get(timeout=10)
        go.set(); results = [output.get(timeout=10) for _ in processes]
        for process in processes: process.join(10); self.assertEqual(0, process.exitcode)
        self.assertEqual(["error", "ok"], sorted(status for status, _ in results))
        winner = next(value for status, value in results if status == "ok")
        saved = protocol.decode((self.home / "spool/same-id.json").read_bytes())
        self.assertEqual(winner, saved["turn_id"])

    def test_existing_collision_and_symlink_destination_are_not_replaced(self):
        first = prepare_event(event("same-id"), self.home)
        with self.assertRaises(ClientError):
            spool_event(dict(first, turn_id="different"), self.home)
        self.assertEqual(first, protocol.decode((self.home / "spool/same-id.json").read_bytes()))
        (self.home / "spool/link-id.json").symlink_to(Path(self.temp.name) / "outside")
        linked = dict(first, event_id="link-id", producer_seq=2)
        with self.assertRaises(OSError):
            spool_event(linked, self.home)
        self.assertFalse((Path(self.temp.name) / "outside").exists())

    def test_created_state_directories_and_files_are_private(self):
        prepare_event(event(), self.home)
        for path in (self.home / "spool", self.home / "producer-seq"):
            self.assertEqual(0o700, path.stat().st_mode & 0o777)
        for path in (self.home / "spool").iterdir():
            self.assertEqual(0o600, path.stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
