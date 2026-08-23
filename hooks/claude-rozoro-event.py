#!/usr/bin/env python3
"""Claude Code 2.1.240 lifecycle hook for managed Rozoro crew and watchtower sessions.

The hook deliberately extracts only opaque lifecycle identifiers and never
publishes prompt, transcript, command, description, or assistant content.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from rozoro_monitor.client import ClientError, ProducerClient, prepare_event  # noqa: E402

CAPABILITY = "2.1.240"
EVENTS = {"SessionStart", "UserPromptSubmit", "SubagentStart", "SubagentStop", "Stop", "SessionEnd"}


_CLAUDE_BINARY: str | None = None
_CAPABILITY_PROOF: str | None = None


def _claude_version() -> str | None:
    """Verify a private launch-time proof against the pinned executable inode."""
    binary, proof = _CLAUDE_BINARY, _CAPABILITY_PROOF
    if not binary or not proof or not os.path.isabs(binary) or not os.path.isabs(proof):
        return None
    try:
        info = os.stat(proof, follow_symlinks=False)
        if not __import__("stat").S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            return None
        value = json.loads(Path(proof).read_text())
        actual = os.stat(os.path.realpath(binary))
        if value.get("binary") != os.path.realpath(binary) or [actual.st_dev, actual.st_ino] != value.get("identity"):
            return None
        return value.get("version") if isinstance(value.get("version"), str) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _identity(payload: dict[str, Any]) -> dict[str, Any] | None:
    role = os.environ.get("ROZORO_ROLE")
    if role not in {"crew", "watchtower"} or _claude_version() != CAPABILITY:
        return None
    expected_session = os.environ.get("ROZORO_SESSION_ID", "")
    native_session = os.environ.get("ROZORO_NATIVE_SESSION_ID", expected_session)
    actual_session = payload.get("session_id")
    identity_name = "task_id" if role == "crew" else "driver_id"
    identity = os.environ.get("ROZORO_TASK_ID" if role == "crew" else "ROZORO_DRIVER_ID", "")
    if not identity or not expected_session or actual_session != native_session:
        return None
    return {"v": 1, "session_id": expected_session, "harness": "claude", "role": role, identity_name: identity}


def _event(base: dict[str, Any], event_type: str, **fields: Any) -> dict[str, Any]:
    return dict(base, type=event_type, event_id=uuid.uuid4().hex, **fields)


def map_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a certified payload to frozen protocol events, without prose fields."""
    name = payload.get("hook_event_name")
    if name not in EVENTS:
        return []
    base = _identity(payload)
    if base is None:
        return []

    prompt_id = payload.get("prompt_id")
    if name == "SessionStart":
        return [_event(base, "session.register")]
    if name == "UserPromptSubmit":
        return [_event(base, "turn.start", turn_id=prompt_id)] if isinstance(prompt_id, str) and prompt_id else []
    if name == "SubagentStart":
        job_id = payload.get("agent_id")
        return [_event(base, "background.start", job_id=job_id, job_kind="subagent")] if isinstance(job_id, str) and job_id else []
    if name == "SubagentStop":
        # A stop edge cannot certify that Claude has no other owned work. The
        # frozen reducer may match this opaque ID against an authoritative
        # count-only snapshot and incorrectly derive clear, so retain the last
        # positive evidence until the next authoritative Stop snapshot.
        return []
    if name == "SessionEnd":
        return [_event(base, "session.end")]

    # Only Stop.background_tasks is certified as authoritative. Retain no task
    # content, and certify clear only for an explicitly present, valid empty list.
    snapshot = payload.get("background_tasks")
    valid_snapshot = isinstance(snapshot, list) and all(
        isinstance(item, dict)
        and isinstance(item.get("id"), str) and bool(item["id"])
        and item.get("status") == "running"
        and item.get("type") in {"subagent", "shell"}
        for item in snapshot
    )
    events: list[dict[str, Any]] = []
    if valid_snapshot:
        events.append(_event(base, "background.snapshot", active_count=len(snapshot)))
    fields: dict[str, Any] = {"background_active": bool(snapshot) if valid_snapshot else None}
    if isinstance(prompt_id, str) and prompt_id:
        fields["turn_id"] = prompt_id
    # Stop the foreground first, then apply the authoritative count last. A
    # true boolean carries presence only and would otherwise de-certify the
    # exact snapshot baseline in the frozen reducer.
    events.insert(0, _event(base, "turn.stop", **fields))
    return events


def main() -> int:
    global _CLAUDE_BINARY, _CAPABILITY_PROOF
    if (len(sys.argv) != 5 or sys.argv[1] != "--claude-binary" or sys.argv[3] != "--capability-proof"
            or not os.path.isabs(sys.argv[2]) or not os.path.isabs(sys.argv[4])):
        return 0
    _CLAUDE_BINARY, _CAPABILITY_PROOF = sys.argv[2], sys.argv[4]
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        events = map_payload(payload)
        if not events:
            return 0
        budget = max(0.0, min(float(os.environ.get("ROZORO_HOOK_TIMEOUT", "0.75")), 0.75))
        deadline = time.monotonic() + budget
        # Reserve every envelope before attempting transport. Thus the second
        # Stop event cannot be lost or wait for another full socket timeout if
        # the first event's ACK is delayed/lost.
        prepared = [prepare_event(event) for event in events]
        client = ProducerClient(timeout=budget or 0.001)
        for event in prepared:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            client.timeout = remaining
            try:
                client.send(event)
            except ClientError:
                continue
    except (ClientError, ValueError, OSError, json.JSONDecodeError):
        # Hooks must not alter unrelated Claude behavior. Invalid/uncertified
        # input emits no lifecycle claim rather than guessing.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
