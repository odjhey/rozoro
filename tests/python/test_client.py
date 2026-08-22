from __future__ import annotations

import json
import multiprocessing
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from rozoro_monitor import protocol
from rozoro_monitor.client import (
    ClientError, ProducerClient, UnsafePathError, allocate_producer_seq,
    prepare_event, spool_event,
)


def event(event_id="evt-1"):
    return {"v": 1, "type": "turn.start", "event_id": event_id,
            "session_id": "session-1", "harness": "claude", "role": "crew",
            "task_id": "task-1", "turn_id": "turn-1"}


class FakeServer:
    def __init__(self, path, reply=None):
        self.path = str(path)
        self.reply = reply
        self.received = None
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def __enter__(self):
        self.thread.start(); self.ready.wait(2)
        return self

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


def allocate_worker(home, count, output):
    output.put([allocate_producer_seq("shared-session", home) for _ in range(count)])


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def spooled(self):
        return list((self.home / "spool").glob("*.json"))

    def test_matching_ack_does_not_spool(self):
        path = self.home / "server.sock"
        reply = lambda got: protocol.encode({"v": 1, "type": "ack", "event_id": got["event_id"], "durable_seq": 9}).encode()
        with FakeServer(path, reply) as server:
            result = ProducerClient(self.home, socket_path=path).send(event())
        self.assertEqual(9, result["durable_seq"])
        self.assertEqual(1, server.received["producer_seq"])
        self.assertEqual([], self.spooled())

    def test_ack_loss_creates_exactly_one_spool_copy_and_retry_keeps_identity(self):
        prepared = prepare_event(event(), self.home)
        path = self.home / "server.sock"
        with FakeServer(path):
            with self.assertRaises(ClientError):
                ProducerClient(self.home, socket_path=path).send(prepared)
        first = self.spooled()
        self.assertEqual(1, len(first))
        self.assertEqual(prepared, protocol.decode(first[0].read_bytes()))

        path.unlink()
        with FakeServer(path):
            with self.assertRaises(ClientError):
                ProducerClient(self.home, socket_path=path).send(prepared)
        self.assertEqual([first[0]], self.spooled())
        self.assertEqual(prepared, protocol.decode(first[0].read_bytes()))

    def test_malformed_and_mismatched_replies_retain_evidence(self):
        replies = [b"not-json\n", protocol.encode({"v": 1, "type": "ack", "event_id": "other", "durable_seq": 1}).encode()]
        for index, reply in enumerate(replies):
            path = self.home / f"server-{index}.sock"
            with FakeServer(path, lambda _got, reply=reply: reply):
                with self.assertRaises(ClientError):
                    ProducerClient(self.home, socket_path=path).send(event(f"evt-{index}"))
        self.assertEqual({"evt-0.json", "evt-1.json"}, {p.name for p in self.spooled()})

    def test_path_traversal_ids_are_rejected_before_state_or_socket_use(self):
        for bad in ("../escape", "/tmp/escape", "a/b", ".."):
            candidate = event(bad)
            with self.assertRaises(protocol.ProtocolError):
                prepare_event(candidate, self.home)
        self.assertFalse((Path(self.temp.name) / "escape").exists())

    def test_spool_refuses_symlink_and_permissive_directories(self):
        prepared = prepare_event(event(), self.home)
        target = Path(self.temp.name) / "target"; target.mkdir(mode=0o700)
        (self.home / "spool").symlink_to(target, target_is_directory=True)
        with self.assertRaises(UnsafePathError):
            spool_event(prepared, self.home)
        (self.home / "spool").unlink()
        (self.home / "spool").mkdir(mode=0o755)
        with self.assertRaises(UnsafePathError):
            spool_event(prepared, self.home)

    def test_concurrent_processes_allocate_unique_contiguous_sequences(self):
        context = multiprocessing.get_context("spawn")
        output = context.Queue()
        processes = [context.Process(target=allocate_worker, args=(str(self.home), 20, output)) for _ in range(5)]
        for process in processes: process.start()
        values = []
        for _ in processes: values.extend(output.get(timeout=10))
        for process in processes:
            process.join(10); self.assertEqual(0, process.exitcode)
        self.assertEqual(list(range(1, 101)), sorted(values))

    def test_existing_spool_collision_never_replaces_identity(self):
        first = prepare_event(event("same-id"), self.home)
        spool_event(first, self.home)
        second = dict(first, turn_id="different")
        with self.assertRaises(ClientError):
            spool_event(second, self.home)
        saved = protocol.decode((self.home / "spool/same-id.json").read_bytes())
        self.assertEqual(first, saved)


if __name__ == "__main__":
    unittest.main()
