#!/usr/bin/env python3
"""Persistent fake Herdr socket API for tests that need delivery, not just edges.

`event_server.py` replays one canned subscription; this one stays up and serves
the whole surface `rozorod` uses against a live session: `events.subscribe` plus
concurrent `agent.get`/`pane.get`/`agent.prompt` round trips, each on its own
connection, for as long as the test needs.

Pane state is a file per pane (`status.<pane>` under the root, matching the CLI
fake's `fake_pane` convention), so a test changes what an agent is doing by
rewriting that file - subscribers notice and push the edge. Every `agent.prompt`
is appended to the log as `<pane>\\t<text>`, which is how a test proves a
follow-up actually reached a pane.

Usage: fake_herdr_daemon.py <socket-path> <root-dir> <prompt-log>
"""
import json
import os
import socket
import sys
import threading
import time

SOCKET_PATH, ROOT, PROMPT_LOG = sys.argv[1:4]
POLL_INTERVAL = 0.05
_log_lock = threading.Lock()


def pane_status(pane):
    try:
        with open(os.path.join(ROOT, f"status.{pane}")) as handle:
            return handle.read().strip()
    except OSError:
        return None


def send(conn, payload):
    conn.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode())


def not_found(conn, request_id):
    send(conn, {"id": request_id, "error": {"code": "not_found", "message": "pane_not_found"}})


def handle_subscribe(conn, request_id, params):
    panes = [item.get("pane_id") for item in params.get("subscriptions", [])]
    panes = [pane for pane in panes if pane]
    # Real Herdr rejects the whole subscription when any pane is absent, which is
    # what drives rozorod's per-pane sharding fallback.
    for pane in panes:
        if pane_status(pane) is None:
            not_found(conn, request_id)
            return
    send(conn, {"id": request_id, "result": {"type": "subscription_started"}})
    seen = {pane: pane_status(pane) for pane in panes}
    seq = 0
    while True:
        time.sleep(POLL_INTERVAL)
        for pane in panes:
            current = pane_status(pane)
            if current is None or current == seen[pane]:
                continue
            seen[pane] = current
            seq += 1
            send(conn, {"event": "pane.agent_status_changed",
                        "data": {"pane_id": pane, "workspace_id": "w1",
                                 "agent_status": current, "agent": "agent",
                                 "state_change_seq": seq}})


def serve(conn):
    stream = conn.makefile("rb")
    while True:
        line = stream.readline()
        if not line:
            return
        try:
            request = json.loads(line)
        except ValueError:
            return
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if method == "events.subscribe":
            handle_subscribe(conn, request_id, params)
            return
        if method == "agent.get":
            status = pane_status(params.get("target"))
            if status is None:
                not_found(conn, request_id)
                continue
            send(conn, {"id": request_id, "result": {
                "type": "agent_info",
                "agent": {"agent": "pi", "agent_status": status,
                          "interactive_ready": True,
                          "pane_id": params.get("target"), "state_change_seq": 1}}})
            continue
        if method == "pane.get":
            if pane_status(params.get("pane_id")) is None:
                not_found(conn, request_id)
            else:
                send(conn, {"id": request_id, "result": {"type": "pane_info"}})
            continue
        if method == "agent.prompt":
            target, text = params.get("target"), params.get("text", "")
            if pane_status(target) is None:
                not_found(conn, request_id)
                continue
            with _log_lock, open(PROMPT_LOG, "a") as handle:
                handle.write(f"{target}\t{text}\n")
            send(conn, {"id": request_id, "result": {"type": "ok"}})
            continue
        send(conn, {"id": request_id, "error": {"code": "unsupported", "message": method}})


def main():
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(16)
    while True:
        conn, _ = server.accept()
        thread = threading.Thread(target=serve, args=(conn,), daemon=True)
        thread.start()


if __name__ == "__main__":
    main()
