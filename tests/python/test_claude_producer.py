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
FIXTURES = [
    FIXTURE,
    json.loads((ROOT / "tests/fixtures/claude-hooks-2.1.241.json").read_text()),
]
SPEC = importlib.util.spec_from_file_location("claude_rozoro_event", ROOT / "hooks/claude-rozoro-event.py")
HOOK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(HOOK)


@contextmanager
def identity(session=FIXTURE["redactions"]["session_id"]):
    values = {
        "ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "crew", "ROZORO_TASK_ID": "task-1",
        "ROZORO_SESSION_ID": session, "ROZORO_CLAUDE_BINARY": str(ROOT / "tests/fakes/claude"),
    }
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        with mock.patch.object(HOOK, "_claude_version", return_value="2.1.240"):
            yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def capability_proof(directory: Path) -> Path:
    binary = (ROOT / "tests/fakes/claude").resolve(); info = binary.stat()
    proof = directory / "capability.json"
    proof.write_text(json.dumps({"version": "2.1.240", "binary": str(binary),
                                 "identity": [info.st_dev, info.st_ino]}))
    proof.chmod(0o600)
    return proof

def capability_proof_from_fixture(directory: Path, fixture: dict[str, object]) -> Path:
    proof = directory / "capability.json"
    proof.write_text(json.dumps(fixture))
    proof.chmod(0o600)
    return proof

def run_hook(home: Path, payload: dict[str, object], proof: Path, *, timeout: float = 5.0,
            claude_env: str | None = None, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({"ROZORO_HOME": str(home), "ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "crew",
                "ROZORO_TASK_ID": "task-1", "ROZORO_SESSION_ID": payload.get("session_id", "session-1"),
                "ROZORO_CLAUDE_BINARY": claude_env or str((ROOT / "tests/fakes/claude").resolve())})
    if extra_env is not None:
        env.update(extra_env)
    return subprocess.run([str(ROOT / "hooks/claude-rozoro-event.py"), "--claude-binary", str((ROOT / "tests/fakes/claude").resolve()),
                           "--capability-proof", str(proof)], input=json.dumps(payload),
                           text=True, env=env, capture_output=True, timeout=timeout)


def collect_spool_events(home: Path) -> list[dict[str, object]]:
    return [json.loads(path.read_text()) for path in (home / "spool").glob("*.json")]


class ClaudeProducerTests(unittest.TestCase):
    def test_supported_version_window(self):
        cases = {
            "2.1.239": False, "2.1.240": True, "2.1.999": True,
            "2.2.0": False, "2.2.0-rc.1": False, "2.1.240-beta": False,
            "": False, "2.1.": False, None: False,
        }
        for version, expected in cases.items():
            self.assertEqual(HOOK._is_supported_claude_version(version), expected, version)

    def test_unsafe_hook_payload_shapes_are_noop_and_do_not_emit_events(self):
        with identity():
            self.assertEqual(HOOK.map_payload(None), [])
            self.assertEqual(HOOK.map_payload("Stop"), [])
            self.assertEqual(HOOK.map_payload([]), [])
            self.assertEqual(HOOK.map_payload({"hook_event_name": "Stop", "session_id": ["bad", "id"]}), [])

    def test_watchtower_identity_is_stable_and_never_uses_task_identity(self):
        payload = {"hook_event_name": "SessionStart", "session_id": "watch-session"}
        values = {"ROZORO_EVENT_BUS": "1", "ROZORO_ROLE": "watchtower",
                  "ROZORO_DRIVER_ID": "herdr-pane-7", "ROZORO_SESSION_ID": "watch-session",
                  "ROZORO_CLAUDE_BINARY": str(ROOT / "tests/fakes/claude")}
        with mock.patch.dict(os.environ, values, clear=True), \
             mock.patch.object(HOOK, "_claude_version", return_value="2.1.240"):
            event = HOOK.map_payload(payload)[0]
        self.assertEqual(event["role"], "watchtower")
        self.assertEqual(event["driver_id"], "herdr-pane-7")
        self.assertNotIn("task_id", event)

    def test_fixture_maps_only_frozen_lifecycle_fields(self):
        expected = ["session.register", "turn.start", "background.start",
                    "turn.stop", "turn.stop", "turn.stop", "session.end"]
        for fixture in FIXTURES:
            with self.subTest(version=fixture["claude_code_version"]):
                mapped = []
                with identity(session=fixture["redactions"]["session_id"]):
                    for payload in fixture["payloads"]:
                        events = HOOK.map_payload(payload)
                        mapped.extend(event["type"] for event in events
                                      if event["type"] != "background.snapshot")
                        encoded = json.dumps(events)
                        for secret in ("prompt", "last_assistant_message", "description",
                                       "command", "transcript"):
                            self.assertNotIn(secret, encoded)
                self.assertEqual(mapped, expected)

    def test_fixture_compatibility_range(self):
        for fixture in FIXTURES:
            with self.subTest(version=fixture["claude_code_version"]):
                with identity(session=fixture["redactions"]["session_id"]):
                    mapped = [event["type"] for payload in fixture["payloads"] for event in HOOK.map_payload(payload)]
                self.assertEqual(
                    mapped,
                    ["session.register", "turn.start", "background.start",
                     "turn.stop", "background.snapshot", "turn.stop",
                     "background.snapshot", "turn.stop", "background.snapshot",
                     "session.end"],
                )

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
            home = Path(temporary) / "home"; home.mkdir(mode=0o700)
            proof = capability_proof(home)
            result = run_hook(home, payload, proof, timeout=5, extra_env={"ROZORO_HOOK_TIMEOUT": "0.05"})
            self.assertEqual(result.returncode, 0, result.stderr)
            events = collect_spool_events(home)
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
            proof = capability_proof(home)
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
            started = time.monotonic()
            result = run_hook(home, payload, proof, timeout=2, extra_env={"ROZORO_HOOK_TIMEOUT": "9"})
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, 1.1)
            events = collect_spool_events(home)
            self.assertEqual(len(events), 2)
            self.assertEqual(sorted(event["producer_seq"] for event in events), [1, 2])

    def test_malformed_or_unsupported_capability_proof_fails_closed(self):
        payload = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][-1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"; home.mkdir(mode=0o700)
            proof = capability_proof(home)
            proof.unlink()
            capability_proof_from_fixture(home, {"version": "2.2.0", "binary": str((ROOT / "tests/fakes/claude").resolve()),
                                                 "identity": [0, 0]})
            result = run_hook(home, payload, home / "capability.json", extra_env={"ROZORO_HOOK_TIMEOUT": "0.05"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(collect_spool_events(home), [])

    def test_proof_identity_drift_fails_closed(self):
        payload = [item for item in FIXTURE["payloads"] if item["hook_event_name"] == "Stop"][-1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"; home.mkdir(mode=0o700)
            proof = capability_proof(home)
            value = json.loads(proof.read_text())
            value["identity"] = [value["identity"][0], value["identity"][1] + 1]
            capability_proof_from_fixture(home, value)
            result = run_hook(home, payload, proof, extra_env={"ROZORO_HOOK_TIMEOUT": "0.05"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(collect_spool_events(home), [])


if __name__ == "__main__":
    unittest.main()
