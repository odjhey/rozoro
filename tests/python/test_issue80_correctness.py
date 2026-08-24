import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.rozoro_monitor import store as store_module
from lib.rozoro_monitor.store import EventStore


def lifecycle(kind, seq, *, session="pi-session", task="task-1"):
    value = {"v": 1, "type": kind, "event_id": f"{session}-{seq}", "producer_seq": seq,
             "session_id": session, "harness": "pi", "role": "crew", "task_id": task}
    if kind == "turn.start": value["turn_id"] = f"turn-{seq}"
    if kind == "turn.stop": value.update(turn_id=f"turn-{seq-1}", background_active=False)
    return value


class Issue80CorrectnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home = Path(self.temp.name)
        os.chmod(self.home, 0o700); (self.home / "tasks/task-1").mkdir(parents=True)
        self.db = self.home / "monitor.db"
    def tearDown(self): self.temp.cleanup()

    def test_progress_and_diagnostics_are_noops_until_certified_settlement(self):
        with EventStore(self.db) as store:
            self.assertIsNone(store.accept_event(lifecycle("session.register", 1)).generation)
            store.reconcile_herdr_liveness("task-1", pane_exists=True)
            self.assertIsNone(store.accept_event(lifecycle("turn.start", 2)).generation)
            self.assertEqual(store.health_snapshot()["generation"], 0)
            settled = store.accept_event(lifecycle("turn.stop", 3))
            self.assertEqual(settled.generation, 1)
            state = store._connection.execute("SELECT reducer_state_json FROM sessions").fetchone()[0]
            self.assertIn('"producer_seq":3', state); self.assertIn('"pending_events":[]', state)
            self.assertIn('"sequence_gap":false', state)
            store.accept_event(lifecycle("turn.start", 4))
            self.assertIsNone(store.accept_event(lifecycle("turn.stop", 5)).generation)
            self.assertEqual(store.health_snapshot()["generation"], 1)

    def test_retirement_is_silent_and_future_snapshot_contains_only_active_members(self):
        (self.home / "tasks/task-2").mkdir()
        with EventStore(self.db) as store:
            for task, session in (("task-1", "one"), ("task-2", "two")):
                store.accept_event(lifecycle("session.register", 1, session=session, task=task))
                store.accept_event(lifecycle("turn.start", 2, session=session, task=task))
            store.retire_task_membership("task-1")
            self.assertEqual(store.health_snapshot()["generation"], 0)
            result = store.accept_event(lifecycle("turn.stop", 3, session="two", task="task-2"))
            self.assertEqual(result.generation, 1)
            registration = store.register_driver("driver", "watch", "pi")
            reports = store.reconcile("driver", "watch", registration["epoch"], 1)
            self.assertEqual([item["task_id"] for item in reports], ["task-2"])
            self.assertEqual(store.task_projection("task-1")["availability"], "gone")

    def test_equal_cursors_have_unambiguous_settled_health(self):
        with EventStore(self.db) as store:
            store.register_driver("driver", "watch", "pi")
            driver = store.health_snapshot()["drivers"][0]
            self.assertEqual((driver["pending"], driver["delivered_unacked"], driver["delivery_state"]),
                             (False, False, "settled"))

    def test_later_valid_correction_recovers_current_state_but_keeps_diagnostics(self):
        handoff = self.home / "tasks/task-1/handoff.md"
        handoff.write_text("## turn 1 — bad\nverdict: needs-action\npending: x\ninputs-needed: operator\nartifacts: none\n"
                           "## turn 2 — corrected\nverdict: done\ndid: fixed\npending: none\ninputs-needed: none\nartifacts: none\n")
        before = handoff.read_bytes()
        with EventStore(self.db) as store:
            store.accept_event(lifecycle("session.register", 1)); store.accept_event(lifecycle("turn.start", 2))
            store.accept_event(lifecycle("turn.stop", 3))
            row = store.task_projection("task-1"); projection = __import__("json").loads(row["projection_json"])
            self.assertEqual((row["report_state"], row["verdict"]), ("valid", "done"))
            self.assertTrue(projection["report"]["protocol_errors"])
            self.assertEqual(projection["report"]["open_items"], [])
        self.assertEqual(handoff.read_bytes(), before)

    def make_v6_fixture(self, *, projections=30, active=10):
        state = self.home / "state"; state.mkdir(mode=0o700, exist_ok=True)
        with EventStore(self.db) as store:
            for number in range(projections):
                task = f"task-{number:02d}"
                store._connection.execute("INSERT INTO task_projections(task_id,last_event_seq,projection_json) VALUES(?,0,'{}')", (task,))
            store._connection.execute("ALTER TABLE task_membership DROP COLUMN retirement_reason")
            store._connection.execute("DROP TABLE producer_migration_quarantine")
            store._connection.execute("DELETE FROM daemon_metadata WHERE key='producer_custody_version'")
            store._connection.execute("PRAGMA user_version=6")
        for number in range(active):
            (state / f"task-{number:02d}.meta").write_text(f"pane=pane-{number}\n")
            os.chmod(state / f"task-{number:02d}.meta", 0o600)
        return state

    def test_production_shaped_migration_scopes_ten_of_thirty_without_deleting_history(self):
        state = self.make_v6_fixture()
        with EventStore(self.db, state_dir=state) as store:
            self.assertEqual(store.schema_version, 7)
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM task_projections").fetchone()[0], 30)
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM task_membership WHERE present=1").fetchone()[0], 10)
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM task_membership WHERE present=0").fetchone()[0], 20)

    def test_migration_preconditions_and_commit_failure_leave_v6_unchanged(self):
        state = self.make_v6_fixture(projections=1, active=1)
        class FailingStore(EventStore):
            def _commit(self): raise RuntimeError("injected migration failure")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            FailingStore(self.db, state_dir=state)
        raw = sqlite3.connect(self.db)
        self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], 6)
        self.assertNotIn("retirement_reason", {row[1] for row in raw.execute("PRAGMA table_info(task_membership)")})
        self.assertIsNone(raw.execute("SELECT name FROM sqlite_master WHERE name='producer_migration_quarantine'").fetchone())
        raw.close()
        with self.assertRaisesRegex(RuntimeError, "empty spool"):
            EventStore(self.db, state_dir=state, spool_backlog=1)

    def test_old_binary_refuses_schema_seven(self):
        with EventStore(self.db): pass
        with mock.patch.object(store_module, "SCHEMA_VERSION", 6):
            with self.assertRaisesRegex(RuntimeError, "newer than supported 6"):
                EventStore(self.db)


if __name__ == "__main__": unittest.main()
