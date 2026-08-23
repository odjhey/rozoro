import json
import tempfile
import unittest
from pathlib import Path

from lib.rozoro_monitor.handoff import parse, parse_task_report
from lib.rozoro_monitor.store import EventStore


def event(event_id, seq, kind, **extra):
    item = {"v": 1, "type": kind, "event_id": event_id, "producer_seq": seq,
            "session_id": "session-1", "harness": "claude", "role": "crew",
            "task_id": "task-1"}
    item.update(extra)
    if kind == "turn.start":
        item.setdefault("turn_id", "turn-1")
    return item


class ProjectionReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.task = self.home / "tasks" / "task-1"
        self.task.mkdir(parents=True)
        self.db = self.home / "monitor.db"

    def tearDown(self):
        self.temp.cleanup()

    def write_handoff(self, text):
        (self.task / "handoff.md").write_text(text, encoding="utf-8")

    def register(self, store):
        store.accept_event(event("register", 1, "session.register"))

    def projection(self, store):
        row = store.task_projection("task-1")
        row["projection_json"] = json.loads(row["projection_json"])
        return row

    def test_out_of_order_facts_remain_unbound_until_registration_then_rereduce(self):
        with EventStore(self.db) as store:
            store.accept_event(event("stop", 2, "turn.stop", background_active=False))
            self.assertIsNone(store.task_projection("task-1"))
            session = store._connection.execute(
                "SELECT registered,producer_seq,availability FROM sessions"
            ).fetchone()
            self.assertEqual(tuple(session), (0, 0, "unknown"))
            store.accept_event(event("register", 1, "session.register"))
            projected = self.projection(store)
            self.assertEqual(projected["availability"], "quiescent")
            self.assertEqual(projected["actionable_reason"], "missing-report")
            self.assertEqual(projected["last_event_seq"], 2)
            self.assertEqual(projected["projection_json"]["background"], "clear")
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)

    def test_report_axis_is_independent_of_runtime_and_ack_cursor(self):
        self.write_handoff("""## turn 1 — question
verdict: needs-action
reason: choose
 did: ignored
pending: choice
inputs-needed: choose A or B
artifacts: none
""")
        # Keep the canonical did field while retaining parser compatibility.
        self.write_handoff((self.task / "handoff.md").read_text().replace(" did:", "did:"))
        with EventStore(self.db) as store:
            self.register(store)
            store.accept_event(event("start", 2, "turn.start", turn_id="turn-1"))
            before = self.projection(store)
            self.assertEqual(before["availability"], "busy")
            self.assertEqual(before["actionable_reason"], "external-action")
            self.assertEqual(before["projection_json"]["report"]["unresolved"], 1)
            (self.task / ".acked-blocks-v2").write_text("1\n")
            # ACK is filesystem/report authority and never changes SQLite by itself.
            self.assertEqual(self.projection(store), before)
            store.accept_event(event("stop", 3, "turn.stop", background_active=False))
            after = self.projection(store)
            self.assertEqual(after["availability"], "quiescent")
            self.assertEqual(after["actionable_reason"], "quiescent-turn")
            self.assertEqual(after["projection_json"]["report"]["acked_through"], 1)

    def test_structured_reasons_cover_invalid_failed_blocked_and_gone(self):
        cases = [
            ("## turn 2 — bad\nverdict: done\ndid: x\npending: none\ninputs-needed: none\nartifacts: none\n", "turn.stop", {"background_active": False}, "invalid-report"),
            ("## turn 1 — failed\nverdict: failed\nreason: broke\ndid: x\npending: none\ninputs-needed: none\nartifacts: none\n", "turn.start", {"turn_id": "t"}, "failed"),
            ("## turn 1 — blocked\nverdict: blocked\nreason: dependency\ndid: x\npending: wait\ninputs-needed: none\nartifacts: none\n", "turn.start", {"turn_id": "t"}, "blocked"),
            ("", "session.end", {}, "gone"),
        ]
        for number, (handoff, kind, fields, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                case_home = self.home / str(number)
                task = case_home / "tasks" / "task-1"
                task.mkdir(parents=True)
                (task / "handoff.md").write_text(handoff)
                with EventStore(case_home / "monitor.db") as store:
                    self.register(store)
                    store.accept_event(event(f"case-{number}", 2, kind, **fields))
                    self.assertEqual(store.task_projection("task-1")["actionable_reason"], expected)

    def test_rebuild_is_byte_equivalent_and_preserves_event_log(self):
        self.write_handoff("""## turn 1 — done
verdict: done
reason:
did: work
pending: none
inputs-needed: none
artifacts: none
""")
        with EventStore(self.db) as store:
            self.register(store)
            store.accept_event(event("start", 2, "turn.start", turn_id="turn-1"))
            store.accept_event(event("stop", 3, "turn.stop", background_active=False))
            before = store._connection.execute(
                "SELECT task_id,availability,report_state,verdict,actionable_reason,projection_generation,last_event_seq,projection_json FROM task_projections"
            ).fetchone()
            before_bytes = json.dumps(tuple(before), separators=(",", ":")).encode()
            event_bytes = store._connection.execute(
                "SELECT group_concat(payload_json,'\n') FROM events ORDER BY durable_seq"
            ).fetchone()[0].encode()
            store.rebuild_projections()
            after = store._connection.execute(
                "SELECT task_id,availability,report_state,verdict,actionable_reason,projection_generation,last_event_seq,projection_json FROM task_projections"
            ).fetchone()
            self.assertEqual(json.dumps(tuple(after), separators=(",", ":")).encode(), before_bytes)
            self.assertEqual(store._connection.execute(
                "SELECT group_concat(payload_json,'\n') FROM events ORDER BY durable_seq"
            ).fetchone()[0].encode(), event_bytes)

    def test_library_parser_matches_cli_contract_for_missing_and_malformed(self):
        missing = parse_task_report(self.task)
        self.assertEqual((missing["blocks"], missing["protocol_errors"]), (0, []))
        self.write_handoff("## turn 1 — malformed\nverdict: wat\n")
        malformed = parse(self.task / "handoff.md")
        self.assertTrue(malformed["protocol_errors"])
        self.assertEqual(malformed, parse_task_report(self.task))


if __name__ == "__main__":
    unittest.main()
