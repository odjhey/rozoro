#!/usr/bin/env python3
"""External test-run guardian; a pipe EOF survives abrupt parent termination."""
import os
import signal
import sys
import time
from pathlib import Path

read_fd, child_pgid, root = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
while os.read(read_fd, 1):
    pass
os.close(read_fd)
# Consume exact spawn records before signaling Bats, whose teardown may remove them.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_helper import process_cleanup
for registry in root.rglob("*owned-processes*.jsonl"):
    os.environ["ROZORO_TEST_PROCESS_REGISTRY"] = str(registry)
    process_cleanup.cleanup()
try:
    os.killpg(child_pgid, signal.SIGTERM)
except ProcessLookupError:
    pass
time.sleep(.1)
try:
    os.killpg(child_pgid, signal.SIGKILL)
except ProcessLookupError:
    pass
