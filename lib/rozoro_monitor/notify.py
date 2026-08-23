"""Deterministic notification collection and narrow delivery actuator contract.

The coalescer owns no authoritative task state.  It observes the durable ledger,
waits on an injected monotonic clock, and offers a content-free notification.
Only an actuator's explicit ``delivered`` result confirms the exact durable
offer; every other outcome leaves that offer pending for an identical retry.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .store import EventStore

DEFAULT_COLLECTION_WINDOW = 0.350


class DeliveryStatus(str, Enum):
    DELIVERED = "delivered"
    DEFERRED = "deferred"
    ERROR = "error"


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatus
    error: str | None = None


@dataclass(frozen=True)
class Notification:
    """The complete, deliberately prose-free actuator payload."""

    generation: int
    priority: str
    task_count: int


class DeliveryActuator(Protocol):
    def deliver(self, notification: Notification) -> DeliveryResult:
        """Return DELIVERED only after the actuator's exact confirmation contract."""


@dataclass
class _Collection:
    generation: int
    deadline: float


class Coalescer:
    """Controlled-clock scheduler for one durable watchtower registration.

    ``poll`` is intentionally synchronous and non-blocking.  Production event
    loops call it when facts arrive and when their timer fires; tests advance a
    virtual clock and never sleep.
    """

    def __init__(
        self,
        store: EventStore,
        driver_id: str,
        session_id: str,
        epoch: int,
        actuator: DeliveryActuator,
        *,
        clock: Callable[[], float] = time.monotonic,
        collection_window: float = DEFAULT_COLLECTION_WINDOW,
    ):
        if collection_window < 0:
            raise ValueError("collection_window must be non-negative")
        self.store = store
        self.driver_id = driver_id
        self.session_id = session_id
        self.epoch = epoch
        self.actuator = actuator
        self.clock = clock
        self.collection_window = collection_window
        self._collection: _Collection | None = None
        # A non-reentrant claim suppresses both recursive actuator callbacks and
        # simultaneous event-loop/thread polls without blocking either caller.
        self._delivery_claim = threading.Lock()

    @property
    def deadline(self) -> float | None:
        return None if self._collection is None else self._collection.deadline

    def poll(self) -> DeliveryResult | None:
        now = self.clock()
        frontier = self.store.notification_frontier(self.driver_id, self.session_id, self.epoch)
        if frontier is None:
            self._collection = None
            return None

        generation, priority, immediate = frontier
        if self._collection is None:
            self._collection = _Collection(generation, now + self.collection_window)
        else:
            self._collection.generation = generation

        # Urgent facts flush an existing normal window immediately.  A durable
        # delivered-but-unacked wake still suppresses N+1 in Store.offer_notification.
        if not immediate and priority != "urgent" and now < self._collection.deadline:
            return None

        if not self._delivery_claim.acquire(blocking=False):
            # Another poll owns the exact offer. Suppression is a normal no-op,
            # not an actuator error and not permission to duplicate delivery.
            return None
        try:
            offer = self.store.offer_notification(self.driver_id, self.session_id, self.epoch)
            if offer is None:
                self._collection = None
                return None
            notification = Notification(**offer)
            try:
                result = self.actuator.deliver(notification)
            except Exception as exc:
                # Timeout, disconnect, and uncertainty are errors, never implicit delivery.
                result = DeliveryResult(DeliveryStatus.ERROR, type(exc).__name__)
            if (not isinstance(result, DeliveryResult)
                    or not isinstance(result.status, DeliveryStatus)):
                result = DeliveryResult(DeliveryStatus.ERROR, "invalid actuator result")
            if result.status is DeliveryStatus.DELIVERED:
                self.store.confirm_delivery(
                    self.driver_id, self.session_id, self.epoch, notification.generation
                )
                self._collection = None
            else:
                self.store.record_delivery_outcome(
                    self.driver_id, self.session_id, self.epoch, notification.generation,
                    result.status.value, result.error,
                )
            # The unconfirmed delivery_offers row preserves the exact generation,
            # priority, and count for deferred/error retries.
            return result
        finally:
            # Includes delivered, deferred, error, invalid result, timeout,
            # disconnect, actuator exception, and durable-store exception paths.
            self._delivery_claim.release()
