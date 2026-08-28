import sqlite3
import tempfile
import unittest
from pathlib import Path

from lib.rozoro_monitor.store import SCHEMA_VERSION, ActionableChange, EventStore


def event(number):
    kind = "session.register" if number == 1 else ("turn.start" if number % 2 == 0 else "turn.stop")
    item = {"v": 1, "type": kind, "event_id": f"event-{number}", "producer_seq": number,
            "session_id": "crew-session", "harness": "claude", "role": "crew", "task_id": "task-1"}
    if kind == "turn.start":
        item["turn_id"] = f"turn-{number}"
    elif kind == "turn.stop":
        item["background_active"] = False
    return item


class DeliveryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        (self.home / "tasks" / "task-1").mkdir(parents=True)
        self.db = self.home / "monitor.db"

    def tearDown(self):
        self.temp.cleanup()

    def open_ready(self):
        store = EventStore(self.db)
        self.epoch = store.register_driver("driver-1", "watch-1", "pi")["epoch"]
        return store

    def test_twenty_actionable_events_remain_twenty_facts(self):
        with self.open_ready() as store:
            for number in range(1, 21):
                store.accept_event(event(number))
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 20)
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM pending_generations").fetchone()[0], 20)
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM generation_task_snapshots").fetchone()[0], 20)
            offer = store.offer_notification("driver-1", "watch-1", self.epoch)
            self.assertEqual(offer["generation"], 20)
            self.assertEqual(offer["task_count"], 1)

    def test_exact_offer_confirmation_and_n_plus_one_isolation(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            self.assertEqual(store.offer_notification("driver-1", "watch-1", self.epoch)["generation"], 1)
            store.accept_event(event(2))
            # The original unconfirmed N remains the only offer; N+1 cannot supersede it.
            self.assertEqual(store.offer_notification("driver-1", "watch-1", self.epoch)["generation"], 1)
            with self.assertRaises(ValueError):
                store.confirm_delivery("driver-1", "watch-1", self.epoch, 2)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 1)
            ledger = store._connection.execute("SELECT latest_generation,delivered_generation,acked_generation FROM watchtower_deliveries").fetchone()
            self.assertEqual(tuple(ledger), (2, 1, 0))
            reports = store.reconcile("driver-1", "watch-1", self.epoch, 1)
            self.assertEqual([item["generation"] for item in reports], [1])
            self.assertEqual(store._connection.execute("SELECT acked_generation FROM watchtower_deliveries").fetchone()[0], 0)
            store.ack_generation("driver-1", "watch-1", self.epoch, 1)
            self.assertEqual(store.offer_notification("driver-1", "watch-1", self.epoch)["generation"], 2)

    def test_delivered_unacked_suppresses_same_epoch_before_and_after_n_plus_one(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            store.offer_notification("driver-1", "watch-1", self.epoch)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 1)
            self.assertIsNone(store.offer_notification("driver-1", "watch-1", self.epoch))
            store.accept_event(event(2))
            self.assertIsNone(store.offer_notification("driver-1", "watch-1", self.epoch))
            self.assertEqual(tuple(store._connection.execute(
                "SELECT latest_generation,delivered_generation,acked_generation FROM watchtower_deliveries"
            ).fetchone()), (2, 1, 0))

    def test_reconcile_delivered_returns_changed_task_delta(self):
        def reducer(task_id, availability):
            def apply(tx, item, durable_seq):
                tx.upsert_task_projection(task_id, durable_seq, availability=availability,
                                          projection={"availability": availability})
            return apply
        def actionable(task_id, reason):
            return lambda tx, item, durable_seq, reduced: ActionableChange(task_id, reason)
        with self.open_ready() as store:
            # g1 changes task-1, g2 changes task-2.
            store.accept_event(event(1), reducer=reducer("task-1", "quiescent"),
                               actionable=actionable("task-1", "quiescent"))
            store.accept_event(event(2), reducer=reducer("task-2", "blocked"),
                               actionable=actionable("task-2", "blocked"))
            store.offer_notification("driver-1", "watch-1", self.epoch)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 2)
            # First reconcile spans (0, 2]: both tasks, nothing suppressed.
            delivered, reports, since, unchanged = store.reconcile_delivered("driver-1")
            self.assertEqual(delivered, 2)
            self.assertEqual(sorted(r["task_id"] for r in reports), ["task-1", "task-2"])
            self.assertEqual((since, unchanged), (0, 0))
            store.ack_delivered("driver-1", 2)

            # g3 changes only task-1; task-2 is unchanged and must not reappear.
            store.accept_event(event(3), reducer=reducer("task-1", "blocked"),
                               actionable=actionable("task-1", "blocked"))
            store.offer_notification("driver-1", "watch-1", self.epoch)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 3)
            delivered, reports, since, unchanged = store.reconcile_delivered("driver-1")
            self.assertEqual(delivered, 3)
            # delivered (3) > acked (2) so the delta is provably non-empty.
            self.assertEqual([r["task_id"] for r in reports], ["task-1"])
            self.assertEqual((since, unchanged), (2, 1))

            # full=True recovers the complete latest-per-task snapshot.
            _, full_reports, full_since, full_unchanged = store.reconcile_delivered("driver-1", full=True)
            self.assertEqual(sorted(r["task_id"] for r in full_reports), ["task-1", "task-2"])
            self.assertEqual((full_since, full_unchanged), (2, 0))
            # Every generation re-freezes all projections, so the full snapshot
            # carries each task's latest frozen generation (the delivered cursor).
            self.assertEqual({r["task_id"]: r["generation"] for r in full_reports},
                             {"task-1": 3, "task-2": 3})

    def test_ack_n_cannot_consume_n_plus_one_and_duplicates_are_idempotent(self):
        with self.open_ready() as store:
            first = store.accept_event(event(1))
            duplicate = store.accept_event(event(1))
            self.assertEqual((first.durable_seq, duplicate.durable_seq), (1, 1))
            self.assertTrue(duplicate.duplicate)
            store.offer_notification("driver-1", "watch-1", self.epoch)
            self.assertTrue(store.confirm_delivery("driver-1", "watch-1", self.epoch, 1))
            self.assertFalse(store.confirm_delivery("driver-1", "watch-1", self.epoch, 1))
            store.accept_event(event(2))
            self.assertTrue(store.ack_generation("driver-1", "watch-1", self.epoch, 1))
            self.assertFalse(store.ack_generation("driver-1", "watch-1", self.epoch, 1))
            self.assertEqual(store._connection.execute("SELECT acked_generation FROM watchtower_deliveries").fetchone()[0], 1)
            self.assertEqual(store.reconcile("driver-1", "watch-1", self.epoch, 1)[0]["generation"], 1)

    def test_reconnect_redelivery_ack_before_duplicate_confirmation_exposes_n_plus_one(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            store.offer_notification("driver-1", "watch-1", self.epoch)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 1)
            store.accept_event(event(2))

            reconnect_epoch = store.register_driver("driver-1", "watch-2", "pi")["epoch"]
            self.assertEqual(store.offer_notification(
                "driver-1", "watch-2", reconnect_epoch)["generation"], 1)
            # Durable d=1 permits reconciliation/ACK even if the reconnect's
            # duplicate redelivery confirmation has not arrived.
            self.assertEqual(store.reconcile(
                "driver-1", "watch-2", reconnect_epoch, 1)[0]["generation"], 1)
            store.ack_generation("driver-1", "watch-2", reconnect_epoch, 1)
            self.assertFalse(store.confirm_delivery(
                "driver-1", "watch-2", reconnect_epoch, 1))
            self.assertEqual(store.offer_notification(
                "driver-1", "watch-2", reconnect_epoch)["generation"], 2)

    def test_partial_ack_preserves_higher_unconfirmed_redelivery(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            store.accept_event(event(2))
            self.assertEqual(store.offer_notification(
                "driver-1", "watch-1", self.epoch)["generation"], 2)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 2)
            reconnect_epoch = store.register_driver("driver-1", "watch-2", "pi")["epoch"]
            self.assertEqual(store.offer_notification(
                "driver-1", "watch-2", reconnect_epoch)["generation"], 2)
            store.ack_generation("driver-1", "watch-2", reconnect_epoch, 1)
            self.assertEqual(store.offer_notification(
                "driver-1", "watch-2", reconnect_epoch)["generation"], 2)

    def test_same_session_reconnect_invalidates_every_old_socket_operation(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            old_epoch = self.epoch
            store.offer_notification("driver-1", "watch-1", old_epoch)
            new_epoch = store.register_driver("driver-1", "watch-1", "pi")["epoch"]
            self.assertGreater(new_epoch, old_epoch)
            for operation in (
                lambda: store.offer_notification("driver-1", "watch-1", old_epoch),
                lambda: store.confirm_delivery("driver-1", "watch-1", old_epoch, 1),
                lambda: store.reconcile("driver-1", "watch-1", old_epoch, 1),
                lambda: store.ack_generation("driver-1", "watch-1", old_epoch, 1),
                lambda: store.watchtower_availability("driver-1", "watch-1", old_epoch),
            ):
                with self.assertRaises(ValueError):
                    operation()
            self.assertEqual(store.offer_notification("driver-1", "watch-1", new_epoch)["generation"], 1)

    def test_disable_atomically_tombstones_adapter_before_new_generation(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            store.offer_notification("driver-1", "watch-1", self.epoch)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 1)
            store.ack_generation("driver-1", "watch-1", self.epoch, 1)
            store.disable_driver_authority("driver-1")
            store.disable_driver_authority("driver-1")  # uncertain first response is retry-idempotent
            self.assertEqual(store.driver_authority("driver-1"), "disabled")
            store.accept_event(event(2))
            self.assertEqual(store._connection.execute(
                "SELECT COUNT(*) FROM watchtower_deliveries WHERE driver_id='driver-1'"
            ).fetchone()[0], 0)
            with self.assertRaisesRegex(ValueError, "disabled for legacy fallback"):
                store.register_driver("driver-1", "racing-adapter", "pi")

    def test_delivered_unacked_survives_reopen_and_reconnect(self):
        with self.open_ready() as store:
            store.accept_event(event(1))
            store.offer_notification("driver-1", "watch-1", self.epoch)
            store.confirm_delivery("driver-1", "watch-1", self.epoch, 1)
        with EventStore(self.db) as store:
            epoch2 = store.register_driver("driver-1", "watch-2", "pi")["epoch"]
            offer = store.offer_notification("driver-1", "watch-2", epoch2)
            self.assertEqual(offer["generation"], 1)
            with self.assertRaises(ValueError):
                store.confirm_delivery("driver-1", "watch-1", self.epoch, 1)
            store.confirm_delivery("driver-1", "watch-2", epoch2, 1)
            self.assertEqual(store.reconcile("driver-1", "watch-2", epoch2, 1)[0]["generation"], 1)

    def test_populated_v4_generation_history_is_rejected_for_reset(self):
        with EventStore(self.db) as store:
            store.accept_event(event(1))
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            store._connection.execute("DROP TABLE pending_sends")
            store._connection.execute("ALTER TABLE generation_task_snapshots DROP COLUMN compat_complete")
            store._connection.execute("DROP TABLE disabled_drivers")
            store._connection.execute("DROP TABLE delivery_offers")
            store._connection.execute("DROP TABLE watchtower_registrations")
            store._connection.execute("DROP TABLE generation_membership_snapshots")
            store._connection.execute("PRAGMA user_version=4")
        with self.assertRaisesRegex(RuntimeError, "monitor reset --force"):
            EventStore(self.db)

    def test_populated_v5_snapshots_are_rejected_instead_of_silent_empty_backfill(self):
        with EventStore(self.db) as store:
            store.accept_event(event(1))
            store._connection.execute("DROP TABLE pending_sends")
            store._connection.execute("ALTER TABLE generation_task_snapshots DROP COLUMN compat_complete")
            store._connection.execute("DROP TABLE disabled_drivers")
            store._connection.execute("PRAGMA user_version=5")
        with self.assertRaisesRegex(RuntimeError, "snapshots lacking immutable report fields"):
            EventStore(self.db)
        raw = sqlite3.connect(self.db)
        self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], 5)
        raw.close()

    def test_v5_generation_zero_task_projection_is_rejected_before_truthful_marker(self):
        with EventStore(self.db) as store:
            store._connection.execute(
                "INSERT INTO task_projections(task_id,last_event_seq,projection_json) VALUES('zero',0,'{}')"
            )
            store._connection.execute("DROP TABLE pending_sends")
            store._connection.execute("ALTER TABLE generation_task_snapshots DROP COLUMN compat_complete")
            store._connection.execute("DROP TABLE disabled_drivers")
            store._connection.execute("PRAGMA user_version=5")
        with self.assertRaisesRegex(RuntimeError, "snapshots lacking immutable report fields"):
            EventStore(self.db)

    def test_v4_generation_zero_task_projection_is_rejected_before_truthful_marker(self):
        with EventStore(self.db) as store:
            store._connection.execute(
                "INSERT INTO task_projections(task_id,last_event_seq,projection_json) VALUES('zero',0,'{}')"
            )
            store._connection.execute("DROP TABLE pending_sends")
            store._connection.execute("ALTER TABLE generation_task_snapshots DROP COLUMN compat_complete")
            store._connection.execute("DROP TABLE disabled_drivers")
            store._connection.execute("DROP TABLE delivery_offers")
            store._connection.execute("DROP TABLE watchtower_registrations")
            store._connection.execute("DROP TABLE generation_membership_snapshots")
            store._connection.execute("PRAGMA user_version=4")
        with self.assertRaisesRegex(RuntimeError, "snapshots lacking immutable report fields"):
            EventStore(self.db)

    def test_empty_v5_upgrades_with_explicit_complete_marker(self):
        with EventStore(self.db) as store:
            store._connection.execute("DROP TABLE pending_sends")
            store._connection.execute("ALTER TABLE generation_task_snapshots DROP COLUMN compat_complete")
            store._connection.execute("DROP TABLE disabled_drivers")
            store._connection.execute("PRAGMA user_version=5")
        with EventStore(self.db) as store:
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            columns = {row[1] for row in store._connection.execute("PRAGMA table_info(generation_task_snapshots)")}
            self.assertIn("compat_complete", columns)

    def test_empty_v4_migration_and_transaction_rollback(self):
        with EventStore(self.db) as store:
            store._connection.execute("DROP TABLE pending_sends")
            store._connection.execute("ALTER TABLE generation_task_snapshots DROP COLUMN compat_complete")
            store._connection.execute("DROP TABLE disabled_drivers")
            store._connection.execute("DROP TABLE delivery_offers")
            store._connection.execute("DROP TABLE watchtower_registrations")
            store._connection.execute("DROP TABLE generation_membership_snapshots")
            store._connection.execute("PRAGMA user_version=4")
        with EventStore(self.db) as store:
            self.assertEqual(store.schema_version, SCHEMA_VERSION)
            original = store._commit
            store._commit = lambda: (_ for _ in ()).throw(RuntimeError("crash"))
            with self.assertRaises(RuntimeError):
                store.register_driver("driver-1", "watch-1", "pi")
            store._commit = original
            self.assertEqual(store._connection.execute(
                "SELECT COUNT(*) FROM watchtower_registrations").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
