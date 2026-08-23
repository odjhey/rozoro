#!/usr/bin/env python3
"""Persistent, opt-in Claude watchtower notification actuator."""
from __future__ import annotations

import argparse
import json
import os
import select
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

FIXED = "Rozoro notification pending; run ./bin/rozoro reconcile."


def frame(kind: str, **fields: Any) -> bytes:
    return (json.dumps({"v": 1, "type": kind, "request_id": uuid.uuid4().hex, **fields},
                       separators=(",", ":")) + "\n").encode()


def run(home: Path, driver: str, session: str, pane: str, *, parent: int = 0,
        poll: float = .1, rpc_timeout: float = .75, ready_file: Path | None = None) -> int:
    """Reconnect until certified session end/parent death; never infer quiescence."""
    def owner_alive() -> bool:
        if not parent: return True
        try: os.kill(parent, 0); return True
        except ProcessLookupError: return False
        except PermissionError: return False

    while owner_alive():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(rpc_timeout)
                client.connect(str(home / "monitor.sock"))
                stream = client.makefile("rb", buffering=0)

                def request(kind: str, *, extra: bool = False, **fields: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
                    client.sendall(frame(kind, **fields))
                    ready, _, _ = select.select([client], [], [], rpc_timeout)
                    if not ready: raise TimeoutError("daemon response timeout")
                    response = json.loads(stream.readline())
                    following = None
                    if extra:
                        ready, _, _ = select.select([client], [], [], poll)
                        if ready: following = json.loads(stream.readline())
                    return response, following

                reply, _ = request("watchtower.register", session_id=session,
                                   harness="claude", driver_id=driver)
                if reply.get("type") != "ok": raise RuntimeError("registration refused")
                if ready_file is not None:
                    temporary = ready_file.with_name(ready_file.name + f".tmp.{os.getpid()}")
                    temporary.write_text(str(os.getpid()) + "\n"); os.chmod(temporary, 0o600)
                    os.replace(temporary, ready_file)
                while owner_alive():
                    state, _ = request("watchtower.availability", driver_id=driver)
                    availability = state.get("availability")
                    if availability == "gone": return 0
                    if availability == "quiescent":
                        pending, notification = request("notification.pending", extra=True,
                                                        driver_id=driver)
                        if pending.get("type") != "ok": raise RuntimeError("poll refused")
                        if notification and notification.get("type") == "notification":
                            generation = notification.get("generation")
                            if not isinstance(generation, int): raise RuntimeError("bad generation")
                            delivered = subprocess.run(
                                ["herdr", "agent", "prompt", pane, FIXED], timeout=rpc_timeout,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, check=False)
                            if delivered.returncode != 0:
                                raise RuntimeError("herdr delivery refused")
                            confirmed, _ = request("notification.delivered", driver_id=driver,
                                                   generation=generation)
                            if confirmed.get("type") != "ok": raise RuntimeError("confirmation refused")
                    time.sleep(poll)
                return 0
        except (ConnectionError, OSError, TimeoutError, ValueError, RuntimeError,
                json.JSONDecodeError, subprocess.SubprocessError):
            if not owner_alive(): return 0
            time.sleep(min(.25, max(.02, poll)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--pane", required=True)
    parser.add_argument("--parent", type=int, default=0)
    parser.add_argument("--poll", type=float, default=.1)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    if args.poll <= 0: parser.error("--poll must be positive")
    try:
        return run(args.home, args.driver, args.session, args.pane, parent=args.parent,
                   poll=args.poll, ready_file=args.ready_file)
    finally:
        if args.ready_file is not None:
            try: args.ready_file.unlink()
            except FileNotFoundError: pass


if __name__ == "__main__":
    raise SystemExit(main())
