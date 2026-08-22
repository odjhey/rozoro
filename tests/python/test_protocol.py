from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from rozoro_monitor.protocol import ProtocolError, decode, encode, validate  # noqa: E402


class ProtocolFixturesTest(unittest.TestCase):
    def test_every_v1_fixture_round_trips(self) -> None:
        path = ROOT / "tests/fixtures/protocol-v1/messages.ndjson"
        messages = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(
            {message["type"] for message in messages},
            {"session.register", "turn.start", "background.start", "background.stop",
             "background.snapshot", "turn.stop", "session.end", "watchtower.register",
             "notification", "notification.delivered", "reconcile", "reconcile.result",
             "ack-generation", "ok", "ack", "error"},
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

    def test_rejects_unknown_fields_and_loose_types(self) -> None:
        self.assert_code("invalid-field", self.fixture(prompt="do something"))
        self.assert_code("invalid-field", self.fixture(background_active=0))
        self.assert_code("unsupported-type", {"v": 1, "type": "future.message"})

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

    def test_error_correlates_exactly_one_input(self) -> None:
        base = {"v": 1, "type": "error", "code": "invalid-event"}
        self.assert_code("invalid-message", base)
        self.assert_code("invalid-message", {**base, "event_id": "evt-1", "request_id": "req-1"})
        self.assertEqual(validate({**base, "request_id": "req-1"})["request_id"], "req-1")


if __name__ == "__main__":
    unittest.main()
