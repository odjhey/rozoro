from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from rozoro_monitor.protocol import (  # noqa: E402
    MAX_FRAME_BYTES, MAX_INTEGER, ProtocolError, decode, encode, validate,
)


class ProtocolFixturesTest(unittest.TestCase):
    def test_every_v1_fixture_round_trips(self) -> None:
        path = ROOT / "tests/fixtures/protocol-v1/messages.ndjson"
        messages = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(
            {message["type"] for message in messages},
            {"session.register", "turn.start", "background.start", "background.stop",
             "background.snapshot", "turn.stop", "session.end", "health", "monitor.stop",
             "health.result", "watchtower.register", "notification.pending",
             "notification", "notification.delivered", "reconcile", "reconcile.result",
             "ack-generation", "ok", "ack", "frame.error", "event.error", "request.error",
             "send.enqueue", "send.enqueue.result", "send.status", "send.status.result"},
        )
        for message in messages:
            with self.subTest(type=message["type"]):
                self.assertEqual(decode(encode(message)), message)


class StrictValidationTest(unittest.TestCase):
    def fixture(self, **changes: object) -> dict[str, object]:
        event: dict[str, object] = {
            "v": 1, "type": "turn.stop", "event_id": "evt-1", "producer_seq": 2,
            "session_id": "session-1", "harness": "claude", "role": "crew",
            "task_id": "task-1", "background_active": False,
        }
        event.update(changes)
        return event

    def assert_code(self, code: str, message: object) -> None:
        with self.assertRaises(ProtocolError) as caught:
            validate(message)
        self.assertEqual(caught.exception.code, code)

    def test_rejects_non_objects_and_bad_json(self) -> None:
        self.assert_code("invalid-message", [])
        with self.assertRaises(ProtocolError) as caught:
            decode("not-json\n")
        self.assertEqual(caught.exception.code, "invalid-json")

    def test_rejects_missing_and_mismatched_versions(self) -> None:
        missing = self.fixture()
        del missing["v"]
        self.assert_code("invalid-version", missing)
        self.assert_code("invalid-version", self.fixture(v=2))
        self.assert_code("invalid-version", self.fixture(v=True))

    def test_lifecycle_identity_and_order_are_mandatory(self) -> None:
        for field in ("event_id", "producer_seq", "session_id", "harness", "role", "task_id"):
            event = self.fixture()
            del event[field]
            self.assert_code("invalid-event", event)
        self.assert_code("invalid-field", self.fixture(producer_seq=0))
        self.assert_code("invalid-field", self.fixture(producer_seq=True))
        self.assert_code("invalid-field", self.fixture(event_id="../escape"))

    def test_role_selects_exactly_one_owner_identity(self) -> None:
        self.assert_code("invalid-event", self.fixture(driver_id="driver-1"))
        watchtower = self.fixture(role="watchtower", driver_id="driver-1")
        del watchtower["task_id"]
        self.assertIs(validate(watchtower), watchtower)
        self.assert_code("invalid-event", self.fixture(role="watchtower"))

    def test_turn_stop_can_explicitly_report_unknown_background(self) -> None:
        self.assertIsNone(validate(self.fixture(background_active=None))["background_active"])
        self.assertIs(validate(self.fixture(background_active=True))["background_active"], True)

    def test_rejects_unknown_fields_and_loose_types(self) -> None:
        self.assert_code("invalid-field", self.fixture(prompt="do something"))
        self.assert_code("invalid-field", self.fixture(background_active=0))
        self.assert_code("unsupported-type", {"v": 1, "type": "future.message"})

    def test_enum_arrays_and_objects_use_protocol_error_path(self) -> None:
        for value in ([], {}):
            self.assert_code("invalid-field", self.fixture(harness=value))
            self.assert_code("invalid-field", {"v": 1, "type": "notification", "generation": 1,
                                               "priority": value, "task_count": 1})

    def test_integer_fields_are_bounded_to_cross_runtime_safe_range(self) -> None:
        self.assertEqual(validate(self.fixture(producer_seq=MAX_INTEGER))["producer_seq"], MAX_INTEGER)
        self.assert_code("invalid-field", self.fixture(producer_seq=MAX_INTEGER + 1))
        notification = {"v": 1, "type": "notification", "generation": MAX_INTEGER + 1,
                        "priority": "normal", "task_count": 1}
        self.assert_code("invalid-field", notification)
        self.assert_code("invalid-field", {**notification, "generation": 1,
                                           "task_count": MAX_INTEGER + 1})

    def test_non_event_requests_require_request_correlation(self) -> None:
        request = {"v": 1, "type": "reconcile", "driver_id": "driver-1", "through": 3}
        self.assert_code("invalid-message", request)
        request["request_id"] = "req-1"
        self.assertIs(validate(request), request)

    def test_delivery_confirmation_is_not_generation_ack(self) -> None:
        delivered = {"v": 1, "type": "notification.delivered", "request_id": "req-1",
                     "driver_id": "driver-1", "generation": 9}
        reconciled = {"v": 1, "type": "ack-generation", "request_id": "req-2",
                      "driver_id": "driver-1", "through": 9}
        self.assertEqual(validate(delivered)["generation"], 9)
        self.assertEqual(validate(reconciled)["through"], 9)
        self.assert_code("invalid-field", {**delivered, "through": 9})
        self.assert_code("invalid-field", {**reconciled, "generation": 9})

    def test_wake_notification_is_content_free(self) -> None:
        notification = {"v": 1, "type": "notification", "generation": 7,
                        "priority": "urgent", "task_count": 2}
        self.assertIs(validate(notification), notification)
        for prose_field in ("message", "summary", "prompt", "reports", "task_ids"):
            self.assert_code("invalid-field", {**notification, prose_field: "crew prose"})

    def test_send_payload_carries_prompt_text_within_one_frame(self) -> None:
        enqueue = {"v": 1, "type": "send.enqueue", "request_id": "req-1",
                   "task_id": "task-1", "payload": "x", "timeout_ms": 120000}
        self.assertIs(validate(enqueue), enqueue)
        # Prompt text needs far more room than a 128-character identifier, but
        # must still fit one frame with its envelope.
        at_limit = {**enqueue, "payload": "x" * 65_536}
        self.assertIs(validate(at_limit), at_limit)
        self.assert_code("invalid-field", {**enqueue, "payload": "x" * 65_537})
        self.assert_code("invalid-field", {**enqueue, "payload": ""})
        self.assert_code("invalid-field", {**enqueue, "timeout_ms": 0})

    def test_error_kinds_have_strict_correlation(self) -> None:
        frame_error = {"v": 1, "type": "frame.error", "code": "invalid-json"}
        self.assertEqual(decode(encode(frame_error)), frame_error)
        self.assert_code("invalid-field", {**frame_error, "request_id": "req-1"})
        self.assert_code("invalid-message", {"v": 1, "type": "request.error",
                                             "code": "invalid-message"})
        self.assert_code("invalid-field", {"v": 1, "type": "event.error",
                                           "event_id": "evt-1", "code": "invalid-json"})
        request_error = {"v": 1, "type": "request.error", "request_id": "req-1",
                         "code": "invalid-field"}
        self.assertEqual(validate(request_error)["request_id"], "req-1")

    def test_reconcile_reports_are_exact_structured_snapshots(self) -> None:
        report = {"task_id": "task-1", "generation": 4, "availability": "unknown",
                  "report_state": "missing", "verdict": None,
                  "actionable_reason": "missing-report"}
        result = {"v": 1, "type": "reconcile.result", "request_id": "req-1",
                  "through": 4, "reports": [report]}
        self.assertIs(validate(result), result)
        for field in report:
            malformed = {**report}
            del malformed[field]
            self.assert_code("invalid-field", {**result, "reports": [malformed]})
        self.assert_code("invalid-field", {**result, "reports": [{**report, "summary": "prose"}]})
        self.assert_code("invalid-field", {**result, "reports": [{**report, "generation": float("inf")}]})
        self.assert_code("invalid-field", {**result, "reports": [{**report, "availability": []}]})
        self.assert_code("invalid-field", {**result, "reports": [{**report, "report_state": "valid"}]})
        valid = {**report, "report_state": "valid", "verdict": "done",
                 "actionable_reason": "quiescent"}
        valid_result = {**result, "reports": [valid]}
        self.assertIs(validate(valid_result), valid_result)
        malformed_with_verdict = {**report, "report_state": "malformed", "verdict": "failed"}
        self.assert_code("invalid-field", {**result, "reports": [malformed_with_verdict]})

    def test_reconcile_snapshot_enforces_cursor_and_unique_tasks(self) -> None:
        report = {"task_id": "task-1", "generation": 4, "availability": "unknown",
                  "report_state": "missing", "verdict": None,
                  "actionable_reason": "missing-report"}
        result = {"v": 1, "type": "reconcile.result", "request_id": "req-1",
                  "through": 4, "reports": [report]}
        self.assertIs(validate(result), result)
        self.assert_code("invalid-field", {**result, "through": 3})
        self.assert_code("invalid-field", {**result, "reports": [report, report]})
        conflicting = {**report, "availability": "blocked"}
        self.assert_code("invalid-field", {**result, "reports": [report, conflicting]})

    def test_reconcile_report_tuple_matrix_rejects_contradictions(self) -> None:
        base = {"task_id": "task-1", "generation": 1, "availability": "unknown",
                "report_state": "missing", "verdict": None,
                "actionable_reason": "missing-report"}
        result = {"v": 1, "type": "reconcile.result", "request_id": "req-1",
                  "through": 1, "reports": [base]}
        self.assertIs(validate(result), result)
        contradictions = (
            {**base, "actionable_reason": "none"},
            {**base, "verdict": "done"},
            {**base, "report_state": "valid"},
            {**base, "report_state": "malformed"},
            {**base, "report_state": "valid", "verdict": "failed",
             "actionable_reason": "quiescent"},
            {**base, "report_state": "valid", "verdict": "blocked",
             "actionable_reason": "failed"},
        )
        for report in contradictions:
            self.assert_code("invalid-field", {**result, "reports": [report]})
        valid = {**base, "report_state": "valid", "verdict": "failed",
                 "actionable_reason": "failed"}
        valid_result = {**result, "reports": [valid]}
        self.assertIs(validate(valid_result), valid_result)

    def test_reconcile_pending_scope_is_optional_bounded_enum(self) -> None:
        base = {"v": 1, "type": "reconcile.pending", "request_id": "req-1", "driver_id": "driver-1"}
        self.assertIs(validate(base), base)  # absent scope = delta default
        for scope in ("delta", "full"):
            message = {**base, "scope": scope}
            self.assertIs(validate(message), message)
        self.assert_code("invalid-field", {**base, "scope": "partial"})
        self.assert_code("invalid-field", {**base, "scope": 1})

    def test_reconcile_pending_result_delta_fields_are_optional_nonnegative(self) -> None:
        base = {"v": 1, "type": "reconcile.pending.result", "request_id": "req-1",
                "through": 5, "reports": []}
        self.assertIs(validate(base), base)  # additive fields may be absent
        annotated = {**base, "since": 2, "unchanged_count": 168}
        self.assertIs(validate(annotated), annotated)
        zeroed = {**base, "since": 0, "unchanged_count": 0}
        self.assertIs(validate(zeroed), zeroed)
        self.assert_code("invalid-field", {**base, "since": -1})
        self.assert_code("invalid-field", {**base, "unchanged_count": -1})
        self.assert_code("invalid-field", {**base, "unchanged_count": "many"})

    def test_frame_error_covers_every_uncorrelatable_failure_without_id(self) -> None:
        codes = ("invalid-json", "frame-too-large", "invalid-message", "invalid-version",
                 "invalid-event", "invalid-field", "unsupported-type")
        for code in codes:
            error = {"v": 1, "type": "frame.error", "code": code}
            self.assertEqual(decode(encode(error)), error)
        for invented in ("event_id", "request_id"):
            self.assert_code("invalid-field", {"v": 1, "type": "frame.error",
                                               "code": "invalid-field", invented: "unsafe"})

    def test_encode_decode_share_newline_inclusive_frame_limit(self) -> None:
        reports = [
            {"task_id": f"task-{index}", "generation": 1, "availability": "unknown",
             "report_state": "missing", "verdict": None,
             "actionable_reason": "missing-report"}
            for index in range(10_000)
        ]
        message = {"v": 1, "type": "reconcile.result", "request_id": "req-1",
                   "through": 1, "reports": reports}
        raw_frame = json.dumps(message, sort_keys=True, separators=(",", ":")) + "\n"
        self.assertGreater(len(raw_frame.encode("utf-8")), MAX_FRAME_BYTES)
        for operation in (lambda: encode(message), lambda: decode(raw_frame)):
            with self.assertRaises(ProtocolError) as caught:
                operation()
            self.assertEqual(caught.exception.code, "frame-too-large")

    def test_decode_rejects_oversized_frames_before_json_parsing(self) -> None:
        with self.assertRaises(ProtocolError) as caught:
            decode("x" * (MAX_FRAME_BYTES + 1))
        self.assertEqual(caught.exception.code, "frame-too-large")

    def test_decode_maps_invalid_unicode_to_protocol_error(self) -> None:
        for frame in ("\ud800", '{"v":1,"type":"frame.error","code":"invalid-json","x":"\udfff"}'):
            with self.assertRaises(ProtocolError) as caught:
                decode(frame)
            self.assertEqual(caught.exception.code, "invalid-json")

    def test_decode_rejects_duplicate_object_members_at_any_depth(self) -> None:
        frames = (
            '{"v":1,"v":1,"type":"frame.error","code":"invalid-json"}',
            '{"v":1,"type":"reconcile.result","request_id":"req-1","through":1,'
            '"reports":[{"task_id":"task-1","task_id":"task-2"}]}',
        )
        for frame in frames:
            with self.assertRaises(ProtocolError) as caught:
                decode(frame)
            self.assertEqual(caught.exception.code, "invalid-json")

    def test_decode_rejects_non_finite_json_constants(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ProtocolError) as caught:
                decode('{"v":1,"type":"notification","generation":1,"priority":"normal",'
                       f'"task_count":{constant}}}')
            self.assertEqual(caught.exception.code, "invalid-json")


if __name__ == "__main__":
    unittest.main()
