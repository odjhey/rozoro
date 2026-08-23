import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))
FIXTURE = json.loads((ROOT / "tests/fixtures/claude-hooks-2.1.240.json").read_text())
SPEC = importlib.util.spec_from_file_location("claude_rozoro_event", ROOT / "hooks/claude-rozoro-event.py")
HOOK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(HOOK)


@contextmanager
def identity(session=FIXTURE["redactions"]["session_id"]):
    values = {
        "ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "crew", "ROZORO_TASK_ID": "task-1",
        "ROZORO_SESSION_ID": session, "ROZORO_CLAUDE_CAPABILITY": "2.1.240",
    }
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ClaudeProducerTests(unittest.TestCase):
    def test_watchtower_identity_is_stable_and_never_uses_task_identity(self):
        payload = {"hook_event_name": "SessionStart", "session_id": "watch-session"}
        values = {"ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "watchtower",
                  "ROZORO_DRIVER_ID": "herdr-pane-7", "ROZORO_SESSION_ID": "watch-session",
                  "ROZORO_CLAUDE_CAPABILITY": "2.1.240"}
        with mock.patch.dict(os.environ, values, clear=True):
            event = HOOK.map_payload(payload)[0]
        self.assertEqual(event["role"], "watchtower")
        self.assertEqual(event["driver_id"], "herdr-pane-7")
        self.assertNotIn("task_id", event)

    def test_watchtower_actuator_registers_polls_and_confirms_over_one_connection(self):
        # A fake daemon reproducing the real per-connection binding: the pending
        # poll and delivery are rejected unless watchtower.register arrived
        # earlier on the SAME connection (server.py binds registered_driver to
        # the socket). If the hook opened a fresh socket per request, the poll
        # would be refused and nothing would ever be delivered.
        transcript = []
        delivered = []
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.mkdir(mode=0o700)
            sock = home / "monitor.sock"
            ready = threading.Event()
            holder = {}

            def handle(connection, index):
                registered = None
                with connection:
                    stream = connection.makefile("rwb", buffering=0)
                    for line in stream:
                        try:
                            message = json.loads(line)
                        except ValueError:
                            return
                        transcript.append((index, message))
                        request_id = message.get("request_id")
                        kind = message.get("type")
                        if kind == "watchtower.register":
                            registered = message["driver_id"]
                            stream.write(json.dumps(
                                {"v": 1, "type": "ok", "request_id": request_id}).encode() + b"\n")
                        elif kind in {"notification.pending", "notification.delivered"}:
                            if registered != message.get("driver_id"):
                                stream.write(json.dumps({"v": 1, "type": "request.error",
                                    "request_id": request_id, "code": "invalid-field"}).encode() + b"\n")
                                continue
                            stream.write(json.dumps(
                                {"v": 1, "type": "ok", "request_id": request_id}).encode() + b"\n")
                            if kind == "notification.pending":
                                stream.write(json.dumps({"v": 1, "type": "notification",
                                    "generation": 9, "priority": "normal", "task_count": 0}).encode() + b"\n")
                            else:
                                delivered.append(message["generation"])

            def serve():
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                holder["server"] = server
                server.bind(str(sock)); server.listen(4); ready.set()
                index = 0
                while True:
                    try:
                        connection, _ = server.accept()
                    except OSError:
                        return
                    index += 1
                    threading.Thread(target=handle, args=(connection, index), daemon=True).start()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start(); ready.wait(1)
            completed = subprocess.CompletedProcess([], 0)
            base = {"session_id": "watch-session", "driver_id": "herdr-pane-7"}
            try:
                with mock.patch.dict(os.environ, {"ROZORO_HOME": str(home),
                                                  "ROZORO_HERDR_PANE_ID": "pane-7"}, clear=True), \
                     mock.patch.object(HOOK.subprocess, "run", return_value=completed) as run:
                    HOOK._watchtower_actuate(base, {"hook_event_name": "Stop", "stop_hook_active": False,
                                                   "background_tasks": [{"id": "job"}]}, .5)
                    self.assertFalse(run.called)
                    self.assertEqual(delivered, [])
                    HOOK._watchtower_actuate(base, {"hook_event_name": "Stop", "stop_hook_active": False,
                                                   "background_tasks": []}, .5)
                    run.assert_called_once_with(
                        ["herdr", "agent", "prompt", "pane-7",
                         "Rozoro notification pending; run ./bin/rozoro reconcile."],
                        timeout=mock.ANY, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, check=False)
            finally:
                server = holder.get("server")
                if server is not None:
                    server.close()
        polls = [index for index, message in transcript if message["type"] == "notification.pending"]
        confirms = [(index, message) for index, message in transcript
                    if message["type"] == "notification.delivered"]
        registers = [index for index, message in transcript if message["type"] == "watchtower.register"]
        self.assertEqual(delivered, [9])
        self.assertEqual(len(polls), 1)
        self.assertEqual(len(confirms), 1)
        self.assertEqual(confirms[0][0], polls[0])
        self.assertIn(polls[0], registers)
        self.assertEqual(confirms[0][1]["generation"], 9)

    def test_quiescent_poll_without_notification_does_not_block_for_the_budget(self):
        # An empty Stop with nothing pending gets only the ok reply, no
        # notification frame. The actuator must bound the wait rather than
        # block for the whole hook budget on every clean Stop.
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.mkdir(mode=0o700)
            sock = home / "monitor.sock"
            ready = threading.Event()
            holder = {}

            def handle(connection):
                registered = None
                with connection:
                    stream = connection.makefile("rwb", buffering=0)
                    for line in stream:
                        message = json.loads(line)
                        request_id = message.get("request_id")
                        if message.get("type") == "watchtower.register":
                            registered = message["driver_id"]
                        stream.write(json.dumps(
                            {"v": 1, "type": "ok", "request_id": request_id}).encode() + b"\n")
                        assert registered is not None

            def serve():
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                holder["server"] = server
                server.bind(str(sock)); server.listen(4); ready.set()
                while True:
                    try:
                        connection, _ = server.accept()
                    except OSError:
                        return
                    threading.Thread(target=handle, args=(connection,), daemon=True).start()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start(); ready.wait(1)
            base = {"session_id": "watch-session", "driver_id": "herdr-pane-7"}
            try:
                with mock.patch.dict(os.environ, {"ROZORO_HOME": str(home),
                                                  "ROZORO_HERDR_PANE_ID": "pane-7"}, clear=True), \
                     mock.patch.object(HOOK.subprocess, "run") as run:
                    started = time.monotonic()
                    HOOK._watchtower_actuate(base, {"hook_event_name": "Stop", "stop_hook_active": False,
                                                   "background_tasks": []}, 2.0)
                    elapsed = time.monotonic() - started
            finally:
                server = holder.get("server")
                if server is not None:
                    server.close()
            self.assertFalse(run.called)
            self.assertLess(elapsed, 1.0)

    def test_fixture_maps_only_frozen_lifecycle_fields(self):
        expected = ["session.register", "turn.start", "background.start",
                    "turn.stop", "turn.stop", "turn.stop", "session.end"]
        mapped = []
        with identity():
            for payload in FIXTURE["payloads"]:
                events = HOOK.map_payload(payload)
                mapped.extend(event["type"] for event in events if event["type"] != "background.snapshot")
                encoded = json.dumps(events)
                for secret in ("prompt", "last_assistant_message", "description", "command", "transcript"):
                    self.assertNotIn(secret, encoded)
        self.assertEqual(mapped, expected)

    def test_stop_snapshots_certify_active_active_clear_and_missing_is_unknown(self):
        stops = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"]
        with identity():
            decisions = [next(event["background_active"] for event in HOOK.map_payload(item)
                              if event["type"] == "turn.stop") for item in stops]
            drifted = dict(stops[-1]); drifted.pop("background_tasks")
            unknown = HOOK.map_payload(drifted)
        self.assertEqual(decisions, [True, True, False])
        self.assertIsNone(unknown[-1]["background_active"])
        self.assertNotIn("background.snapshot", [event["type"] for event in unknown])

    def test_authoritative_active_snapshot_remains_exact_and_certified(self):
        from rozoro_monitor.reducer import LifecycleState, reduce_event
        active = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][0]
        with identity():
            events = HOOK.map_payload(active)
        self.assertEqual([event["type"] for event in events], ["turn.stop", "background.snapshot"])
        state = LifecycleState()
        for seq, event in enumerate(events, 1):
            state = reduce_event(state, dict(event, producer_seq=seq)).state
        self.assertTrue(state.background_certified)
        self.assertEqual(state.active_count, 1)
        self.assertEqual(state.availability, "waiting-background")

    def test_subagent_stop_cannot_clear_authoritative_active_until_empty_stop(self):
        from rozoro_monitor.reducer import LifecycleState, reduce_event
        active, empty = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][::2]
        subagent_stop = next(item for item in FIXTURE["payloads"] if item["hook_event_name"] == "SubagentStop")
        with identity():
            batches = [HOOK.map_payload(active), HOOK.map_payload(subagent_stop), HOOK.map_payload(empty)]
        self.assertEqual(batches[1], [])
        state = LifecycleState(); seq = 0
        for event in batches[0]:
            seq += 1; state = reduce_event(state, dict(event, producer_seq=seq)).state
        self.assertEqual(state.background, "active")
        self.assertTrue(state.background_certified)
        self.assertEqual(state.active_count, 1)
        # The uncertifying incremental stop emits no claim; positive evidence
        # remains and global clear/quiescence is impossible.
        self.assertNotEqual(state.background, "clear")
        self.assertNotEqual(state.availability, "quiescent")
        for event in batches[2]:
            seq += 1; state = reduce_event(state, dict(event, producer_seq=seq)).state
        self.assertEqual(state.background, "clear")
        self.assertTrue(state.background_certified)
        self.assertEqual(state.availability, "quiescent")

    def test_unrelated_or_wrong_session_is_noop(self):
        payload = FIXTURE["payloads"][0]
        self.assertEqual(HOOK.map_payload(payload), [])
        with identity("different-session"):
            self.assertEqual(HOOK.map_payload(payload), [])

    def test_shuffled_replay_reaches_expected_projection(self):
        from rozoro_monitor.reducer import LifecycleState, reduce_event
        stop = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][-1]
        with identity():
            payloads = [FIXTURE["payloads"][0], FIXTURE["payloads"][1], FIXTURE["payloads"][2], stop]
            events = [event for payload in payloads for event in HOOK.map_payload(payload)]
        events = [dict(event, producer_seq=index + 1) for index, event in enumerate(events)]
        state = LifecycleState()
        for event in reversed(events):
            state = reduce_event(state, event).state
        self.assertEqual(state.availability, "quiescent")
        self.assertEqual(state.background, "clear")

    def test_daemon_down_retains_exact_redacted_events_in_spool(self):
        payload = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][-1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            env = os.environ.copy()
            env.update({"ROZORO_HOME": str(home), "ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "crew",
                        "ROZORO_TASK_ID": "task-1", "ROZORO_SESSION_ID": payload["session_id"],
                        "ROZORO_CLAUDE_CAPABILITY": "2.1.240", "ROZORO_HOOK_TIMEOUT": "0.05"})
            result = subprocess.run([str(ROOT / "hooks/claude-rozoro-event.py")], input=json.dumps(payload),
                                    text=True, env=env, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(path.read_text()) for path in (home / "spool").glob("*.json")]
            self.assertEqual({event["type"] for event in events}, {"background.snapshot", "turn.stop"})
            self.assertEqual(sorted(event["producer_seq"] for event in events), [1, 2])
            encoded = json.dumps(events)
            self.assertNotIn("<redacted>", encoded)
            self.assertNotIn("last_assistant_message", encoded)

    def test_stop_uses_one_hook_wide_delivery_budget(self):
        payload = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][-1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.mkdir(mode=0o700)
            sock = home / "monitor.sock"
            ready = threading.Event()

            def delayed_ack():
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                    server.bind(str(sock)); server.listen(1); ready.set()
                    connection, _ = server.accept()
                    with connection:
                        connection.recv(65536)
                        time.sleep(2)

            thread = threading.Thread(target=delayed_ack, daemon=True); thread.start(); ready.wait(1)
            env = os.environ.copy()
            env.update({"ROZORO_HOME": str(home), "ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "crew",
                        "ROZORO_TASK_ID": "task-1", "ROZORO_SESSION_ID": payload["session_id"],
                        "ROZORO_CLAUDE_CAPABILITY": "2.1.240", "ROZORO_HOOK_TIMEOUT": "9"})
            started = time.monotonic()
            result = subprocess.run([str(ROOT / "hooks/claude-rozoro-event.py")], input=json.dumps(payload),
                                    text=True, env=env, capture_output=True, timeout=2)
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, 1.1)
            events = [json.loads(path.read_text()) for path in (home / "spool").glob("*.json")]
            self.assertEqual(len(events), 2)
            self.assertEqual(sorted(event["producer_seq"] for event in events), [1, 2])


if __name__ == "__main__":
    unittest.main()
