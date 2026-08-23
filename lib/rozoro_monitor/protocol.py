"""Strict, transport-independent validation for Rozoro protocol v1.

The protocol uses one JSON object per NDJSON frame.  This module deliberately
contains no socket, persistence, reducer, or adapter behavior.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

VERSION = 1
# Integers cross Python, Node, JSON, and SQLite boundaries.  The JavaScript
# safe-integer limit is the narrowest exact range.
MAX_INTEGER = 9_007_199_254_740_991
# The limit covers the complete UTF-8 NDJSON frame, including its trailing
# newline when present. encode() always emits and counts that newline; decode()
# counts exactly the bytes supplied by the transport.
MAX_FRAME_BYTES = 1_048_576

# IDs are opaque but deliberately safe to use in logs and (for event_id) spool
# filenames. Whitespace, path separators, and control characters are excluded.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")


@dataclass(frozen=True)
class ProtocolError(ValueError):
    code: str
    message: str
    field: str | None = None

    def __str__(self) -> str:
        return self.message


def _fail(code: str, message: str, field: str | None = None) -> None:
    raise ProtocolError(code, message, field)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _id(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        _fail("invalid-field", f"{field} must be a safe non-empty identifier", field)


def _string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 128:
        _fail("invalid-field", f"{field} must be a non-empty string of at most 128 characters", field)


def _positive(value: Any, field: str) -> None:
    if not _is_int(value) or not 1 <= value <= MAX_INTEGER:
        _fail("invalid-field", f"{field} must be an integer from 1 through {MAX_INTEGER}", field)


def _nonnegative(value: Any, field: str) -> None:
    if not _is_int(value) or not 0 <= value <= MAX_INTEGER:
        _fail("invalid-field", f"{field} must be an integer from 0 through {MAX_INTEGER}", field)


def _boolean(value: Any, field: str) -> None:
    if not isinstance(value, bool):
        _fail("invalid-field", f"{field} must be a boolean", field)


def _known_or_unknown_boolean(value: Any, field: str) -> None:
    if value is not None and not isinstance(value, bool):
        _fail("invalid-field", f"{field} must be true, false, or null (unknown)", field)


def _enum(*values: str) -> Callable[[Any, str], None]:
    allowed = frozenset(values)

    def check(value: Any, field: str) -> None:
        # Check the type first: lists and objects are unhashable and must still
        # take the deterministic ProtocolError path.
        if not isinstance(value, str) or value not in allowed:
            _fail("invalid-field", f"{field} must be one of {sorted(allowed)}", field)

    return check


def _nullable(check: Callable[[Any, str], None]) -> Callable[[Any, str], None]:
    def nullable_check(value: Any, field: str) -> None:
        if value is not None:
            check(value, field)

    return nullable_check


_ID = _id
_POSITIVE = _positive
_NONNEGATIVE = _nonnegative
_BOOL = _boolean
_STRING = _string
_HARNESS = _enum("claude", "pi", "codex", "copilot")
_ROLE = _enum("crew", "watchtower")
_PRIORITY = _enum("normal", "urgent")
_RESULT = _enum("success", "failed", "cancelled", "unknown")
_AVAILABILITY = _enum("busy", "waiting-background", "quiescent", "blocked", "gone", "unknown")
_VERDICT = _enum("done", "waiting", "needs-action", "failed", "blocked")
_REPORT_STATE = _enum("missing", "malformed", "valid")
_ACTIONABLE_REASON = _enum(
    "none", "quiescent", "missing-report", "malformed-report", "waiting-background",
    "blocked", "failed", "needs-action", "gone", "unknown",
)
_REPORT_TUPLES = frozenset({
    ("missing", None, "missing-report"),
    ("malformed", None, "malformed-report"),
    ("valid", "done", "none"),
    ("valid", "done", "quiescent"),
    ("valid", "done", "gone"),
    ("valid", "waiting", "waiting-background"),
    ("valid", "waiting", "unknown"),
    ("valid", "waiting", "gone"),
    ("valid", "needs-action", "needs-action"),
    ("valid", "needs-action", "gone"),
    ("valid", "failed", "failed"),
    ("valid", "failed", "gone"),
    ("valid", "blocked", "blocked"),
    ("valid", "blocked", "gone"),
})

# type -> (required fields, optional fields). Unknown fields are rejected so a
# misspelling cannot silently weaken lifecycle or generation semantics.
_SCHEMAS: dict[str, tuple[dict[str, Callable[[Any, str], None]], dict[str, Callable[[Any, str], None]]]] = {
    "session.register": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE}, {"task_id": _ID, "driver_id": _ID}),
    "turn.start": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "turn_id": _ID}, {"task_id": _ID, "driver_id": _ID}),
    "background.start": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "job_id": _ID, "job_kind": _STRING}, {"task_id": _ID, "driver_id": _ID}),
    "background.stop": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "job_id": _ID, "result": _RESULT}, {"task_id": _ID, "driver_id": _ID}),
    "background.snapshot": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "active_count": _NONNEGATIVE}, {"task_id": _ID, "driver_id": _ID}),
    "turn.stop": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "background_active": _known_or_unknown_boolean}, {"task_id": _ID, "driver_id": _ID, "turn_id": _ID}),
    "session.end": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE}, {"task_id": _ID, "driver_id": _ID}),
    "health": ({"request_id": _ID}, {}),
    "health.result": ({"request_id": _ID, "schema_version": _POSITIVE, "clients": _NONNEGATIVE}, {}),
    "watchtower.register": ({"request_id": _ID, "session_id": _ID, "harness": _HARNESS, "driver_id": _ID}, {}),
    "notification": ({"generation": _POSITIVE, "priority": _PRIORITY, "task_count": _NONNEGATIVE}, {}),
    "notification.delivered": ({"request_id": _ID, "driver_id": _ID, "generation": _POSITIVE}, {}),
    "reconcile": ({"request_id": _ID, "driver_id": _ID, "through": _POSITIVE}, {}),
    "reconcile.result": ({"request_id": _ID, "through": _POSITIVE, "reports": lambda value, field: _reports(value, field)}, {}),
    "ack-generation": ({"request_id": _ID, "driver_id": _ID, "through": _POSITIVE}, {}),
    "ok": ({"request_id": _ID}, {}),
    "ack": ({"event_id": _ID, "durable_seq": _POSITIVE}, {}),
    # frame.error is the complete no-safe-correlation path.  It intentionally
    # supports every validation/framing code and carries no invented ID.
    "frame.error": ({"code": _enum("invalid-json", "frame-too-large", "invalid-message", "invalid-version", "invalid-event", "invalid-field", "unsupported-type")}, {}),
    "event.error": ({"event_id": _ID, "code": _enum("invalid-event", "invalid-field", "unsupported-type")}, {}),
    "request.error": ({"request_id": _ID, "code": _enum("invalid-message", "invalid-field", "unsupported-type")}, {}),
}


def requires_producer_seq(message_type: str) -> bool:
    """Return whether *message_type*'s schema declares a producer_seq field."""
    schema = _SCHEMAS.get(message_type)
    return schema is not None and "producer_seq" in schema[0]


