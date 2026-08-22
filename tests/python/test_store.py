import concurrent.futures
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from lib.rozoro_monitor.store import ActionableChange, EventStore, SCHEMA_VERSION, _MIGRATIONS


def event(event_id="event-1", seq=1, kind="turn.start", **fields):
    value = {
        "v": 1, "type": kind, "event_id": event_id, "producer_seq": seq,
        "session_id": "session-1", "harness": "claude", "role": "crew",
        "task_id": "task-1",
    }
    value.update(fields)
    if kind == "turn.start":
        value.setdefault("turn_id", "turn-1")
    return value


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "private" / "monitor"
        self.db = self.home / "monitor.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_database_has_complete_versioned_schema(self):
        with EventStore(self.db) as store:
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            names = {row[0] for row in store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertTrue({"events", "sessions", "task_projections", "watchtower_deliveries",
                             "pending_generations", "pending_generation_tasks", "task_membership",
                             "daemon_metadata"} <= names)

    def test_reopen_and_upgrade_from_migration_one(self):
        self.home.mkdir(parents=True)
        connection = sqlite3.connect(self.db)
        connection.executescript(_MIGRATIONS[1])
        connection.execute("PRAGMA user_version=1")
        connection.commit()
        connection.close()
        with EventStore(self.db) as store:
            self.assertEqual(store.schema_version, 2)
            self.assertIsNotNone(store._connection.execute(
                "SELECT name FROM sqlite_master WHERE name='sessions'"
            ).fetchone())
        with EventStore(self.db) as reopened:
            self.assertEqual(reopened.schema_version, 2)

    def test_duplicate_returns_original_sequence_without_rereduction(self):
        calls = []
        def reducer(tx, item, durable_seq):
            calls.append(durable_seq)
        with EventStore(self.db) as store:
            first = store.accept_event(event(), reducer=reducer)
            duplicate = store.accept_event(event(), reducer=reducer)
            self.assertFalse(first.duplicate)
            self.assertTrue(duplicate.duplicate)
            self.assertEqual(duplicate.durable_seq, first.durable_seq)
            self.assertEqual(calls, [first.durable_seq])
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)

    def test_concurrent_duplicate_ingestion_is_serialized(self):
        calls = []
        with EventStore(self.db) as store:
            def ingest(_):
                return store.accept_event(event(), reducer=lambda tx, item, seq: calls.append(seq))
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(ingest, range(40)))
            self.assertEqual({result.durable_seq for result in results}, {1})
            self.assertEqual(sum(not result.duplicate for result in results), 1)
            self.assertEqual(calls, [1])

    def test_reducer_failure_rolls_back_event_projection_and_generation(self):
        def fail(tx, item, durable_seq):
            tx.upsert_task_projection("task-1", durable_seq, availability="busy")
            raise RuntimeError("injected")
        with EventStore(self.db) as store:
            with self.assertRaisesRegex(RuntimeError, "injected"):
                store.accept_event(event(), reducer=fail)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 0)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM task_projections").fetchone()[0], 0)
            self.assertEqual(store._connection.execute(
                "SELECT value FROM daemon_metadata WHERE key='latest_generation'"
            ).fetchone()[0], "0")
            accepted = store.accept_event(event())
            self.assertFalse(accepted.duplicate)

    def test_actionable_failure_rolls_back_event_and_reducer_persistence(self):
        def reducer(tx, item, durable_seq):
            tx.upsert_task_projection("task-1", durable_seq, availability="quiescent")
        def fail_actionable(tx, item, durable_seq, reduced):
            raise RuntimeError("generation hook failed")
        with EventStore(self.db) as store:
            with self.assertRaisesRegex(RuntimeError, "generation hook failed"):
                store.accept_event(event(), reducer=reducer, actionable=fail_actionable)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 0)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM task_projections").fetchone()[0], 0)
            self.assertEqual(store._connection.execute(
                "SELECT value FROM daemon_metadata WHERE key='latest_generation'"
            ).fetchone()[0], "0")

    def test_reducer_projection_and_actionable_generation_are_atomic(self):
        def reducer(tx, item, durable_seq):
            tx.upsert_task_projection("task-1", durable_seq, availability="quiescent")
            return "quiescent"
        def actionable(tx, item, durable_seq, reduced):
            self.assertEqual(reduced, "quiescent")
            return ActionableChange("task-1", "quiescent")
        with EventStore(self.db) as store:
            result = store.accept_event(event(), reducer=reducer, actionable=actionable)
            self.assertEqual(result.generation, 1)
            row = store._connection.execute(
                "SELECT projection_generation,actionable_reason FROM task_projections WHERE task_id='task-1'"
            ).fetchone()
            self.assertEqual(tuple(row), (1, "quiescent"))
            self.assertEqual(store._connection.execute(
                "SELECT task_id FROM pending_generation_tasks WHERE generation=1"
            ).fetchone()[0], "task-1")

    def test_default_frozen_reducer_persists_and_recovers_after_restart(self):
        with EventStore(self.db) as store:
            store.accept_event(event())
        with EventStore(self.db) as store:
            state = store._connection.execute(
                "SELECT foreground,availability,producer_seq FROM sessions WHERE session_id='session-1'"
            ).fetchone()
            self.assertEqual(tuple(state), ("running", "busy", 1))
            result = store.accept_event(event("event-2", 2, "turn.stop", background_active=False))
            self.assertFalse(result.duplicate)
        with EventStore(self.db) as store:
            state = store._connection.execute(
                "SELECT foreground,background,availability,producer_seq FROM sessions"
            ).fetchone()
            self.assertEqual(tuple(state), ("stopped", "clear", "quiescent", 2))

    def test_permissions_are_repaired_to_user_only(self):
        self.home.mkdir(parents=True, mode=0o777)
        os.chmod(self.home, 0o777)
        self.db.touch(mode=0o666)
        os.chmod(self.db, 0o666)
        with EventStore(self.db):
            self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(self.db.stat().st_mode), 0o600)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.db) + suffix)
                if sidecar.exists():
                    self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
