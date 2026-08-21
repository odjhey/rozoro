#!/usr/bin/env python3
"""Raw AF_UNIX subscriber for herdr's native pane.agent_status_changed stream.

The WIRE TRANSPORT for rozoro's push-based watcher (bin/fl-watch.sh). It knows
nothing about rozoro's policy: it opens ONE connection to the herdr control
socket, subscribes to pane.agent_status_changed for the given panes (ALL
statuses, so working/idle/done/blocked edges are all seen), and prints one
TAB-separated line per event to stdout, flushing each so the bash caller reacts
sub-second. This replaces the old `agent wait --until` re-arm loop, which was
LEVEL-triggered (returned instantly while a pane sat in a transient/`unknown`
state) and spun the CPU. A push edge is a real edge; there is nothing to spin.

Wire protocol (verified on herdr 0.8.2, protocol 16+; newline-delimited JSON):
  request : {"id","method":"events.subscribe","params":{"subscriptions":[
             {"type":"pane.agent_status_changed","pane_id":P}, ...]}}\n
  ack     : {"id",...,"result":{"type":"subscription_started"}}\n
  stream  : {"event":"pane.agent_status_changed",
             "data":{"pane_id","workspace_id","agent_status","agent",...}}\n

Usage: herdr-eventwait.py <socket_path> <timeout_seconds> <pane_id> [<pane_id>...]
  timeout_seconds <= 0 streams FOREVER (until killed or the socket closes) -
  rozoro's watcher is long-lived, so that is the normal mode.

Output (one line per event, TAB-separated; a raw projection, the bash side adds
timing and dedups):
  @subscribed
  <pane_id>\t<workspace_id>\t<agent_status>\t<agent>

Exit status:
  0  the bounded timeout elapsed cleanly, or the caller closed our stdout.
  2  bad arguments, could not connect, or could not send the subscribe request.
  3  the subscribe request did not return a subscription_started ack.
  4  the server closed the stream or a receive operation failed.
A non-zero exit tells fl-watch the push path is unavailable this run.
"""
import json
import socket
import sys
import time

CONNECT_TIMEOUT = 5.0
ACK_TIMEOUT = 5.0
RECV_CHUNK = 65536


def _read_line(sock, buf, deadline):
    """Read one newline-terminated chunk, honoring an absolute monotonic
    deadline (None = no deadline). Returns (line_or_None, buf, outcome) where
    outcome is line, timeout, closed, or error."""
    while b"\n" not in buf:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, buf, "timeout"
            sock.settimeout(remaining)
        else:
            sock.settimeout(None)
        try:
            chunk = sock.recv(RECV_CHUNK)
        except socket.timeout:
            return None, buf, "timeout"
        except OSError:
            return None, buf, "error"
        if not chunk:
            return None, buf, "closed"
        buf += chunk
    line, buf = buf.split(b"\n", 1)
    return line, buf, "line"


def _clean(value):
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")


def main(argv):
    if len(argv) < 4:
        return 2
    sock_path = argv[1]
    try:
        timeout = float(argv[2])
    except ValueError:
        return 2
    panes = argv[3:]
    if not panes:
        return 2
    forever = timeout <= 0

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect(sock_path)
    except OSError:
        return 2

    subscriptions = [
        {"type": "pane.agent_status_changed", "pane_id": pane} for pane in panes
    ]
    request = {
        "id": "rozoro-eventwait",
        "method": "events.subscribe",
        "params": {"subscriptions": subscriptions},
    }
    try:
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
    except OSError:
        return 2

    start = time.monotonic()
    deadline = None if forever else start + timeout
    buf = b""

    # Bounded wait for the subscription_started ack (its own short budget).
    ack_deadline = start + ACK_TIMEOUT
    if deadline is not None:
        ack_deadline = min(deadline, ack_deadline)
    line, buf, outcome = _read_line(sock, buf, ack_deadline)
    if line is None:
        return 2
    try:
        ack = json.loads(line.decode("utf-8", "replace"))
    except ValueError:
        return 3
    result = ack.get("result") or {}
    if result.get("type") != "subscription_started":
        return 3

    sys.stdout.write("@subscribed\n")
    sys.stdout.flush()

    # Stream projected events until the deadline (if any) or the server closes.
    while True:
        line, buf, outcome = _read_line(sock, buf, deadline)
        if line is None:
            return 0 if outcome == "timeout" else 4
        try:
            message = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue
        if message.get("event") != "pane.agent_status_changed":
            continue
        data = message.get("data") or {}
        fields = (
            _clean(data.get("pane_id") or ""),
            _clean(data.get("workspace_id") or ""),
            _clean(data.get("agent_status") or ""),
            _clean(data.get("agent") or ""),
        )
        sys.stdout.write("\t".join(fields) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:
        # fl-watch stopped reading (e.g. --once found its edge and killed us).
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