_REPORT_SCHEMA: dict[str, Callable[[Any, str], None]] = {
    "task_id": _ID,
    "generation": _POSITIVE,
    "availability": _AVAILABILITY,
    "report_state": _REPORT_STATE,
    "verdict": _nullable(_VERDICT),
    "actionable_reason": _ACTIONABLE_REASON,
}


def _reports(value: Any, field: str) -> None:
    if not isinstance(value, list):
        _fail("invalid-field", f"{field} must be an array", field)
    for index, report in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(report, dict):
            _fail("invalid-field", f"{item_field} must be an object", item_field)
        missing = sorted(set(_REPORT_SCHEMA) - set(report))
        unknown = sorted(set(report) - set(_REPORT_SCHEMA))
        if missing:
            _fail("invalid-field", f"{item_field} missing field(s): {', '.join(missing)}", item_field)
        if unknown:
            _fail("invalid-field", f"{item_field} has unknown field(s): {', '.join(unknown)}", item_field)
        for name, check in _REPORT_SCHEMA.items():
            check(report[name], f"{item_field}.{name}")
        report_tuple = (report["report_state"], report["verdict"], report["actionable_reason"])
        if report_tuple not in _REPORT_TUPLES:
            _fail(
                "invalid-field",
                f"{item_field} has contradictory report state, verdict, and actionable reason",
                item_field,
            )


