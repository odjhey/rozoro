#!/usr/bin/env python3
"""Claude Code 2.1.240 lifecycle hook for opt-in Rozoro crew sessions.

The hook deliberately extracts only opaque lifecycle identifiers and never
publishes prompt, transcript, command, description, or assistant content.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
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


def _identity(payload: dict[str, Any]) -> dict[str, Any] | None:
    if os.environ.get("ROZORO_EVENT_BUS") != "1":
        return None
    role = os.environ.get("ROZORO_ROLE")
    if role not in {"crew", "watchtower"} or os.environ.get("ROZORO_CLAUDE_CAPABILITY") != CAPABILITY:
        return None
    expected_session = os.environ.get("ROZORO_SESSION_ID", "")
    actual_session = payload.get("session_id")
    identity_name = "task_id" if role == "crew" else "driver_id"
    identity = os.environ.get("ROZORO_TASK_ID" if role == "crew" else "ROZORO_DRIVER_ID", "")
    if not identity or not expected_session or actual_session != expected_session:
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


NOTIFICATION_READ_BUDGET = 0.1


def _watchtower_actuate(base: dict[str, Any], payload: dict[str, Any], timeout: float) -> None:
    """Register durably and claim/deliver only at a certified clear Stop.

    The daemon binds watchtower registration to the connection that carried
    watchtower.register, so registration, the pending poll, and the delivery
    confirmation must travel one persistent connection.
    """
    driver = base["driver_id"]
    path = Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser() / "monitor.sock"
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        stream = client.makefile("rb")

        def send(message: dict[str, Any]) -> None:
            frame = dict(message, v=1, request_id=uuid.uuid4().hex)
            client.sendall((json.dumps(frame, separators=(",", ":")) + "\n").encode())

        def receive(bound: float) -> dict[str, Any] | None:
            remaining = min(bound, deadline - time.monotonic())
            if remaining <= 0:
                return None
            client.settimeout(remaining)
            line = stream.readline()
            return json.loads(line) if line else None

        send({"type": "watchtower.register", "session_id": base["session_id"],
              "harness": "claude", "driver_id": driver})
        registered = receive(timeout)
        if not isinstance(registered, dict) or registered.get("type") != "ok":
            return
        snapshot = payload.get("background_tasks")
        if payload.get("hook_event_name") != "Stop" or payload.get("stop_hook_active") is not False:
            return
        if not isinstance(snapshot, list) or snapshot:  # missing/malformed/nonempty fails closed
            return
        send({"type": "notification.pending", "driver_id": driver})
        reply = receive(timeout)
        if not isinstance(reply, dict) or reply.get("type") != "ok":
            return
        try:
            notification = receive(NOTIFICATION_READ_BUDGET)
        except TimeoutError:
            return
        if not isinstance(notification, dict) or notification.get("type") != "notification":
            return
        generation = notification.get("generation")
        if not isinstance(generation, int):
            return
        pane = os.environ.get("ROZORO_HERDR_PANE_ID", "")
        remaining = deadline - time.monotonic()
        if not pane or remaining <= 0:
            return
        fixed = "Rozoro notification pending; run ./bin/rozoro reconcile."
        completed = subprocess.run(["herdr", "agent", "prompt", pane, fixed], timeout=remaining,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=False)
        if completed.returncode != 0:
            return
        send({"type": "notification.delivered", "driver_id": driver, "generation": generation})
        try:
            receive(timeout)
        except OSError:
            pass


def main() -> int:
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
        if events and events[0].get("role") == "watchtower":
            remaining = deadline - time.monotonic()
            if remaining > 0:
                try:
                    _watchtower_actuate(events[0], payload, remaining)
                except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
                    pass
    except (ClientError, ValueError, OSError, json.JSONDecodeError):
        # Hooks must not alter unrelated Claude behavior. Invalid/uncertified
        # input emits no lifecycle claim rather than guessing.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
