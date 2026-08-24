#!/usr/bin/env python3
"""Codex native lifecycle hook for managed Rozoro crew sessions."""
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

EVENTS = {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"}


def map_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    name = payload.get("hook_event_name")
    task = os.environ.get("ROZORO_TASK_ID", "")
    session = payload.get("session_id")
    if name not in EVENTS or not task or not isinstance(session, str) or not session:
        return []
    base = {"v": 1, "session_id": session, "harness": "codex", "role": "crew", "task_id": task}
    fields: dict[str, Any] = {}
    turn = payload.get("turn_id")
    if isinstance(turn, str) and turn:
        fields["turn_id"] = turn
    kind = {"SessionStart": "session.register", "UserPromptSubmit": "turn.start",
            "Stop": "turn.stop", "SessionEnd": "session.end"}[name]
    if name == "Stop":
        # Codex does not provide an authoritative all-background-clear snapshot.
        fields["background_active"] = None
    return [dict(base, type=kind, event_id=uuid.uuid4().hex, **fields)]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            deadline = time.monotonic() + .75
            for event in map_payload(payload):
                prepared = prepare_event(event)
                client = ProducerClient(timeout=max(.001, deadline - time.monotonic()))
                client.send(prepared)
    except (ClientError, ValueError, OSError, json.JSONDecodeError):
        return 0
    # Native hooks require a JSON object on stdout.
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
