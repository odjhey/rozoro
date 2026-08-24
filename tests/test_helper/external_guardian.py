#!/usr/bin/env python3
"""External test-run guardian; a pipe EOF survives abrupt parent termination."""
import os
import signal
import sys
import time
from pathlib import Path

read_fd, child_pgid, root = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
child_birth, child_token = sys.argv[4], sys.argv[5]
payload = bytearray()
while chunk := os.read(read_fd, 64):
    payload.extend(chunk)
os.close(read_fd)
if payload == b"graceful":
    raise SystemExit(0)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_helper import process_cleanup
for registry in root.rglob("*owned-processes*.jsonl"):
    os.environ["ROZORO_TEST_PROCESS_REGISTRY"] = str(registry)
    process_cleanup.cleanup()


def owns_group() -> bool:
    if process_cleanup._birth(child_pgid, child_token) != child_birth:
        return False
    try:
        return os.getpgid(child_pgid) == child_pgid
    except ProcessLookupError:
        return False


if owns_group():
    try:
        os.killpg(child_pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(.1)
if owns_group():
    try:
        os.killpg(child_pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
