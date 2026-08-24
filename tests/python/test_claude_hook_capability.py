from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


class ClaudeHookCapabilityFixtureAssertions:
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(cls.fixture_path.read_text())
        cls.payloads = cls.fixture["payloads"]

    def test_all_required_hooks_have_exact_observed_fields(self) -> None:
        names = {payload["hook_event_name"] for payload in self.payloads}
        self.assertEqual(names, set(EXPECTED_FIELDS))
        for payload in self.payloads:
            with self.subTest(event=payload["hook_event_name"]):
                self.assertEqual(set(payload), EXPECTED_FIELDS[payload["hook_event_name"]])
        self.assertEqual(self.payloads[0]["source"], "startup")
        self.assertEqual(self.payloads[-1]["reason"], "other")
        for payload in self.payloads:
            if "permission_mode" in payload:
                self.assertEqual(payload["permission_mode"], "bypassPermissions")

    def test_three_stage_stop_snapshots_certify_active_active_clear(self) -> None:
        stops = [p for p in self.payloads if p["hook_event_name"] == "Stop"]
        snapshots = [[(t["id"], t["type"], t["status"])
                      for t in p["background_tasks"]] for p in stops]
        self.assertEqual(snapshots, [
            [("agent-redacted-1", "subagent", "running")],
            [("shell-redacted-1", "shell", "running")],
            [],
        ])
        evidence = self.fixture["outcome_evidence"]["background_sequence"]
        self.assertEqual(evidence["decision"], ["active", "active", "clear"])
        self.assertEqual(
            [[(t["id"], t["type"], t["status"]) for t in snapshot]
             for snapshot in evidence["stop_snapshots"]], snapshots)
        self.assertTrue(all(p["stop_hook_active"] is False for p in stops))

    def test_subagent_identity_and_crons_are_structurally_redacted(self) -> None:
        starts = [p for p in self.payloads
                  if p["hook_event_name"] == "SubagentStart"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["agent_id"], "agent-redacted-1")
        self.assertEqual(starts[0]["agent_type"], "general-purpose")

        stopped = next(p for p in self.payloads
                       if p["hook_event_name"] == "SubagentStop")
        self.assertEqual(stopped["agent_id"], "agent-redacted-1")
        self.assertEqual(stopped["agent_type"], "general-purpose")
        self.assertIn(stopped["agent_id"], {
            task["id"] for task in stopped["background_tasks"]
            if task["status"] == "running"
        })
        for payload in self.payloads:
            if "session_crons" in payload:
                self.assertEqual(payload["session_crons"], [])

    def test_background_task_shapes_and_prose_placeholders_are_exact(self) -> None:
        for payload in self.payloads:
            for task in payload.get("background_tasks", []):
                common = {"id", "type", "status", "description"}
                expected = common | ({"agent_type"} if task["type"] == "subagent"
                                     else {"command"})
                self.assertEqual(set(task), expected)
                self.assertEqual(task["status"], "running")
                self.assertEqual(task["description"], "<redacted>")
                if task["type"] == "subagent":
                    self.assertEqual(task["id"], "agent-redacted-1")
                    self.assertEqual(task["agent_type"], "general-purpose")
                else:
                    self.assertEqual(task["type"], "shell")
                    self.assertEqual(task["id"], "shell-redacted-1")
                    self.assertEqual(task["command"], "<redacted>")

    def test_placeholders_are_complete_and_no_identity_or_prose_leaks(self) -> None:
        self.assertEqual(set(self.fixture), {
            "fixture_version", "claude_code_version", "captured_with",
            "redactions", "payloads", "stream_hook_events", "outcome_evidence",
        })
        version = self.fixture["claude_code_version"]
        self.assertIn(version, {"2.1.240", "2.1.241"})
        self.assertIn("--no-session-persistence", self.fixture["captured_with"])
        self.assertEqual(self.fixture["outcome_evidence"]["certification"], {
            "claude_code_version": version,
            "probe": "background-agent",
            "observed_sequence": ["active", "active", "clear"],
            "capture": "live-hook-capability-probe",
        })
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
        text = self.fixture_path.read_text()
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

    def test_include_hook_events_identity_and_output_are_fully_redacted(self) -> None:
        started, response = self.fixture["stream_hook_events"]
        self.assertEqual(set(started), {
            "type", "subtype", "hook_name", "hook_event", "hook_id",
            "session_id", "uuid",
        })
        self.assertEqual(set(response), set(started) | {
            "exit_code", "outcome", "stdout", "stderr", "output",
        })
        self.assertEqual((started["subtype"], response["subtype"]),
                         ("hook_started", "hook_response"))
        for event, uuid in zip((started, response), (
                "00000000-0000-4000-8000-000000000003",
                "00000000-0000-4000-8000-000000000004"), strict=True):
            self.assertEqual(event["type"], "system")
            self.assertEqual(event["hook_name"], "Stop")
            self.assertEqual(event["hook_event"], "Stop")
            self.assertEqual(event["hook_id"], "hook-redacted-1")
            self.assertEqual(event["session_id"],
                             "00000000-0000-4000-8000-000000000001")
            self.assertEqual(event["uuid"], uuid)
        self.assertEqual((response["outcome"], response["exit_code"]),
                         ("success", 0))
        self.assertEqual(
            (response["stdout"], response["stderr"], response["output"]),
            ("", "", ""),
        )

    def test_reproduction_script_is_isolated_and_contains_all_experiments(self) -> None:
        script = PROBE.read_text()
        for required in ("--setting-sources ''", "--settings", "--debug hooks",
                         "--include-hook-events", "--no-session-persistence",
                         "timeout.settings.json",
                         "continuation.settings.json", "stop_hook_active",
                         "raise SystemExit(2)"):
            self.assertIn(required, script)
        for forbidden in ("~/.claude", "$HOME/.claude", "settings.json >"):
            self.assertNotIn(forbidden, script)


class TestClaudeHookCapabilityFixture240(ClaudeHookCapabilityFixtureAssertions,
                                         unittest.TestCase):
    fixture_path = ROOT / "tests/fixtures/claude-hooks-2.1.240.json"


class TestClaudeHookCapabilityFixture241(ClaudeHookCapabilityFixtureAssertions,
                                         unittest.TestCase):
    fixture_path = ROOT / "tests/fixtures/claude-hooks-2.1.241.json"


if __name__ == "__main__":
    unittest.main()
