from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/claude-hooks-2.1.240.json"


class ClaudeHookCapabilityFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.payloads = cls.fixture["payloads"]

    def test_all_required_hooks_are_represented(self) -> None:
        names = {payload["hook_event_name"] for payload in self.payloads}
        self.assertEqual(names, {
            "SessionStart", "UserPromptSubmit", "SubagentStart",
            "SubagentStop", "Stop", "SessionEnd",
        })

    def test_stop_captures_active_and_clear_background_snapshots(self) -> None:
        stops = [p for p in self.payloads if p["hook_event_name"] == "Stop"]
        snapshots = [p["background_tasks"] for p in stops]
        self.assertTrue(any(snapshot for snapshot in snapshots))
        self.assertIn([], snapshots)
        self.assertTrue(all("stop_hook_active" in p for p in stops))

    def test_subagent_stop_does_not_imply_background_clear(self) -> None:
        payload = next(
            p for p in self.payloads if p["hook_event_name"] == "SubagentStop"
        )
        self.assertIn(payload["agent_id"], {
            task["id"] for task in payload["background_tasks"]
            if task["status"] == "running"
        })

    def test_fixture_is_redacted_and_versioned(self) -> None:
        self.assertEqual(self.fixture["claude_code_version"], "2.1.240")
        text = FIXTURE.read_text()
        forbidden = ("/Users/", ".claude/projects/", "sleep 8", "SUBAGENT_OK")
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, text)

    def test_include_hook_events_has_started_response_pair(self) -> None:
        events = self.fixture["stream_hook_events"]
        self.assertEqual(
            [event["subtype"] for event in events],
            ["hook_started", "hook_response"],
        )
        self.assertEqual(events[1]["outcome"], "success")
        self.assertEqual(events[1]["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
