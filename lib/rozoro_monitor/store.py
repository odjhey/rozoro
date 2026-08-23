"""Daemon-owned, versioned SQLite persistence for the Rozoro event bus.

The store has one serialized connection and one transaction boundary for event
insertion, lifecycle reduction, projection persistence, and actionable
membership. Socket/client code deliberately does not live here.

Threat model: the owning effective UID is trusted. We reject other owners,
unsafe pre-existing entries, direct symlinks/non-files, and insecure modes, but
do not claim race-free protection against malicious concurrent mutation by the
same UID. SQLite remains file-backed in WAL mode.
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

from .handoff import parse_task_report
from .reducer import LifecycleState, PendingEvent, ReportState, reduce_event

SCHEMA_VERSION = 6


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
_DEFAULT_REDUCER = object()


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
    3: """
        CREATE TABLE generation_task_snapshots (
            generation INTEGER NOT NULL REFERENCES pending_generations(generation) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES task_projections(task_id),
            availability TEXT NOT NULL,
            report_state TEXT NOT NULL,
            verdict TEXT,
            actionable_reason TEXT NOT NULL,
            projection_generation INTEGER NOT NULL,
            last_event_seq INTEGER NOT NULL,
            projection_json TEXT NOT NULL,
            PRIMARY KEY(generation, task_id)
        );
        CREATE TRIGGER sessions_identity_immutable
        BEFORE UPDATE OF harness, role, task_id, driver_id ON sessions
        WHEN OLD.harness IS NOT NEW.harness
          OR OLD.role IS NOT NEW.role
          OR OLD.task_id IS NOT NEW.task_id
          OR OLD.driver_id IS NOT NEW.driver_id
        BEGIN
            SELECT RAISE(ABORT, 'session identity is immutable');
        END;
        CREATE TRIGGER sessions_identity_valid_insert
        BEFORE INSERT ON sessions
        WHEN (NEW.role = 'crew' AND (NEW.task_id IS NULL OR NEW.driver_id IS NOT NULL))
          OR (NEW.role = 'watchtower' AND (NEW.driver_id IS NULL OR NEW.task_id IS NOT NULL))
        BEGIN
            SELECT RAISE(ABORT, 'session role identity is invalid');
        END;
    """,
    4: """
        ALTER TABLE sessions ADD COLUMN registered INTEGER NOT NULL DEFAULT 0 CHECK(registered IN (0,1));
    """,
    5: """
        CREATE TABLE watchtower_registrations (
            driver_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            harness TEXT NOT NULL,
            registration_epoch INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE delivery_offers (
            driver_id TEXT NOT NULL REFERENCES watchtower_registrations(driver_id) ON DELETE CASCADE,
            registration_epoch INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            PRIMARY KEY(driver_id, registration_epoch, generation)
        );
        CREATE INDEX delivery_offers_active ON delivery_offers(driver_id,registration_epoch,confirmed);
        CREATE TABLE generation_membership_snapshots (
            generation INTEGER NOT NULL REFERENCES pending_generations(generation) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            PRIMARY KEY(generation, task_id)
        );
    """,
    6: """
        ALTER TABLE generation_task_snapshots ADD COLUMN compat_complete INTEGER NOT NULL DEFAULT 0 CHECK(compat_complete IN (0,1));
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

    def persist_session(
        self, event: Mapping[str, Any], durable_seq: int, state: LifecycleState, *, registered: bool
    ) -> None:
        identity = self._connection.execute(
            "SELECT harness,role,task_id,driver_id FROM sessions WHERE session_id=?",
            (event["session_id"],),
        ).fetchone()
        incoming = (event["harness"], event["role"], event.get("task_id"), event.get("driver_id"))
        if identity is not None and tuple(identity) != incoming:
            raise ValueError(f"session {event['session_id']!r} identity is immutable")
        self._connection.execute(
            """INSERT INTO sessions(
                   session_id,task_id,driver_id,harness,role,foreground,background,
                   background_count,availability,producer_seq,reducer_state_json,latest_durable_seq,registered
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                   foreground=excluded.foreground, background=excluded.background,
                   background_count=excluded.background_count,
                   availability=excluded.availability, producer_seq=excluded.producer_seq,
                   reducer_state_json=excluded.reducer_state_json,
                   latest_durable_seq=excluded.latest_durable_seq,
                   registered=MAX(sessions.registered,excluded.registered),
                   last_seen_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
            (
                event["session_id"], event.get("task_id"), event.get("driver_id"),
                event["harness"], event["role"], state.foreground, state.background,
                state.active_count, state.availability, state.producer_seq,
                _state_to_json(state), durable_seq, int(registered),
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
        updated = self._connection.execute(
            """UPDATE task_projections SET projection_generation=?, actionable_reason=?
               WHERE task_id=?""",
            (generation, change.reason, change.task_id),
        )
        if updated.rowcount != 1:
            raise ValueError(f"actionable task {change.task_id!r} has no projection")
        self._connection.execute(
            "INSERT INTO pending_generation_tasks(generation,task_id,actionable_reason) VALUES(?,?,?)",
            (generation, change.task_id, change.reason),
        )
        # Freeze both membership and every projection at this generation. Later
        # joins never consult mutable task rows, so N+1 cannot leak into N.
        self._connection.execute(
            "INSERT INTO generation_membership_snapshots(generation,task_id) SELECT ?,task_id FROM task_projections",
            (generation,),
        )
        self._connection.execute(
            """INSERT INTO generation_task_snapshots(
                   generation,task_id,availability,report_state,verdict,actionable_reason,
                   projection_generation,last_event_seq,projection_json,compat_complete)
               SELECT ?,task_id,availability,report_state,verdict,actionable_reason,
                      projection_generation,last_event_seq,projection_json,1
               FROM task_projections""",
            (generation,),
        )
        self._connection.execute(
            "UPDATE watchtower_deliveries SET latest_generation=?", (generation,)
        )
        return generation


def _report_projection(task_dir: Path) -> tuple[str, str | None, dict[str, Any]]:
    try:
        report = parse_task_report(task_dir)
    except Exception as exc:
        report = {
            "blocks": 0, "acked_through": 0, "unresolved": 0, "open_items": [],
            "latest": None, "protocol_errors": [f"unreadable handoff: {type(exc).__name__}"],
        }
    latest = report["latest"]
    state = "malformed" if report["protocol_errors"] else ("missing" if report["blocks"] == 0 else "valid")
    latest_verdict = (None if latest is None else latest["fields"].get("verdict", "").casefold() or None)
    verdict = latest_verdict
    if state != "valid":
        verdict = None
    elif report["open_items"]:
        # FIFO report authority: the earliest unacknowledged open verdict
        # survives a later done block, encoded using protocol v1's frozen tuple.
        open_verdict = report["open_items"][0].get("verdict", "").casefold()
        verdict = open_verdict if open_verdict in {"needs-action", "failed", "blocked"} else "needs-action"
    fields = {} if latest is None else latest.get("fields", {})
    summary = {
        "state": state,
        "verdict": verdict,
        "latest_verdict": latest_verdict,
        "blocks": report["blocks"],
        "acked_through": report["acked_through"],
        "acked_source": report.get("acked_source", "none"),
        "unresolved": report["unresolved"],
        "open_items": report["open_items"],
        "protocol_errors": report["protocol_errors"],
        "external_action": bool(report["open_items"]),
        "heading": "" if latest is None else latest.get("heading", ""),
        "reason": fields.get("reason", ""),
        "pending": fields.get("pending", ""),
        "inputs_needed": fields.get("inputs-needed", ""),
        "artifacts": fields.get("artifacts", ""),
    }
    return state, verdict, summary


def _actionable_reason(state: LifecycleState, report: Mapping[str, Any]) -> str:
    """Map projections exactly onto protocol v1's frozen report tuple matrix."""
    report_state = report.get("state")
    if report_state == "missing":
        return "missing-report"
    if report_state == "malformed":
        return "malformed-report"
    verdict = report.get("verdict")
    if state.availability == "gone":
        return "gone"
    if verdict == "done":
        return "quiescent" if state.availability == "quiescent" else "none"
    if verdict == "waiting":
        return "waiting-background" if state.availability == "waiting-background" else "unknown"
    if verdict == "needs-action":
        return "needs-action"
    if verdict == "failed":
        return "failed"
    if verdict == "blocked":
        return "blocked"
    raise ValueError("valid report has no protocol verdict")


def _reduce_projection(
    tx: StoreTransaction, event: Mapping[str, Any], durable_seq: int, tasks_dir: Path
) -> LifecycleState:
    state = tx.get_session_state(event["session_id"]) or LifecycleState()
    result = reduce_event(state, event)
    existing = tx._connection.execute(
        "SELECT registered FROM sessions WHERE session_id=?", (event["session_id"],)
    ).fetchone()
    registered = event["type"] == "session.register" or bool(existing and existing[0])
    tx.persist_session(event, durable_seq, result.state, registered=registered)
    task_id = event.get("task_id")
    if registered and event["role"] == "crew" and task_id:
        report_state, verdict, report = _report_projection(tasks_dir / task_id)
        projection = {
            "task_id": task_id,
            "folder_present": (tasks_dir / task_id).is_dir(),
            "session_id": event["session_id"],
            "foreground": result.state.foreground,
            "background": result.state.background,
            "background_count": result.state.active_count,
            "availability": result.state.availability,
            "report": report,
        }
        tx.upsert_task_projection(
            task_id, durable_seq, availability=result.state.availability,
            report_state=report_state, verdict=verdict,
            actionable_reason=_actionable_reason(result.state, report), projection=projection,
        )
    return result.state


class EventStore:
    """File-backed SQLite store under an owning-effective-UID trust boundary."""

    @staticmethod
    def _validate_entry(directory_fd: int, name: str, *, create: bool = False) -> None:
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        if create:
            flags |= os.O_CREAT
        fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise RuntimeError(f"unsafe SQLite state entry: {name}")
            os.fchmod(fd, 0o600)
            if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                raise RuntimeError(f"could not make SQLite state private: {name}")
        finally:
            os.close(fd)

    def __init__(self, path: str | os.PathLike[str], *, tasks_dir: str | os.PathLike[str] | None = None):
        self.path = Path(path).absolute()
        self.tasks_dir = Path(tasks_dir).absolute() if tasks_dir is not None else self.path.parent / "tasks"
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_fd = os.open(
            self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            directory_info = os.fstat(directory_fd)
            if directory_info.st_uid != os.geteuid():
                raise RuntimeError("SQLite directory must be owner-controlled")
            os.fchmod(directory_fd, 0o700)
            if stat.S_IMODE(os.fstat(directory_fd).st_mode) != 0o700:
                raise RuntimeError("could not make SQLite directory private")
            self._validate_entry(directory_fd, self.path.name, create=True)
            for suffix in ("-wal", "-shm"):
                try:
                    self._validate_entry(directory_fd, self.path.name + suffix)
                except FileNotFoundError:
                    pass

            self._lock = threading.RLock()
            self._connection = sqlite3.connect(
                self.path, isolation_level=None, check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA journal_mode=WAL")
            try:
                self._migrate()
                # SQLite may create sidecars while enabling WAL/migrating. Under
                # the accepted threat model the owning effective UID is trusted;
                # directly reject unsafe resulting entries and chmod only fds.
                for suffix in ("-wal", "-shm"):
                    try:
                        self._validate_entry(directory_fd, self.path.name + suffix)
                    except FileNotFoundError:
                        pass
            except BaseException:
                self._connection.close()
                raise
        finally:
            os.close(directory_fd)

    def _commit(self) -> None:
        """Commit seam kept explicit for fault-injection durability tests."""
        self._connection.commit()

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
            self._commit()
        except BaseException:
            # A failed COMMIT can leave SQLite's transaction active. Always
            # roll it back before exposing the exception so this sole daemon
            # connection remains reusable and no uncommitted row is visible.
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    @staticmethod
    def _validate_v2_upgrade(connection: sqlite3.Connection) -> None:
        """Reject v2 state whose missing immutable history cannot be invented."""
        invalid_owner = connection.execute(
            """SELECT session_id FROM sessions
               WHERE (role='crew' AND (task_id IS NULL OR driver_id IS NOT NULL))
                  OR (role='watchtower' AND (driver_id IS NULL OR task_id IS NOT NULL))
                  OR role NOT IN ('crew','watchtower')
               LIMIT 1"""
        ).fetchone()
        if invalid_owner is not None:
            raise RuntimeError(
                f"cannot upgrade schema 2: session {invalid_owner[0]!r} has invalid owner identity"
            )

        # v2 allowed an upsert to replace identity. Validate each event on its
        # own, establish one identity per session from history, then compare it
        # with the durable session anchor. Event-only histories are unsafe: v3
        # triggers protect sessions, not orphan event rows.
        session_anchors = {
            row["session_id"]: (row["harness"], row["role"], row["task_id"], row["driver_id"])
            for row in connection.execute(
                "SELECT session_id,harness,role,task_id,driver_id FROM sessions"
            )
        }
        historical: dict[str, tuple[Any, ...]] = {}
        for row in connection.execute(
            """SELECT event_id,session_id,task_id,driver_id,event_type,payload_json
               FROM events ORDER BY durable_seq"""
        ):
            try:
                payload = json.loads(row["payload_json"])
                if not isinstance(payload, dict):
                    raise TypeError("event payload is not an object")
                stored = (
                    row["event_id"], row["session_id"], row["task_id"],
                    row["driver_id"], row["event_type"],
                )
                embedded = (
                    payload["event_id"], payload["session_id"], payload.get("task_id"),
                    payload.get("driver_id"), payload["type"],
                )
                identity = (
                    payload["harness"], payload["role"],
                    payload.get("task_id"), payload.get("driver_id"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("cannot upgrade schema 2: malformed event identity history") from exc
            if embedded != stored:
                raise RuntimeError(
                    f"cannot upgrade schema 2: event {row['event_id']!r} payload identity disagrees with stored columns"
                )
            previous = historical.setdefault(row["session_id"], identity)
            if previous != identity:
                raise RuntimeError(
                    f"cannot upgrade schema 2: session {row['session_id']!r} has contradictory event identities"
                )

        for session_id, identity in historical.items():
            anchor = session_anchors.get(session_id)
            if anchor is None:
                raise RuntimeError(
                    f"cannot upgrade schema 2: session {session_id!r} has orphan event history without an identity anchor"
                )
            if identity != anchor:
                raise RuntimeError(
                    f"cannot upgrade schema 2: session {session_id!r} has contradictory identity history"
                )

        # v2 retained only each task's mutable latest projection. Once any
        # generation existed, an exact historical snapshot through N cannot be
        # proven, even when the latest row happens to carry N. This schema was
        # unreleased, so fail closed rather than manufacture reconciliation data.
        generated = connection.execute(
            """SELECT
                 (SELECT COUNT(*) FROM pending_generations) +
                 (SELECT COUNT(*) FROM pending_generation_tasks) +
                 (SELECT COUNT(*) FROM task_projections WHERE projection_generation<>0) +
                 (SELECT COUNT(*) FROM watchtower_deliveries
                    WHERE latest_generation<>0 OR delivered_generation<>0 OR acked_generation<>0) +
                 (SELECT CASE WHEN CAST(value AS INTEGER)<>0 THEN 1 ELSE 0 END
                    FROM daemon_metadata WHERE key='latest_generation')"""
        ).fetchone()[0]
        if generated:
            raise RuntimeError(
                "cannot upgrade schema 2 with generation state: immutable projection history is unavailable"
            )

    def _migrate(self) -> None:
        with self._lock, self._immediate() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"database schema {current} is newer than supported {SCHEMA_VERSION}")
            for version in range(current + 1, SCHEMA_VERSION + 1):
                if version == 3:
                    self._validate_v2_upgrade(connection)
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
                if version == 4:
                    self._replay_v3_projections(connection)
                if version == 5:
                    self._validate_v4_delivery_upgrade(connection)
                if version == 6:
                    self._validate_v5_compat_upgrade(connection)
                    connection.execute("UPDATE generation_task_snapshots SET compat_complete=1")
                connection.execute(f"PRAGMA user_version={version}")

    @staticmethod
    def _validate_v4_delivery_upgrade(connection: sqlite3.Connection) -> None:
        """Only empty v4 ledgers can migrate: v4 did not freeze full membership."""
        generated = connection.execute(
            """SELECT
                 (SELECT COUNT(*) FROM pending_generations) +
                 (SELECT COUNT(*) FROM pending_generation_tasks) +
                 (SELECT COUNT(*) FROM generation_task_snapshots) +
                 (SELECT COUNT(*) FROM task_projections WHERE projection_generation<>0) +
                 (SELECT COUNT(*) FROM watchtower_deliveries
                    WHERE latest_generation<>0 OR delivered_generation<>0 OR acked_generation<>0) +
                 (SELECT CASE WHEN CAST(value AS INTEGER)<>0 THEN 1 ELSE 0 END
                    FROM daemon_metadata WHERE key='latest_generation')"""
        ).fetchone()[0]
        if generated:
            raise RuntimeError(
                "cannot upgrade schema 4 with generation history: run `rozoro monitor reset --force`; task folders are preserved"
            )

    @staticmethod
    def _validate_v5_compat_upgrade(connection: sqlite3.Connection) -> None:
        """v5 snapshots omitted immutable compatibility details and cannot be backfilled losslessly."""
        generated = int(connection.execute(
            """SELECT
                 (SELECT COUNT(*) FROM generation_task_snapshots) +
                 (SELECT COUNT(*) FROM pending_generations) +
                 (SELECT COUNT(*) FROM pending_generation_tasks) +
                 (SELECT COUNT(*) FROM watchtower_deliveries
                    WHERE latest_generation<>0 OR delivered_generation<>0 OR acked_generation<>0) +
                 (SELECT CASE WHEN CAST(value AS INTEGER)<>0 THEN 1 ELSE 0 END
                    FROM daemon_metadata WHERE key='latest_generation')"""
        ).fetchone()[0])
        if generated:
            raise RuntimeError(
                "cannot upgrade schema 5 with generation snapshots lacking immutable report fields: "
                "run `rozoro monitor reset --force`; task folders are preserved"
            )

    def _replay_v3_projections(self, connection: sqlite3.Connection) -> None:
        """Validate v3 history, then derive registration and projections from it."""
        anchors = {
            row["session_id"]: (row["harness"], row["role"], row["task_id"], row["driver_id"])
            for row in connection.execute(
                "SELECT session_id,harness,role,task_id,driver_id FROM sessions"
            )
        }
        identities: dict[str, tuple[Any, ...]] = {}
        decoded: list[tuple[int, dict[str, Any]]] = []
        for row in connection.execute(
            """SELECT durable_seq,event_id,session_id,task_id,driver_id,event_type,payload_json
               FROM events ORDER BY durable_seq"""
        ):
            try:
                event = json.loads(row["payload_json"])
                if not isinstance(event, dict):
                    raise TypeError
                stored = (row["event_id"], row["session_id"], row["task_id"],
                          row["driver_id"], row["event_type"])
                embedded = (event["event_id"], event["session_id"], event.get("task_id"),
                            event.get("driver_id"), event["type"])
                identity = (event["harness"], event["role"], event.get("task_id"),
                            event.get("driver_id"))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RuntimeError("cannot upgrade schema 3: malformed event identity history") from exc
            if stored != embedded:
                raise RuntimeError("cannot upgrade schema 3: event payload identity disagrees with stored columns")
            previous = identities.setdefault(event["session_id"], identity)
            if previous != identity:
                raise RuntimeError("cannot upgrade schema 3: contradictory session identity history")
            decoded.append((int(row["durable_seq"]), event))
        for session_id, identity in identities.items():
            if anchors.get(session_id) != identity:
                raise RuntimeError("cannot upgrade schema 3: event identity disagrees with session anchor")
        if connection.execute("SELECT COUNT(*) FROM generation_task_snapshots").fetchone()[0]:
            raise RuntimeError("cannot upgrade schema 3 with generated projection snapshots")
        connection.execute("DELETE FROM task_projections")
        connection.execute("DELETE FROM sessions")
        tx = StoreTransaction(connection)
        for durable_seq, event in decoded:
            _reduce_projection(tx, event, durable_seq, self.tasks_dir)

    @property
    def schema_version(self) -> int:
        with self._lock:
            return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    def accept_event(
        self, event: Mapping[str, Any], *, reducer: ReducerHook | None | object = _DEFAULT_REDUCER,
        actionable: ActionableHook | None = None,
    ) -> AcceptedEvent:
        """Durably accept once; duplicates never invoke either hook."""
        payload = json.dumps(dict(event), sort_keys=True, separators=(",", ":"))
        with self._lock, self._immediate() as connection:
            duplicate = connection.execute(
                "SELECT durable_seq,payload_json FROM events WHERE event_id=?", (event["event_id"],)
            ).fetchone()
            if duplicate is not None:
                if duplicate["payload_json"] != payload:
                    raise ValueError(f"event_id {event['event_id']!r} conflicts with its durable envelope")
                return AcceptedEvent(int(duplicate["durable_seq"]), True)
            cursor = connection.execute(
                """INSERT INTO events(event_id,session_id,task_id,driver_id,event_type,payload_json)
                   VALUES(?,?,?,?,?,?)""",
                (event["event_id"], event["session_id"], event.get("task_id"),
                 event.get("driver_id"), event["type"], payload),
            )
            durable_seq = int(cursor.lastrowid)
            tx = StoreTransaction(connection)
            before_projection = None
            if reducer is _DEFAULT_REDUCER and event.get("task_id"):
                before_projection = connection.execute(
                    "SELECT availability,report_state,verdict,actionable_reason,projection_json FROM task_projections WHERE task_id=?",
                    (event["task_id"],),
                ).fetchone()
            if reducer is _DEFAULT_REDUCER:
                reduced = _reduce_projection(tx, event, durable_seq, self.tasks_dir)
            else:
                reduced = reducer(tx, event, durable_seq) if reducer is not None else None
            if actionable is not None:
                change = actionable(tx, event, durable_seq, reduced)
            elif reducer is _DEFAULT_REDUCER and event.get("task_id"):
                after_projection = connection.execute(
                    "SELECT availability,report_state,verdict,actionable_reason,projection_json FROM task_projections WHERE task_id=?",
                    (event["task_id"],),
                ).fetchone()
                before_tuple = None if before_projection is None else tuple(before_projection)
                after_tuple = None if after_projection is None else tuple(after_projection)
                reason = None if after_projection is None else after_projection["actionable_reason"]
                change = (ActionableChange(
                              event["task_id"], reason,
                              "urgent" if reason in {"blocked", "failed", "needs-action"} else "normal",
                          )
                          if reason is not None and reason != "none"
                          and before_tuple != after_tuple else None)
            else:
                change = None
            generation = tx.bump_actionable(change) if change is not None else None
            return AcceptedEvent(durable_seq, False, generation)

    def rebuild_projections(self) -> None:
        """Deterministically reconstruct mutable projections from the accepted event log."""
        with self._lock, self._immediate() as connection:
            generated = connection.execute(
                "SELECT COUNT(*) FROM generation_task_snapshots"
            ).fetchone()[0]
            if generated:
                raise RuntimeError("projection rebuild requires delivery-ledger replay support")
            connection.execute("DELETE FROM task_projections")
            connection.execute("DELETE FROM sessions")
            tx = StoreTransaction(connection)
            for row in connection.execute(
                "SELECT durable_seq,payload_json FROM events ORDER BY durable_seq"
            ).fetchall():
                _reduce_projection(tx, json.loads(row["payload_json"]), int(row["durable_seq"]), self.tasks_dir)

    def task_projection(self, task_id: str) -> dict[str, Any] | None:
        """Return a normalized projection without exposing SQLite row mechanics."""
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM task_projections WHERE task_id=?", (task_id,)
            ).fetchone()
            return None if row is None else dict(row)

    def driver_snapshot(self, driver_id: str) -> dict[str, int]:
        """Return one driver's exact generation cursors for CLI reconciliation."""
        with self._lock:
            row = self._connection.execute(
                "SELECT latest_generation,delivered_generation,acked_generation FROM watchtower_deliveries WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            if row is None:
                return {"generation": 0, "delivered_generation": 0, "acked_generation": 0}
            return {"generation": int(row[0]), "delivered_generation": int(row[1]), "acked_generation": int(row[2])}

    def health_snapshot(self) -> dict[str, Any]:
        """Return a consistent, read-only diagnostic snapshot."""
        with self._lock:
            event = self._connection.execute(
                "SELECT durable_seq,received_at FROM events ORDER BY durable_seq DESC LIMIT 1"
            ).fetchone()
            delivery = self._connection.execute(
                """SELECT COALESCE(MAX(latest_generation),0),
                          COALESCE(MAX(delivered_generation),0),
                          COALESCE(MAX(acked_generation),0)
                   FROM watchtower_deliveries"""
            ).fetchone()
            generation = int(self._connection.execute(
                "SELECT value FROM daemon_metadata WHERE key='latest_generation'"
            ).fetchone()[0])
            return {
                "schema_version": self.schema_version,
                "last_durable_seq": 0 if event is None else int(event[0]),
                "last_durable_time": None if event is None else event[1],
                "task_count": int(self._connection.execute(
                    "SELECT COUNT(DISTINCT task_id) FROM sessions WHERE task_id IS NOT NULL"
                ).fetchone()[0]),
                "driver_count": int(self._connection.execute(
                    "SELECT COUNT(DISTINCT driver_id) FROM sessions WHERE driver_id IS NOT NULL"
                ).fetchone()[0]),
                "generation": generation,
                "delivered_generation": int(delivery[1]),
                "acked_generation": int(delivery[2]),
                "pending_count": int(self._connection.execute(
                    "SELECT COUNT(DISTINCT task_id) FROM pending_generation_tasks"
                ).fetchone()[0]),
            }

    def register_driver(self, driver_id: str, session_id: str, harness: str) -> dict[str, Any]:
        """Bind a new connection epoch, including for same-session reconnects."""
        with self._lock, self._immediate() as connection:
            current = connection.execute(
                "SELECT harness,registration_epoch FROM watchtower_registrations WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            if current is None:
                epoch = 1
                connection.execute(
                    "INSERT INTO watchtower_registrations(driver_id,session_id,harness,registration_epoch) VALUES(?,?,?,?)",
                    (driver_id, session_id, harness, epoch),
                )
                latest = int(connection.execute(
                    "SELECT value FROM daemon_metadata WHERE key='latest_generation'"
                ).fetchone()[0])
                connection.execute(
                    "INSERT INTO watchtower_deliveries(driver_id,latest_generation) VALUES(?,?)",
                    (driver_id, latest),
                )
            else:
                if current["harness"] != harness:
                    raise ValueError("driver harness is immutable")
                epoch = int(current["registration_epoch"]) + 1
                connection.execute(
                    "UPDATE watchtower_registrations SET session_id=?,registration_epoch=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE driver_id=?",
                    (session_id, epoch, driver_id),
                )
            return {"driver_id": driver_id, "session_id": session_id, "epoch": epoch}

    @staticmethod
    def _require_registration(connection: sqlite3.Connection, driver_id: str,
                              session_id: str, epoch: int) -> None:
        row = connection.execute(
            "SELECT session_id,registration_epoch FROM watchtower_registrations WHERE driver_id=?",
            (driver_id,),
        ).fetchone()
        if row is None or row["session_id"] != session_id or int(row["registration_epoch"]) != epoch:
            raise ValueError("stale or mismatched driver connection epoch")

    def notification_frontier(self, driver_id: str, session_id: str,
                              epoch: int) -> tuple[int, str, bool] | None:
        """Return pending generation, aggregate priority, and immediate-retry flag.

        This read does not create an offer or mutate delivery state.  Urgency is
        aggregated across the whole unacknowledged range rather than inferred
        only from its highest generation.
        """
        with self._lock:
            self._require_registration(self._connection, driver_id, session_id, epoch)
            ledger = self._connection.execute(
                "SELECT latest_generation,delivered_generation,acked_generation FROM watchtower_deliveries WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            g, d, a = map(int, ledger)
            offer = self._connection.execute(
                """SELECT generation FROM delivery_offers
                   WHERE driver_id=? AND registration_epoch=? AND session_id=? AND confirmed=0
                     AND generation>? ORDER BY generation LIMIT 1""",
                (driver_id, epoch, session_id, a),
            ).fetchone()
            if offer is not None:
                generation = int(offer[0])
                immediate = True
            elif g <= a:
                return None
            elif d > a:
                confirmed_here = self._connection.execute(
                    """SELECT 1 FROM delivery_offers WHERE driver_id=? AND registration_epoch=?
                       AND session_id=? AND generation=? AND confirmed=1""",
                    (driver_id, epoch, session_id, d),
                ).fetchone()
                if confirmed_here is not None:
                    return None
                generation = d
                immediate = True
            else:
                generation = g
                immediate = False
            urgent = self._connection.execute(
                """SELECT 1 FROM pending_generations
                   WHERE generation>? AND generation<=? AND priority='urgent' LIMIT 1""",
                (a, generation),
            ).fetchone()
            return generation, "urgent" if urgent is not None else "normal", immediate

    def offer_notification(self, driver_id: str, session_id: str, epoch: int) -> dict[str, Any] | None:
        """Return one exact offer until confirmation or registration invalidation."""
        with self._lock, self._immediate() as connection:
            self._require_registration(connection, driver_id, session_id, epoch)
            existing = connection.execute(
                """SELECT generation FROM delivery_offers
                   WHERE driver_id=? AND registration_epoch=? AND session_id=?
                     AND confirmed=0 AND generation>(
                         SELECT acked_generation FROM watchtower_deliveries WHERE driver_id=?)
                   ORDER BY generation LIMIT 1""",
                (driver_id, epoch, session_id, driver_id),
            ).fetchone()
            ledger = connection.execute(
                "SELECT latest_generation,delivered_generation,acked_generation FROM watchtower_deliveries WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            g, d, a = map(int, ledger)
            if existing is not None:
                generation = int(existing[0])
            elif g <= a:
                return None
            elif d > a:
                # The current connection already consumed its one normal wake.
                # Only a fresh registration epoch may redeliver delivered-but-
                # unacked N; N+1 remains pending until N is acknowledged.
                confirmed_here = connection.execute(
                    """SELECT 1 FROM delivery_offers
                       WHERE driver_id=? AND registration_epoch=? AND session_id=?
                         AND generation=? AND confirmed=1""",
                    (driver_id, epoch, session_id, d),
                ).fetchone()
                if confirmed_here is not None:
                    return None
                generation = d
                connection.execute(
                    "INSERT INTO delivery_offers(driver_id,registration_epoch,session_id,generation) VALUES(?,?,?,?)",
                    (driver_id, epoch, session_id, generation),
                )
            else:
                generation = g
                connection.execute(
                    "INSERT INTO delivery_offers(driver_id,registration_epoch,session_id,generation) VALUES(?,?,?,?)",
                    (driver_id, epoch, session_id, generation),
                )
            priority = connection.execute(
                """SELECT 1 FROM pending_generations
                   WHERE generation>? AND generation<=? AND priority='urgent' LIMIT 1""",
                (a, generation),
            ).fetchone()
            count = connection.execute(
                "SELECT COUNT(DISTINCT task_id) FROM pending_generation_tasks WHERE generation<=? AND generation>?",
                (generation, a),
            ).fetchone()[0]
            return {"generation": generation, "priority": "urgent" if priority else "normal",
                    "task_count": int(count)}

    def withdraw_unconfirmed_offer(self, driver_id: str, session_id: str, epoch: int,
                                   generation: int) -> None:
        """Withdraw only this epoch/session's exact unconfirmed offer.

        Used when selection advances beyond the frontier whose coalescer
        eligibility was claimed. Confirmed or mismatched offers fail closed.
        """
        with self._lock, self._immediate() as connection:
            self._require_registration(connection, driver_id, session_id, epoch)
            deleted = connection.execute(
                """DELETE FROM delivery_offers WHERE driver_id=? AND registration_epoch=?
                   AND session_id=? AND generation=? AND confirmed=0""",
                (driver_id, epoch, session_id, generation),
            )
            if deleted.rowcount != 1:
                raise ValueError("generation does not match the exact unconfirmed offer")

    def record_delivery_outcome(self, driver_id: str, session_id: str, epoch: int,
                                generation: int, state: str, error: str | None = None) -> None:
        """Record deferred/error diagnostics without consuming the exact offer."""
        if state not in {"deferred", "error"}:
            raise ValueError("non-delivery state must be deferred or error")
        with self._lock, self._immediate() as connection:
            self._require_registration(connection, driver_id, session_id, epoch)
            offer = connection.execute(
                """SELECT 1 FROM delivery_offers WHERE driver_id=? AND registration_epoch=?
                   AND session_id=? AND generation=? AND confirmed=0""",
                (driver_id, epoch, session_id, generation),
            ).fetchone()
            if offer is None:
                # Concurrent reconciliation may ACK and retire this exact
                # in-flight offer before a deferred/error actuator returns.
                consumed = connection.execute(
                    """SELECT 1 FROM delivery_offers o JOIN watchtower_deliveries w
                         ON w.driver_id=o.driver_id
                       WHERE o.driver_id=? AND o.registration_epoch=? AND o.session_id=?
                         AND o.generation=? AND o.confirmed=1 AND w.acked_generation>=?""",
                    (driver_id, epoch, session_id, generation, generation),
                ).fetchone()
                if consumed is not None:
                    return
                raise ValueError("generation does not match the exact outstanding offer")
            connection.execute(
                """UPDATE watchtower_deliveries SET delivery_state=?,last_error=?,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE driver_id=?""",
                (state, None if error is None else error[:128], driver_id),
            )

    def confirm_delivery(self, driver_id: str, session_id: str, epoch: int, generation: int) -> bool:
        """Confirm only the current epoch's exact outstanding offer."""
        with self._lock, self._immediate() as connection:
            self._require_registration(connection, driver_id, session_id, epoch)
            offer = connection.execute(
                """SELECT generation,confirmed FROM delivery_offers
                   WHERE driver_id=? AND registration_epoch=? AND session_id=?
                   ORDER BY generation DESC LIMIT 1""",
                (driver_id, epoch, session_id),
            ).fetchone()
            if offer is None or int(offer["generation"]) != generation:
                raise ValueError("generation does not match the exact outstanding offer")
            if offer["confirmed"]:
                return False
            connection.execute(
                "UPDATE delivery_offers SET confirmed=1 WHERE driver_id=? AND registration_epoch=? AND generation=?",
                (driver_id, epoch, generation),
            )
            connection.execute(
                "UPDATE watchtower_deliveries SET delivered_generation=MAX(delivered_generation,?),delivery_state='delivered',last_error=NULL,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE driver_id=?",
                (generation, driver_id),
            )
            return True

    def _snapshot_rows(self, connection: sqlite3.Connection, through: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            """SELECT s.* FROM generation_task_snapshots s
               JOIN (SELECT task_id,MAX(generation) generation FROM generation_task_snapshots
                     WHERE generation<=? GROUP BY task_id) latest
                 ON latest.task_id=s.task_id AND latest.generation=s.generation
               ORDER BY s.generation,s.task_id""", (through,)
        ).fetchall()
        if any(not int(row["compat_complete"]) for row in rows):
            raise RuntimeError("generation snapshot lacks immutable compatibility fields")
        return [{"task_id": row["task_id"], "generation": int(row["generation"]),
                 "availability": row["availability"], "report_state": row["report_state"],
                 "verdict": row["verdict"], "actionable_reason": row["actionable_reason"],
                 "projection": json.loads(row["projection_json"])} for row in rows]

    def reconcile(self, driver_id: str, session_id: str, epoch: int,
                  through: int) -> list[dict[str, Any]]:
        """Return the authoritative immutable per-task snapshot through N; never deliver or ACK."""
        with self._lock:
            self._require_registration(self._connection, driver_id, session_id, epoch)
            ledger = self._connection.execute(
                "SELECT latest_generation FROM watchtower_deliveries WHERE driver_id=?", (driver_id,)
            ).fetchone()
            if ledger is None or through > ledger[0]:
                raise ValueError("unavailable generation")
            return self._snapshot_rows(self._connection, through)

    def reconcile_delivered(self, driver_id: str) -> tuple[int, list[dict[str, Any]]]:
        """Consume only the exact confirmed delivered-but-unacked offer, without changing cursors."""
        with self._lock, self._immediate() as connection:
            ledger = connection.execute(
                "SELECT delivered_generation,acked_generation FROM watchtower_deliveries WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            registration = connection.execute(
                "SELECT registration_epoch FROM watchtower_registrations WHERE driver_id=?", (driver_id,)
            ).fetchone()
            if ledger is None or registration is None:
                raise ValueError("unknown driver")
            delivered, acked = map(int, ledger)
            if delivered <= acked:
                return acked, []
            confirmed = connection.execute(
                "SELECT 1 FROM delivery_offers WHERE driver_id=? AND generation=? AND confirmed=1",
                (driver_id, delivered),
            ).fetchone()
            if confirmed is None:
                raise ValueError("delivered cursor has no exact confirmed offer")
            # Prior registration epochs are invalidated by definition. An
            # unconfirmed redelivery of the already-confirmed exact d is also a
            # duplicate, not an older semantic delivery. Retire only those rows.
            connection.execute(
                """UPDATE delivery_offers SET confirmed=1
                   WHERE driver_id=? AND confirmed=0
                     AND (registration_epoch<? OR generation=?)""",
                (driver_id, int(registration[0]), delivered),
            )
            older = connection.execute(
                "SELECT 1 FROM delivery_offers WHERE driver_id=? AND generation<? AND confirmed=0 LIMIT 1",
                (driver_id, delivered),
            ).fetchone()
            if older is not None:
                raise ValueError("an older valid delivery offer remains unconfirmed")
            return delivered, self._snapshot_rows(connection, delivered)

    def ack_delivered(self, driver_id: str, through: int) -> bool:
        """ACK an exact confirmed delivered cursor without registering or retiring offers."""
        with self._lock, self._immediate() as connection:
            ledger = connection.execute(
                "SELECT delivered_generation,acked_generation FROM watchtower_deliveries WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            if ledger is None:
                raise ValueError("unknown driver")
            delivered, acked = map(int, ledger)
            if through == acked:
                return False
            if through != delivered or through < acked:
                raise ValueError("ack must equal the exact delivered cursor")
            unconfirmed = connection.execute(
                "SELECT 1 FROM delivery_offers WHERE driver_id=? AND generation<=? AND confirmed=0 LIMIT 1",
                (driver_id, through),
            ).fetchone()
            if unconfirmed is not None:
                raise ValueError("cannot retire an unconfirmed delivery offer")
            connection.execute(
                "UPDATE watchtower_deliveries SET acked_generation=?,delivery_state='pending',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE driver_id=?",
                (through, driver_id),
            )
            return True

    def ack_generation(self, driver_id: str, session_id: str, epoch: int, through: int) -> bool:
        """Advance ACK to exactly a delivered, consumed generation; never consume N+1."""
        with self._lock, self._immediate() as connection:
            self._require_registration(connection, driver_id, session_id, epoch)
            ledger = connection.execute(
                "SELECT delivered_generation,acked_generation FROM watchtower_deliveries WHERE driver_id=?",
                (driver_id,),
            ).fetchone()
            delivered, acked = map(int, ledger)
            if through < acked:
                raise ValueError("stale acknowledgement")
            if through == acked:
                return False
            if through > delivered:
                raise ValueError("cannot acknowledge an undelivered generation")
            connection.execute(
                "UPDATE watchtower_deliveries SET acked_generation=?,delivery_state='pending',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE driver_id=?",
                (through, driver_id),
            )
            # Adapter ACKs may race a reconnect redelivery; preserve the phase-2
            # registration contract here. The CLI uses ack_delivered(), which
            # rejects rather than retires any unconfirmed offer.
            connection.execute(
                "UPDATE delivery_offers SET confirmed=1 WHERE driver_id=? AND generation<=?",
                (driver_id, through),
            )
            return True

    def projection_snapshots_through(self, through: int) -> list[sqlite3.Row]:
        """Return immutable actionable projection history through a generation."""
        with self._lock:
            return list(self._connection.execute(
                """SELECT * FROM generation_task_snapshots
                   WHERE generation<=? ORDER BY generation,task_id""",
                (through,),
            ))

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
