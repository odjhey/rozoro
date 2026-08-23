import tempfile
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
                store.accept_event(event(number))
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
            store.accept_event(event(1))
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
            store.accept_event(event(1))
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
            store.accept_event(event(1)); coalescer.poll(); self.clock.advance(.350); coalescer.poll()
            store.accept_event(event(2))
            self.clock.advance(1); coalescer.poll()
            self.assertEqual([n.generation for n in actuator.notifications], [1])
            store.ack_generation("driver", "watch", coalescer.epoch, 1)
            coalescer.poll(); self.clock.advance(.350); coalescer.poll()
            self.assertEqual([n.generation for n in actuator.notifications], [1, 2])

    def test_restart_and_reconnect_create_no_facts_or_synthetic_generations(self):
        with EventStore(self.db) as store:
            first = Actuator()
            coalescer = self.ready(store, first)
            store.accept_event(event(1)); coalescer.poll(); self.clock.advance(.350); coalescer.poll()
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
