"""Daemon-owned, versioned SQLite persistence for the Rozoro event bus.

The store has one serialized connection and one transaction boundary for event
insertion, lifecycle reduction, projection persistence, and actionable
membership.  Socket/client code deliberately does not live here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .reducer import LifecycleState, PendingEvent, ReportState, reduce_event

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class AcceptedEvent:
    durable_seq: int
    duplicate: bool
    generation: int | None = None


@dataclass(frozen=True)
class ActionableChange:
    """An optional generation bump returned by an actionable hook."""

    task_id: str
    reason: str
    priority: str = "normal"


ReducerHook = Callable[["StoreTransaction", Mapping[str, Any], int], Any]
ActionableHook = Callable[["StoreTransaction", Mapping[str, Any], int, Any], ActionableChange | None]


_MIGRATIONS = {
    1: """
        CREATE TABLE events (
            durable_seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            session_id TEXT NOT NULL,
            task_id TEXT,
            driver_id TEXT,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE INDEX events_session_seq ON events(session_id, durable_seq);
        CREATE TABLE daemon_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO daemon_metadata(key, value) VALUES ('latest_generation', '0');
    """,
    2: """
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            task_id TEXT,
            driver_id TEXT,
            harness TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('crew','watchtower')),
            foreground TEXT NOT NULL DEFAULT 'unknown',
            background TEXT NOT NULL DEFAULT 'unknown',
            background_count INTEGER,
            availability TEXT NOT NULL DEFAULT 'unknown',
            producer_seq INTEGER NOT NULL DEFAULT 0,
            reducer_state_json TEXT NOT NULL,
            latest_durable_seq INTEGER NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE INDEX sessions_task ON sessions(task_id);
        CREATE INDEX sessions_driver ON sessions(driver_id);
        CREATE TABLE task_projections (
            task_id TEXT PRIMARY KEY,
            availability TEXT NOT NULL DEFAULT 'unknown',
            report_state TEXT NOT NULL DEFAULT 'missing',
            verdict TEXT,
            actionable_reason TEXT NOT NULL DEFAULT 'none',
            projection_generation INTEGER NOT NULL DEFAULT 0,
            last_event_seq INTEGER NOT NULL,
            projection_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE watchtower_deliveries (
            driver_id TEXT PRIMARY KEY,
            latest_generation INTEGER NOT NULL DEFAULT 0,
            delivered_generation INTEGER NOT NULL DEFAULT 0,
            acked_generation INTEGER NOT NULL DEFAULT 0,
            delivery_state TEXT NOT NULL DEFAULT 'pending',
            last_error TEXT,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            CHECK(acked_generation <= delivered_generation),
            CHECK(delivered_generation <= latest_generation)
        );
        CREATE TABLE pending_generations (
            generation INTEGER PRIMARY KEY,
            priority TEXT NOT NULL CHECK(priority IN ('normal','urgent')),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE pending_generation_tasks (
            generation INTEGER NOT NULL REFERENCES pending_generations(generation) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            actionable_reason TEXT NOT NULL,
            PRIMARY KEY(generation, task_id)
        );
        CREATE TABLE task_membership (
            task_id TEXT PRIMARY KEY,
            present INTEGER NOT NULL CHECK(present IN (0,1)),
            updated_event_seq INTEGER,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
    """,
}


def _state_to_json(state: LifecycleState) -> str:
    value = asdict(state)
    value["active_jobs"] = sorted(state.active_jobs)
    value["pending_events"] = [
        {"producer_seq": item.producer_seq, "fields": list(item.fields)}
        for item in state.pending_events
    ]
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _state_from_json(raw: str) -> LifecycleState:
    value = json.loads(raw)
    value["active_jobs"] = frozenset(value.get("active_jobs", ()))
    value["pending_events"] = tuple(
        PendingEvent(item["producer_seq"], tuple(tuple(pair) for pair in item["fields"]))
        for item in value.get("pending_events", ())
    )
    value["report"] = ReportState(**value.get("report", {}))
    return LifecycleState(**value)


class StoreTransaction:
    """Narrow transaction API supplied to reducer/actionable hooks."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def get_session_state(self, session_id: str) -> LifecycleState | None:
        row = self._connection.execute(
            "SELECT reducer_state_json FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        return None if row is None else _state_from_json(row[0])

    def persist_session(self, event: Mapping[str, Any], durable_seq: int, state: LifecycleState) -> None:
        self._connection.execute(
            """INSERT INTO sessions(
                   session_id,task_id,driver_id,harness,role,foreground,background,
                   background_count,availability,producer_seq,reducer_state_json,latest_durable_seq
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                   task_id=excluded.task_id, driver_id=excluded.driver_id,
                   foreground=excluded.foreground, background=excluded.background,
                   background_count=excluded.background_count,
                   availability=excluded.availability, producer_seq=excluded.producer_seq,
                   reducer_state_json=excluded.reducer_state_json,
                   latest_durable_seq=excluded.latest_durable_seq,
                   last_seen_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
            (
                event["session_id"], event.get("task_id"), event.get("driver_id"),
                event["harness"], event["role"], state.foreground, state.background,
                state.active_count, state.availability, state.producer_seq,
                _state_to_json(state), durable_seq,
            ),
        )

    def upsert_task_projection(
        self, task_id: str, durable_seq: int, *, availability: str,
        report_state: str = "missing", verdict: str | None = None,
        actionable_reason: str = "none", projection: Mapping[str, Any] | None = None,
    ) -> None:
        self._connection.execute(
            """INSERT INTO task_projections(
                   task_id,availability,report_state,verdict,actionable_reason,last_event_seq,projection_json
               ) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(task_id) DO UPDATE SET
                   availability=excluded.availability, report_state=excluded.report_state,
                   verdict=excluded.verdict, actionable_reason=excluded.actionable_reason,
                   last_event_seq=excluded.last_event_seq, projection_json=excluded.projection_json""",
            (task_id, availability, report_state, verdict, actionable_reason, durable_seq,
             json.dumps(projection or {}, sort_keys=True, separators=(",", ":"))),
        )

    def bump_actionable(self, change: ActionableChange) -> int:
        row = self._connection.execute(
            "UPDATE daemon_metadata SET value=CAST(value AS INTEGER)+1 WHERE key='latest_generation' RETURNING value"
        ).fetchone()
        generation = int(row[0])
        self._connection.execute(
            "INSERT INTO pending_generations(generation,priority) VALUES(?,?)",
            (generation, change.priority),
        )
        self._connection.execute(
            "INSERT INTO pending_generation_tasks(generation,task_id,actionable_reason) VALUES(?,?,?)",
            (generation, change.task_id, change.reason),
        )
        self._connection.execute(
            """UPDATE task_projections SET projection_generation=?, actionable_reason=?
               WHERE task_id=?""",
            (generation, change.reason, change.task_id),
        )
        self._connection.execute(
            "UPDATE watchtower_deliveries SET latest_generation=?", (generation,)
        )
        return generation


def _default_reducer(tx: StoreTransaction, event: Mapping[str, Any], durable_seq: int) -> LifecycleState:
    state = tx.get_session_state(event["session_id"]) or LifecycleState()
    result = reduce_event(state, event)
    tx.persist_session(event, durable_seq, result.state)
    return result.state


class EventStore:
    """One connection and lock: the daemon's only SQLite write path."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        existed = self.path.exists()
        if not existed:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(fd)
        os.chmod(self.path, 0o600)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        # WAL sidecars inherit process umask; tighten any that already exist.
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.exists():
                os.chmod(sidecar, 0o600)

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _migrate(self) -> None:
        with self._lock, self._immediate() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"database schema {current} is newer than supported {SCHEMA_VERSION}")
            for version in range(current + 1, SCHEMA_VERSION + 1):
                # sqlite3.executescript() issues an implicit COMMIT and would
                # split a migration from its version bump. Execute complete
                # statements individually inside our BEGIN IMMEDIATE instead.
                statement = ""
                for line in _MIGRATIONS[version].splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ""
                if statement.strip():  # a migration constant is programmer-owned
                    raise RuntimeError(f"incomplete SQL in migration {version}")
                connection.execute(f"PRAGMA user_version={version}")

    @property
    def schema_version(self) -> int:
        with self._lock:
            return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    def accept_event(
        self, event: Mapping[str, Any], *, reducer: ReducerHook | None = _default_reducer,
        actionable: ActionableHook | None = None,
    ) -> AcceptedEvent:
        """Durably accept once; duplicates never invoke either hook."""
        payload = json.dumps(dict(event), sort_keys=True, separators=(",", ":"))
        with self._lock, self._immediate() as connection:
            duplicate = connection.execute(
                "SELECT durable_seq FROM events WHERE event_id=?", (event["event_id"],)
            ).fetchone()
            if duplicate is not None:
                return AcceptedEvent(int(duplicate[0]), True)
            cursor = connection.execute(
                """INSERT INTO events(event_id,session_id,task_id,driver_id,event_type,payload_json)
                   VALUES(?,?,?,?,?,?)""",
                (event["event_id"], event["session_id"], event.get("task_id"),
                 event.get("driver_id"), event["type"], payload),
            )
            durable_seq = int(cursor.lastrowid)
            tx = StoreTransaction(connection)
            reduced = reducer(tx, event, durable_seq) if reducer is not None else None
            change = actionable(tx, event, durable_seq, reduced) if actionable is not None else None
            generation = tx.bump_actionable(change) if change is not None else None
            return AcceptedEvent(durable_seq, False, generation)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
