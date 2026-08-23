import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
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
    def test_fixture_maps_only_frozen_lifecycle_fields(self):
        expected = ["session.register", "turn.start", "background.start", "background.stop",
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
            decisions = [HOOK.map_payload(item)[-1]["background_active"] for item in stops]
            drifted = dict(stops[-1]); drifted.pop("background_tasks")
            unknown = HOOK.map_payload(drifted)
        self.assertEqual(decisions, [True, True, False])
        self.assertIsNone(unknown[-1]["background_active"])
        self.assertNotIn("background.snapshot", [event["type"] for event in unknown])

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


if __name__ == "__main__":
    unittest.main()
