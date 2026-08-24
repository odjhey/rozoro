#!/usr/bin/env python3
"""Translate a managed Codex rollout JSONL into Rozoro protocol-v1 lifecycle events."""
from __future__ import annotations

import argparse
import glob
import json
import os
import socket
import time
import uuid
from pathlib import Path


def find_rollout(store: Path, task: str, cwd: str, session: str | None) -> tuple[Path, str] | None:
    marker = f"rozoro-task: {task}"
    for name in sorted(glob.glob(str(store / "**" / "*.jsonl"), recursive=True), reverse=True):
        try:
            with open(name, encoding="utf-8") as stream:
                first = json.loads(next(stream))
                payload = first.get("payload", {})
                if first.get("type") != "session_meta" or payload.get("cwd") != cwd:
                    continue
                sid = payload.get("id")
                if not sid or (session and sid != session):
                    continue
                if session:
                    return Path(name), sid
                for line in stream:
                    item = json.loads(line)
                    message = item.get("payload", {})
                    if item.get("type") == "response_item" and message.get("type") == "message" and message.get("role") == "user":
                        if any(marker in part.get("text", "").splitlines() for part in message.get("content", []) if isinstance(part, dict)):
                            return Path(name), sid
        except (OSError, StopIteration, ValueError):
            continue
    return None


class Producer:
    def __init__(self, socket_path: Path, task: str, session: str):
        self.socket_path, self.task, self.session = socket_path, task, session
        self.seq = 0

    def emit(self, kind: str, **fields: object) -> None:
        self.seq += 1
        frame = {"v": 1, "type": kind, "event_id": uuid.uuid4().hex,
                 "producer_seq": self.seq, "session_id": self.session,
                 "harness": "codex", "role": "crew", "task_id": self.task, **fields}
        # A fresh correlated connection per event makes daemon restarts recoverable.
        while True:
            try:
                with socket.socket(socket.AF_UNIX) as conn:
                    conn.settimeout(3)
                    conn.connect(str(self.socket_path))
                    conn.sendall((json.dumps(frame, separators=(",", ":")) + "\n").encode())
                    reply = json.loads(conn.makefile().readline())
                    if reply.get("type") != "ack" or reply.get("event_id") != frame["event_id"]:
                        raise RuntimeError(f"event rejected: {reply}")
                    return
            except (OSError, ValueError, RuntimeError):
                time.sleep(.2)


def run(args: argparse.Namespace) -> None:
    store = Path(args.store).expanduser()
    found = None
    while found is None:
        found = find_rollout(store, args.task, args.cwd, args.session)
        if found is None:
            time.sleep(.1)
    path, session = found
    producer = Producer(Path(args.socket), args.task, session)
    producer.emit("session.register")
    with path.open(encoding="utf-8") as stream:
        while True:
            line = stream.readline()
            if not line:
                time.sleep(.05)
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item.get("type") != "event_msg":
                continue
            payload = item.get("payload", {})
            turn = payload.get("turn_id")
            if payload.get("type") == "task_started" and turn:
                producer.emit("turn.start", turn_id=turn)
            elif payload.get("type") == "task_complete" and turn:
                # Codex exposes no certified background-job state.
                producer.emit("turn.stop", turn_id=turn, background_active=None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True); parser.add_argument("--cwd", required=True)
    parser.add_argument("--session"); parser.add_argument("--store", required=True); parser.add_argument("--socket", required=True)
    run(parser.parse_args())

if __name__ == "__main__":
    main()