def validate(message: Any) -> dict[str, Any]:
    """Validate and return *message* unchanged, or raise :class:`ProtocolError`."""
    if not isinstance(message, dict):
        _fail("invalid-message", "protocol message must be a JSON object")
    if "v" not in message:
        _fail("invalid-version", "protocol version v is required", "v")
    if not _is_int(message["v"]) or message["v"] != VERSION:
        _fail("invalid-version", f"unsupported protocol version {message['v']!r}", "v")
    message_type = message.get("type")
    if not isinstance(message_type, str):
        _fail("invalid-message", "message type is required", "type")
    if message_type not in _SCHEMAS:
        _fail("unsupported-type", f"unsupported message type {message_type!r}", "type")

    required, optional = _SCHEMAS[message_type]
    allowed = {"v", "type", *required, *optional}
    unknown = sorted(set(message) - allowed)
    if unknown:
        _fail("invalid-field", f"unknown field(s): {', '.join(unknown)}", unknown[0])
    missing = sorted(set(required) - set(message))
    if missing:
        _fail("invalid-event" if "event_id" in required else "invalid-message", f"missing required field(s): {', '.join(missing)}", missing[0])
    for field, check in {**required, **optional}.items():
        if field in message:
            check(message[field], field)

    if message_type in {"session.register", "turn.start", "background.start", "background.stop", "background.snapshot", "turn.stop", "session.end"}:
        identity = "task_id" if message["role"] == "crew" else "driver_id"
        other = "driver_id" if identity == "task_id" else "task_id"
        if identity not in message or other in message:
            _fail("invalid-event", f"role {message['role']!r} requires {identity} and forbids {other}", identity)
    if message_type == "reconcile.result":
        seen_tasks: set[str] = set()
        for index, report in enumerate(message["reports"]):
            if report["generation"] > message["through"]:
                _fail(
                    "invalid-field",
                    f"reports[{index}].generation exceeds reconcile through cursor",
                    f"reports[{index}].generation",
                )
            if report["task_id"] in seen_tasks:
                _fail(
                    "invalid-field",
                    f"duplicate task_id {report['task_id']!r} in reconcile snapshot",
                    f"reports[{index}].task_id",
                )
            seen_tasks.add(report["task_id"])
    return message


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object member {key!r}")
        result[key] = value
    return result


def _frame_size(frame: str | bytes) -> int:
    if isinstance(frame, bytes):
        return len(frame)
    try:
        return len(frame.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ProtocolError("invalid-json", "frame is not valid UTF-8 JSON") from exc


def decode(line: str | bytes) -> dict[str, Any]:
    """Decode one bounded JSON frame and validate it."""
    if _frame_size(line) > MAX_FRAME_BYTES:
        _fail("frame-too-large", f"frame exceeds {MAX_FRAME_BYTES} bytes including newline")
    try:
        message = json.loads(
            line,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError("invalid-json", "frame is not valid finite JSON") from exc
    return validate(message)


def encode(message: Any) -> str:
    """Validate and encode one canonical, newline-terminated NDJSON frame."""
    validate(message)
    frame = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    if _frame_size(frame) > MAX_FRAME_BYTES:
        _fail("frame-too-large", f"encoded frame exceeds {MAX_FRAME_BYTES} bytes including newline")
    return frame
