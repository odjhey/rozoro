import tempfile
import threading
import unittest
from pathlib import Path

from lib.rozoro_monitor.notify import (
    DEFAULT_COLLECTION_WINDOW, Coalescer, DeliveryResult, DeliveryStatus,
)
from lib.rozoro_monitor.store import ActionableChange, EventStore


def event(number, task="task-1"):
    kind = "session.register" if number == 1 else ("turn.start" if number % 2 == 0 else "turn.stop")
    value = {"v": 1, "type": kind, "event_id": f"event-{number}", "producer_seq": number,
             "session_id": "crew", "harness": "claude", "role": "crew", "task_id": task}
    if kind == "turn.start":
        value["turn_id"] = f"turn-{number}"
    elif kind == "turn.stop":
        value["background_active"] = False
    return value


def accept_fact(store, item):
    """Create an explicit semantic fact; delivery tests do not test lifecycle policy."""
    return store.accept_event(item, actionable=lambda tx, event, seq, reduced: ActionableChange(event["task_id"], "quiescent"))


class Clock:
    def __init__(self): self.now = 10.0
    def __call__(self): return self.now
    def advance(self, amount): self.now += amount


class Actuator:
    def __init__(self, *results):
        self.results = list(results)
        self.notifications = []
    def deliver(self, notification):
        self.notifications.append(notification)
        result = self.results.pop(0) if self.results else DeliveryStatus.DELIVERED
        if isinstance(result, BaseException):
            raise result
        return DeliveryResult(result)


class ReentrantActuator:
    def __init__(self, result):
        self.coalescer = None
        self.result = result
        self.calls = 0
        self.nested_result = "unset"

    def deliver(self, notification):
        self.calls += 1
        self.nested_result = self.coalescer.poll()
        return DeliveryResult(self.result)


class BlockingActuator:
    def __init__(self, result):
        self.result = result
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.notifications = []

    def deliver(self, notification):
        self.calls += 1
        self.notifications.append(notification)
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test release was not signalled")
        return DeliveryResult(self.result)


class CoalescerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        (self.home / "tasks" / "task-1").mkdir(parents=True)
        self.db = self.home / "monitor.db"
        self.clock = Clock()

    def tearDown(self): self.temp.cleanup()

    def ready(self, store, actuator, session="watch"):
        epoch = store.register_driver("driver", session, "pi")["epoch"]
        return Coalescer(store, "driver", session, epoch, actuator, clock=self.clock)

    def test_default_window_is_exactly_350_ms_and_twenty_facts_make_one_wake(self):
        self.assertEqual(DEFAULT_COLLECTION_WINDOW, 0.350)
        with EventStore(self.db) as store:
            actuator = Actuator()
            coalescer = self.ready(store, actuator)
            for number in range(1, 21):
                accept_fact(store, event(number))
                coalescer.poll()
            self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 20)
            self.assertEqual(actuator.notifications, [])
            self.clock.advance(0.349)
            coalescer.poll()
            self.assertEqual(actuator.notifications, [])
            self.clock.advance(0.001)
            coalescer.poll()
            self.assertEqual(len(actuator.notifications), 1)
            self.assertEqual(actuator.notifications[0].generation, 20)

    def test_urgent_flush_and_progress_only_never_wakes(self):
        with EventStore(self.db) as store:
            actuator = Actuator()
            coalescer = self.ready(store, actuator)
            accept_fact(store, event(1))
            coalescer.poll()
            store.accept_event(
                event(2),
                actionable=lambda tx, message, seq, reduced:
                    ActionableChange("task-1", "blocked", "urgent"),
            )
            coalescer.poll()
            self.assertEqual([(n.generation, n.priority) for n in actuator.notifications], [(2, "urgent")])
            store.ack_generation("driver", "watch", coalescer.epoch, 2)
            store.accept_event({**event(3), "event_id": "progress"}, actionable=lambda *args: None)
            self.clock.advance(1)
            coalescer.poll()
            self.assertEqual(len(actuator.notifications), 1)

    def test_deferred_error_timeout_and_uncertainty_retry_exact_offer(self):
        with EventStore(self.db) as store:
            actuator = Actuator(DeliveryStatus.DEFERRED, DeliveryStatus.ERROR,
                                TimeoutError("timeout"), DeliveryStatus.DELIVERED)
            coalescer = self.ready(store, actuator)
            accept_fact(store, event(1))
            coalescer.poll(); self.clock.advance(DEFAULT_COLLECTION_WINDOW)
            results = [coalescer.poll(), coalescer.poll(), coalescer.poll(), coalescer.poll()]
            self.assertEqual([r.status for r in results], [DeliveryStatus.DEFERRED, DeliveryStatus.ERROR,
                                                         DeliveryStatus.ERROR, DeliveryStatus.DELIVERED])
            self.assertEqual({(n.generation, n.priority, n.task_count) for n in actuator.notifications},
                             {(1, "normal", 1)})
            ledger = store._connection.execute(
                "SELECT delivered_generation FROM watchtower_deliveries WHERE driver_id='driver'"
            ).fetchone()[0]
            self.assertEqual(ledger, 1)

    def test_arrival_during_outstanding_delivery_remains_n_plus_one(self):
        with EventStore(self.db) as store:
            actuator = Actuator()
            coalescer = self.ready(store, actuator)
            accept_fact(store, event(1)); coalescer.poll(); self.clock.advance(.350); coalescer.poll()
            accept_fact(store, event(2))
            self.clock.advance(1); coalescer.poll()
            self.assertEqual([n.generation for n in actuator.notifications], [1])
            store.ack_generation("driver", "watch", coalescer.epoch, 1)
            coalescer.poll(); self.clock.advance(.350); coalescer.poll()
            self.assertEqual([n.generation for n in actuator.notifications], [1, 2])

    def test_reentrant_poll_is_suppressed_and_deferred_offer_retries_after_release(self):
        with EventStore(self.db) as store:
            actuator = ReentrantActuator(DeliveryStatus.DEFERRED)
            coalescer = self.ready(store, actuator)
            actuator.coalescer = coalescer
            accept_fact(store, event(1)); coalescer.poll(); self.clock.advance(.350)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DEFERRED)
            self.assertIsNone(actuator.nested_result)
            self.assertEqual(actuator.calls, 1)
            actuator.result = DeliveryStatus.DELIVERED
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DELIVERED)
            self.assertEqual(actuator.calls, 2)

    def test_simultaneous_poll_invokes_once_and_mixed_result_releases_guard(self):
        with EventStore(self.db) as store:
            actuator = BlockingActuator(DeliveryStatus.DELIVERED)
            coalescer = self.ready(store, actuator)
            accept_fact(store, event(1)); coalescer.poll(); self.clock.advance(.350)
            first = []
            worker = threading.Thread(target=lambda: first.append(coalescer.poll()))
            worker.start()
            self.assertTrue(actuator.entered.wait(timeout=5))
            # The loser is a deterministic no-op while delivery is in flight.
            self.assertIsNone(coalescer.poll())
            self.assertEqual(actuator.calls, 1)
            actuator.release.set(); worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(first[0].status, DeliveryStatus.DELIVERED)
            self.assertIsNone(coalescer.poll())
            # ACK and a new generation prove the claim was released normally.
            store.ack_generation("driver", "watch", coalescer.epoch, 1)
            accept_fact(store, event(2)); coalescer.poll(); self.clock.advance(.350)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DELIVERED)
            self.assertEqual(actuator.calls, 2)

    def test_reconnect_redelivery_cleanup_preserves_concurrent_n_plus_one_deadline(self):
        with EventStore(self.db) as store:
            # N was delivered on an old connection; N+1 arrived while its wake
            # remained outstanding.
            old_epoch = store.register_driver("driver", "old-watch", "pi")["epoch"]
            accept_fact(store, event(1))
            store.offer_notification("driver", "old-watch", old_epoch)
            store.confirm_delivery("driver", "old-watch", old_epoch, 1)
            accept_fact(store, event(2))

            actuator = BlockingActuator(DeliveryStatus.DELIVERED)
            coalescer = self.ready(store, actuator, "watch")
            redelivery = []
            worker = threading.Thread(target=lambda: redelivery.append(coalescer.poll()))
            worker.start()
            self.assertTrue(actuator.entered.wait(timeout=5))

            # Reconciliation can legitimately ACK N before reconnect redelivery
            # confirmation. The losing poll opens N+1's collection at t=10.0,
            # but must not duplicate N while its actuator is blocked.
            store.ack_generation("driver", "watch", coalescer.epoch, 1)
            self.assertIsNone(coalescer.poll())
            self.assertEqual(actuator.calls, 1)
            self.assertEqual(coalescer.deadline, 10.350)

            # N+2 arrives 100 ms into N+1's collection while reconnect N is
            # still blocked. It batches into that first window and must not
            # move eligibility to t=10.450.
            self.clock.advance(.100)
            accept_fact(store, event(3))
            self.assertIsNone(coalescer.poll())
            self.assertEqual(coalescer.deadline, 10.350)
            self.assertEqual(actuator.calls, 1)

            self.clock.advance(.249)
            actuator.release.set(); worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(redelivery[0].status, DeliveryStatus.DELIVERED)
            self.assertEqual(coalescer.deadline, 10.350)
            self.assertIsNone(coalescer.poll())
            self.assertEqual(actuator.calls, 1)

            # N+1 and N+2 are eligible together at the original 350 ms
            # boundary, not 350 ms after either N cleanup or N+2 arrival.
            self.clock.advance(.001)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DELIVERED)
            self.assertEqual(actuator.calls, 2)
            self.assertEqual([item.generation for item in actuator.notifications], [1, 3])

    def test_claimed_n_cannot_actuate_n_plus_one_selected_after_concurrent_ack(self):
        with EventStore(self.db) as store:
            old_epoch = store.register_driver("driver", "old-watch", "pi")["epoch"]
            accept_fact(store, event(1))
            store.offer_notification("driver", "old-watch", old_epoch)
            store.confirm_delivery("driver", "old-watch", old_epoch, 1)
            accept_fact(store, event(2))

            actuator = Actuator()
            coalescer = self.ready(store, actuator, "watch")
            entered = threading.Event()
            release = threading.Event()
            original_offer = store.offer_notification

            def paused_before_selection(*args, **kwargs):
                entered.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("offer selection was not released")
                return original_offer(*args, **kwargs)

            store.offer_notification = paused_before_selection
            owner = []
            worker = threading.Thread(target=lambda: owner.append(coalescer.poll()))
            worker.start()
            self.assertTrue(entered.wait(timeout=5))

            # N retires before selection, so the concurrent poll opens N+1's
            # fresh collection while the N owner still holds the claim.
            store.ack_generation("driver", "watch", coalescer.epoch, 1)
            self.assertIsNone(coalescer.poll())
            self.assertEqual(coalescer.deadline, 10.350)
            release.set(); worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(owner, [None])
            self.assertEqual(actuator.notifications, [])

            # Selection returned N+1, but stale immediate eligibility was not
            # used and its temporary exact offer was withdrawn. It remains
            # quiet until the already-open N+1 boundary.
            store.offer_notification = original_offer
            self.clock.advance(.349)
            self.assertIsNone(coalescer.poll())
            self.assertEqual(actuator.notifications, [])
            self.clock.advance(.001)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DELIVERED)
            self.assertEqual([item.generation for item in actuator.notifications], [2])

    def test_claim_publishes_frontier_before_paused_retry_offer_returns(self):
        with EventStore(self.db) as store:
            old_epoch = store.register_driver("driver", "old-watch", "pi")["epoch"]
            accept_fact(store, event(1))
            store.offer_notification("driver", "old-watch", old_epoch)
            store.confirm_delivery("driver", "old-watch", old_epoch, 1)
            accept_fact(store, event(2))

            actuator = Actuator(DeliveryStatus.DEFERRED, DeliveryStatus.DEFERRED,
                                DeliveryStatus.DELIVERED)
            coalescer = self.ready(store, actuator, "watch")
            # First reconnect redelivery is deferred, leaving exact offer N and
            # an old collection deadline that will expire before retry.
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DEFERRED)
            self.clock.advance(1.0)

            returned = threading.Event()
            release = threading.Event()
            original_offer = store.offer_notification

            def paused_offer(*args, **kwargs):
                offer = original_offer(*args, **kwargs)
                returned.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("paused offer was not released")
                return offer

            store.offer_notification = paused_offer
            retry = []
            worker = threading.Thread(target=lambda: retry.append(coalescer.poll()))
            worker.start()
            self.assertTrue(returned.wait(timeout=5))

            # ACK after offer return exposes N+1. The concurrent poll must see
            # the already-published N claim and open a fresh t=11.350 window,
            # rather than reuse N's expired t=10.350 deadline.
            store.ack_generation("driver", "watch", coalescer.epoch, 1)
            self.assertIsNone(coalescer.poll())
            self.assertEqual(coalescer.deadline, 11.350)
            self.assertEqual(len(actuator.notifications), 1)

            release.set(); worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(retry[0].status, DeliveryStatus.DEFERRED)
            store.offer_notification = original_offer
            self.assertIsNone(coalescer.poll())
            self.assertEqual(len(actuator.notifications), 2)
            self.clock.advance(.350)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DELIVERED)
            self.assertEqual([item.generation for item in actuator.notifications], [1, 1, 2])

    def test_invalid_result_and_exception_release_guard_for_exact_retry(self):
        with EventStore(self.db) as store:
            actuator = Actuator("invalid", RuntimeError("disconnect"), DeliveryStatus.DELIVERED)
            coalescer = self.ready(store, actuator)
            accept_fact(store, event(1)); coalescer.poll(); self.clock.advance(.350)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.ERROR)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.ERROR)
            self.assertEqual(coalescer.poll().status, DeliveryStatus.DELIVERED)
            self.assertEqual([n.generation for n in actuator.notifications], [1, 1, 1])

    def test_restart_and_reconnect_create_no_facts_or_synthetic_generations(self):
        with EventStore(self.db) as store:
            first = Actuator()
            coalescer = self.ready(store, first)
            accept_fact(store, event(1)); coalescer.poll(); self.clock.advance(.350); coalescer.poll()
        with EventStore(self.db) as store:
            before = tuple(store._connection.execute(
                "SELECT (SELECT COUNT(*) FROM events),(SELECT value FROM daemon_metadata WHERE key='latest_generation')"
            ).fetchone())
            second = Actuator(DeliveryStatus.DEFERRED, DeliveryStatus.DELIVERED)
            reconnect = self.ready(store, second, "watch-2")
            reconnect.poll(); reconnect.poll()
            after = tuple(store._connection.execute(
                "SELECT (SELECT COUNT(*) FROM events),(SELECT value FROM daemon_metadata WHERE key='latest_generation')"
            ).fetchone())
            self.assertEqual(before, after)
            self.assertEqual([n.generation for n in second.notifications], [1, 1])


if __name__ == "__main__": unittest.main()
