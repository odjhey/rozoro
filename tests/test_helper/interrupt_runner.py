#!/usr/bin/env python3
"""Forward terminal-style interrupts to an isolated test process group."""
import os
import signal
import subprocess
import sys
from pathlib import Path

child = subprocess.Popen(sys.argv[1:], start_new_session=True)
if os.environ.get("INTERRUPT_CHILD_PID_FILE"):
    Path(os.environ["INTERRUPT_CHILD_PID_FILE"]).write_text(str(child.pid))

def forward(signum, _frame):
    try: os.killpg(child.pid, signum)
    except ProcessLookupError: pass

signal.signal(signal.SIGINT, forward)
signal.signal(signal.SIGTERM, forward)
status = child.wait()
root = os.environ.get("INTERRUPT_REGISTRY_ROOT")
if root:
    import time; time.sleep(.2)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.test_helper import process_cleanup
    for registry in Path(root).rglob("*owned-processes*.jsonl"):
        os.environ["ROZORO_TEST_PROCESS_REGISTRY"] = str(registry)
        process_cleanup.cleanup()
raise SystemExit(status)
