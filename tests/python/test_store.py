import concurrent.futures
import json
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
                             "generation_task_snapshots", "daemon_metadata"} <= names)

    def create_v2_database(self):
        self.home.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db)
        connection.executescript(_MIGRATIONS[1])
        connection.executescript(_MIGRATIONS[2])
        connection.execute("PRAGMA user_version=2")
        connection.commit()
        return connection

    def assert_database_remains_v2(self):
        connection = sqlite3.connect(self.db, timeout=0)
        try:
            # Also proves failed EventStore construction closed its connection
            # and released the migration write lock.
            connection.execute("BEGIN IMMEDIATE")
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='generation_task_snapshots'"
            ).fetchone())
            connection.rollback()
        finally:
            connection.close()

    @staticmethod
    def insert_v2_event(connection, item):
        connection.execute(
            """INSERT INTO events(
                   event_id,session_id,task_id,driver_id,event_type,payload_json)
               VALUES(?,?,?,?,?,?)""",
            (item["event_id"], item["session_id"], item.get("task_id"),
             item.get("driver_id"), item["type"], json.dumps(item)),
        )

    def test_reopen_and_upgrade_from_migration_one(self):
        self.home.mkdir(parents=True)
        connection = sqlite3.connect(self.db)
        connection.executescript(_MIGRATIONS[1])
        connection.execute("PRAGMA user_version=1")
        connection.commit()
        connection.close()
        with EventStore(self.db) as store:
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            self.assertIsNotNone(store._connection.execute(
                "SELECT name FROM sqlite_master WHERE name='sessions'"
            ).fetchone())
            self.assertIsNotNone(store._connection.execute(
                "SELECT name FROM sqlite_master WHERE name='generation_task_snapshots'"
            ).fetchone())
        with EventStore(self.db) as reopened:
            self.assertEqual(reopened.schema_version, SCHEMA_VERSION)

    def test_populated_v2_generation_state_is_rejected_without_version_bump(self):
        connection = self.create_v2_database()
        connection.execute(
            """INSERT INTO task_projections(
                   task_id,availability,actionable_reason,projection_generation,last_event_seq,projection_json)
               VALUES('task-1','quiescent','quiescent',1,1,'{"state":"at-one"}')"""
        )
        connection.execute("INSERT INTO pending_generations(generation,priority) VALUES(1,'normal')")
        connection.execute(
            "INSERT INTO pending_generation_tasks VALUES(1,'task-1','quiescent')"
        )
        # v2 mutates latest-only state for N+1, destroying the exact N view.
        connection.execute(
            """UPDATE task_projections SET availability='blocked', actionable_reason='blocked',
                   projection_generation=2, last_event_seq=2, projection_json='{"state":"at-two"}'
               WHERE task_id='task-1'"""
        )
        connection.execute("INSERT INTO pending_generations(generation,priority) VALUES(2,'urgent')")
        connection.execute("INSERT INTO pending_generation_tasks VALUES(2,'task-1','blocked')")
        connection.execute("UPDATE daemon_metadata SET value='2' WHERE key='latest_generation'")
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "immutable projection history is unavailable"):
            EventStore(self.db)
        self.assert_database_remains_v2()

    def test_populated_v2_invalid_session_owner_is_rejected_without_version_bump(self):
        connection = self.create_v2_database()
        connection.execute(
            """INSERT INTO sessions(
                   session_id,task_id,driver_id,harness,role,reducer_state_json,latest_durable_seq)
               VALUES('session-bad','task-1','driver-1','claude','crew','{}',1)"""
        )
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "invalid owner identity"):
            EventStore(self.db)
        self.assert_database_remains_v2()

    def test_populated_v2_single_orphan_event_is_rejected_and_unlocks(self):
        connection = self.create_v2_database()
        self.insert_v2_event(connection, event())
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "orphan event history"):
            EventStore(self.db)
        self.assert_database_remains_v2()

    def test_populated_v2_contradictory_orphan_events_are_rejected_and_unlock(self):
        connection = self.create_v2_database()
        self.insert_v2_event(connection, event())
        self.insert_v2_event(connection, event("event-2", 2, task_id="task-2"))
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "contradictory event identities"):
            EventStore(self.db)
        self.assert_database_remains_v2()

    def test_populated_v2_safe_anchored_history_upgrades(self):
        connection = self.create_v2_database()
        first = event()
        self.insert_v2_event(connection, first)
        connection.execute(
            """INSERT INTO sessions(
                   session_id,task_id,driver_id,harness,role,reducer_state_json,latest_durable_seq)
               VALUES('session-1','task-1',NULL,'claude','crew','{}',1)"""
        )
        connection.commit()
        connection.close()

        with EventStore(self.db) as store:
            self.assertEqual(store.schema_version, 3)
            self.assertIsNotNone(store._connection.execute(
                "SELECT name FROM sqlite_master WHERE name='generation_task_snapshots'"
            ).fetchone())

    def test_populated_v2_event_payload_column_mismatch_is_rejected(self):
        connection = self.create_v2_database()
        first = event()
        connection.execute(
            """INSERT INTO events(event_id,session_id,task_id,event_type,payload_json)
               VALUES('stored-id','session-1','task-1','turn.start',?)""",
            (json.dumps(first),),
        )
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "payload identity disagrees with stored columns"):
            EventStore(self.db)
        self.assert_database_remains_v2()

    def test_populated_v2_contradictory_identity_history_is_rejected(self):
        connection = self.create_v2_database()
        first = event()
        self.insert_v2_event(connection, first)
        connection.execute(
            """INSERT INTO sessions(
                   session_id,task_id,driver_id,harness,role,reducer_state_json,latest_durable_seq)
               VALUES('session-1','task-2',NULL,'claude','crew','{}',1)"""
        )
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(RuntimeError, "contradictory identity history"):
            EventStore(self.db)
        self.assert_database_remains_v2()

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

    def test_commit_failure_rolls_back_and_leaves_connection_reusable(self):
        with EventStore(self.db) as store:
            real_commit = store._commit
            failures = 1
            def fail_once():
                nonlocal failures
                if failures:
                    failures -= 1
                    raise sqlite3.OperationalError("injected commit failure")
                real_commit()
            store._commit = fail_once
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected commit failure"):
                store.accept_event(event())
            self.assertFalse(store._connection.in_transaction)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 0)
            accepted = store.accept_event(event())
            self.assertFalse(accepted.duplicate)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)

    def test_actionable_requires_existing_projection_and_rolls_back_membership(self):
        def actionable(tx, item, durable_seq, reduced):
            return ActionableChange("missing-task", "quiescent")
        with EventStore(self.db) as store:
            with self.assertRaisesRegex(ValueError, "has no projection"):
                store.accept_event(event(), reducer=lambda *args: None, actionable=actionable)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 0)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM pending_generations").fetchone()[0], 0)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM pending_generation_tasks").fetchone()[0], 0)
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
            snapshot = store.projection_snapshots_through(1)[0]
            self.assertEqual((snapshot["generation"], snapshot["availability"], snapshot["actionable_reason"]),
                             (1, "quiescent", "quiescent"))

    def test_generation_snapshots_remain_exact_after_newer_projection(self):
        def reducer(availability):
            def apply(tx, item, durable_seq):
                tx.upsert_task_projection(
                    "task-1", durable_seq, availability=availability,
                    projection={"availability": availability, "seq": durable_seq},
                )
            return apply
        def actionable(reason):
            return lambda tx, item, durable_seq, reduced: ActionableChange("task-1", reason)
        with EventStore(self.db) as store:
            store.accept_event(event(), reducer=reducer("quiescent"), actionable=actionable("quiescent"))
            store.accept_event(event("event-2", 2), reducer=reducer("blocked"), actionable=actionable("blocked"))
            through_one = store.projection_snapshots_through(1)
            through_two = store.projection_snapshots_through(2)
            self.assertEqual(len(through_one), 1)
            self.assertEqual((through_one[0]["generation"], through_one[0]["availability"],
                              through_one[0]["projection_json"]),
                             (1, "quiescent", '{"availability":"quiescent","seq":1}'))
            self.assertEqual([(row["generation"], row["availability"]) for row in through_two],
                             [(1, "quiescent"), (2, "blocked")])

    def test_session_identity_is_immutable_in_application_and_database(self):
        with EventStore(self.db) as store:
            store.accept_event(event())
            contradictions = (
                event("event-harness", 2, harness="pi"),
                event("event-role", 2, role="watchtower", task_id=None, driver_id="driver-1"),
                event("event-owner", 2, task_id="task-2"),
            )
            for contradictory in contradictions:
                with self.subTest(contradictory=contradictory):
                    with self.assertRaisesRegex(ValueError, "identity is immutable"):
                        store.accept_event(contradictory)
                    self.assertFalse(store._connection.in_transaction)
            self.assertEqual(store._connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "session identity is immutable"):
                store._connection.execute(
                    "UPDATE sessions SET harness='pi' WHERE session_id='session-1'"
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "session role identity is invalid"):
                store._connection.execute(
                    """INSERT INTO sessions(
                           session_id,task_id,driver_id,harness,role,reducer_state_json,latest_durable_seq)
                       VALUES('invalid','task-1','driver-1','claude','crew','{}',1)"""
                )
            identity = store._connection.execute(
                "SELECT harness,role,task_id,driver_id FROM sessions WHERE session_id='session-1'"
            ).fetchone()
            self.assertEqual(tuple(identity), ("claude", "crew", "task-1", None))

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
