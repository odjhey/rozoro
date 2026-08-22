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
    if not _is_int(value) or value < 1:
        _fail("invalid-field", f"{field} must be a positive integer", field)


def _nonnegative(value: Any, field: str) -> None:
    if not _is_int(value) or value < 0:
        _fail("invalid-field", f"{field} must be a non-negative integer", field)


def _boolean(value: Any, field: str) -> None:
    if not isinstance(value, bool):
        _fail("invalid-field", f"{field} must be a boolean", field)


def _enum(*values: str) -> Callable[[Any, str], None]:
    allowed = frozenset(values)

    def check(value: Any, field: str) -> None:
        if value not in allowed or not isinstance(value, str):
            _fail("invalid-field", f"{field} must be one of {sorted(allowed)}", field)

    return check


_ID = _id
_POSITIVE = _positive
_NONNEGATIVE = _nonnegative
_BOOL = _boolean
_STRING = _string
_HARNESS = _enum("claude", "pi", "codex", "copilot")
_ROLE = _enum("crew", "watchtower")
_PRIORITY = _enum("normal", "urgent")
_RESULT = _enum("success", "failed", "cancelled", "unknown")

# type -> (required fields, optional fields). Unknown fields are rejected so a
# misspelling cannot silently weaken lifecycle or generation semantics.
_SCHEMAS: dict[str, tuple[dict[str, Callable[[Any, str], None]], dict[str, Callable[[Any, str], None]]]] = {
    "session.register": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE}, {"task_id": _ID, "driver_id": _ID}),
    "turn.start": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "turn_id": _ID}, {"task_id": _ID, "driver_id": _ID}),
    "background.start": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "job_id": _ID, "job_kind": _STRING}, {"task_id": _ID, "driver_id": _ID}),
    "background.stop": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "job_id": _ID, "result": _RESULT}, {"task_id": _ID, "driver_id": _ID}),
    "background.snapshot": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "active_count": _NONNEGATIVE}, {"task_id": _ID, "driver_id": _ID}),
    "turn.stop": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE, "background_active": _BOOL}, {"task_id": _ID, "driver_id": _ID, "turn_id": _ID}),
    "session.end": ({"event_id": _ID, "producer_seq": _POSITIVE, "session_id": _ID, "harness": _HARNESS, "role": _ROLE}, {"task_id": _ID, "driver_id": _ID}),
    "watchtower.register": ({"request_id": _ID, "session_id": _ID, "harness": _HARNESS, "driver_id": _ID}, {}),
    "notification": ({"generation": _POSITIVE, "priority": _PRIORITY, "task_count": _NONNEGATIVE}, {}),
    "notification.delivered": ({"request_id": _ID, "driver_id": _ID, "generation": _POSITIVE}, {}),
    "reconcile": ({"request_id": _ID, "driver_id": _ID, "through": _POSITIVE}, {}),
    "reconcile.result": ({"request_id": _ID, "through": _POSITIVE, "reports": lambda value, field: _reports(value, field)}, {}),
    "ack-generation": ({"request_id": _ID, "driver_id": _ID, "through": _POSITIVE}, {}),
    "ok": ({"request_id": _ID}, {}),
    "ack": ({"event_id": _ID, "durable_seq": _POSITIVE}, {}),
    "error": ({"code": _enum("invalid-json", "invalid-message", "invalid-version", "invalid-event", "invalid-field", "unsupported-type")}, {"event_id": _ID, "request_id": _ID}),
}


def _reports(value: Any, field: str) -> None:
    if not isinstance(value, list):
        _fail("invalid-field", f"{field} must be an array", field)
    for report in value:
        if not isinstance(report, dict):
            _fail("invalid-field", f"each {field} entry must be an object", field)


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
    if message_type == "error" and ("event_id" in message) == ("request_id" in message):
        _fail("invalid-message", "error must correlate exactly one event_id or request_id")
    return message


def decode(line: str | bytes) -> dict[str, Any]:
    """Decode one JSON frame and validate it."""
    try:
        message = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("invalid-json", "frame is not valid JSON") from exc
    return validate(message)


def encode(message: Any) -> str:
    """Validate and encode one canonical, newline-terminated NDJSON frame."""
    validate(message)
    return json.dumps(message, sort_keys=True, separators=(",", ":")) + "\n"
