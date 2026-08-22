from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/claude-hooks-2.1.240.json"
PROBE = ROOT / "tests/live/claude-hook-capability-probe.sh"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

COMMON = {"session_id", "transcript_path", "cwd", "hook_event_name"}
EXPECTED_FIELDS = {
    "SessionStart": COMMON | {"source"},
    "UserPromptSubmit": COMMON | {"permission_mode", "prompt", "prompt_id"},
    "SubagentStart": COMMON | {"agent_id", "agent_type", "prompt_id"},
    "SubagentStop": COMMON | {"permission_mode", "stop_hook_active", "agent_id",
        "agent_type", "agent_transcript_path", "last_assistant_message",
        "background_tasks", "session_crons", "prompt_id"},
    "Stop": COMMON | {"permission_mode", "stop_hook_active",
        "last_assistant_message", "background_tasks", "session_crons", "prompt_id"},
    "SessionEnd": COMMON | {"reason", "prompt_id"},
}


class ClaudeHookCapabilityFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.payloads = cls.fixture["payloads"]

    def test_all_required_hooks_have_exact_observed_fields(self) -> None:
        names = {payload["hook_event_name"] for payload in self.payloads}
        self.assertEqual(names, set(EXPECTED_FIELDS))
        for payload in self.payloads:
            with self.subTest(event=payload["hook_event_name"]):
                self.assertEqual(set(payload), EXPECTED_FIELDS[payload["hook_event_name"]])

    def test_three_stage_stop_snapshots_certify_active_active_clear(self) -> None:
        stops = [p for p in self.payloads if p["hook_event_name"] == "Stop"]
        snapshots = [[(t["id"], t["type"], t["status"])
                      for t in p["background_tasks"]] for p in stops]
        self.assertEqual(snapshots, [
            [("agent-redacted-1", "subagent", "running"),
             ("shell-redacted-1", "shell", "running")],
            [("shell-redacted-1", "shell", "running")],
            [],
        ])
        evidence = self.fixture["outcome_evidence"]["background_sequence"]
        self.assertEqual(evidence["decision"], ["active", "active", "clear"])
        self.assertEqual(
            [[(t["id"], t["type"], t["status"]) for t in snapshot]
             for snapshot in evidence["stop_snapshots"]], snapshots)
        self.assertTrue(all(p["stop_hook_active"] is False for p in stops))

    def test_subagent_stop_does_not_imply_background_clear(self) -> None:
        payload = next(p for p in self.payloads
                       if p["hook_event_name"] == "SubagentStop")
        self.assertIn(payload["agent_id"], {
            task["id"] for task in payload["background_tasks"]
            if task["status"] == "running"
        })

    def test_placeholders_are_complete_and_no_identity_or_prose_leaks(self) -> None:
        self.assertEqual(set(self.fixture), {
            "fixture_version", "claude_code_version", "captured_with",
            "redactions", "payloads", "stream_hook_events", "outcome_evidence",
        })
        self.assertEqual(self.fixture["claude_code_version"], "2.1.240")
        redactions = self.fixture["redactions"]
        self.assertEqual(redactions, {
            "session_id": "00000000-0000-4000-8000-000000000001",
            "prompt_id": "00000000-0000-4000-8000-000000000002",
            "cwd": "/redacted/worktree",
            "transcript_path": "/redacted/transcript.jsonl",
        })
        for payload in self.payloads:
            self.assertEqual(payload["session_id"], redactions["session_id"])
            self.assertEqual(payload["cwd"], redactions["cwd"])
            self.assertEqual(payload["transcript_path"], redactions["transcript_path"])
            if "prompt_id" in payload:
                self.assertEqual(payload["prompt_id"], redactions["prompt_id"])
            for key in ("prompt", "last_assistant_message"):
                if key in payload:
                    self.assertEqual(payload[key], "<redacted>")
            if "agent_transcript_path" in payload:
                self.assertEqual(payload["agent_transcript_path"], "/redacted/subagent.jsonl")
            for task in payload.get("background_tasks", []):
                self.assertIn(task["id"], {"agent-redacted-1", "shell-redacted-1"})
                self.assertEqual(task["description"], "<redacted>")
                if "command" in task:
                    self.assertEqual(task["command"], "<redacted>")
        text = FIXTURE.read_text()
        allowed_uuids = {
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
            "00000000-0000-4000-8000-000000000003",
            "00000000-0000-4000-8000-000000000004",
        }
        self.assertEqual(set(UUID.findall(text)), allowed_uuids)

        def inspect(value: object, key: str = "") -> None:
            self.assertNotRegex(key.lower(), r"(^|_)(api_?key|token|secret|password)($|_)")
            if isinstance(value, dict):
                for child_key, child in value.items():
                    inspect(child, child_key)
            elif isinstance(value, list):
                for child in value:
                    inspect(child, key)
            elif isinstance(value, str) and value.startswith("/"):
                self.assertTrue(value.startswith("/redacted/"), value)
        inspect(self.fixture)
        for forbidden in ("/Users/", "/home/", ".claude/projects/", "sleep 8",
                          "SUBAGENT_OK", "MAIN_OK", "BG_DONE", "INITIAL_STOP",
                          "TIMEOUT_OK", "STOP_CONTINUATION_CONFIRMED", "sk-ant-",
                          "Bearer ", "ghp_"):
            self.assertNotIn(forbidden, text)

    def test_timeout_claim_has_matching_cancelled_evidence(self) -> None:
        evidence = self.fixture["outcome_evidence"]["timeout"]
        self.assertEqual(evidence["hook_event"], "UserPromptSubmit")
        self.assertEqual(evidence["configured_timeout_seconds"], 1)
        self.assertGreater(evidence["hook_sleep_seconds"], 1)
        self.assertEqual(evidence["hook_response"], {
            "exit_code": 1, "outcome": "cancelled", "stderr": ""})
        self.assertIs(evidence["model_turn_proceeded"], True)
        self.assertEqual(evidence["model_result"], "<redacted>")

    def test_continuation_claim_has_guarded_two_stop_evidence(self) -> None:
        evidence = self.fixture["outcome_evidence"]["stop_continuation"]
        self.assertEqual(evidence["first_stop"], {
            "stop_hook_active": False, "exit_code": 2, "outcome": "error",
            "stderr": "<redacted-continuation-instruction>"})
        self.assertEqual(evidence["second_stop"], {
            "stop_hook_active": True, "exit_code": 0, "outcome": "success",
            "stderr": ""})
        self.assertEqual(evidence["result"], "<redacted-continuation-result>")
        self.assertEqual(evidence["num_turns"], 2)

    def test_include_hook_events_has_started_response_pair(self) -> None:
        events = self.fixture["stream_hook_events"]
        self.assertEqual([e["subtype"] for e in events],
                         ["hook_started", "hook_response"])
        self.assertEqual((events[1]["outcome"], events[1]["exit_code"]),
                         ("success", 0))

    def test_reproduction_script_is_isolated_and_contains_all_experiments(self) -> None:
        script = PROBE.read_text()
        for required in ("--setting-sources ''", "--settings", "--debug hooks",
                         "--include-hook-events", "timeout.settings.json",
                         "continuation.settings.json", "stop_hook_active",
                         "raise SystemExit(2)"):
            self.assertIn(required, script)
        for forbidden in ("~/.claude", "$HOME/.claude", "settings.json >"):
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
