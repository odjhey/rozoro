#!/usr/bin/env python3
"""Run a test group with an external pipe-liveness cleanup guardian."""
import os
import signal
import subprocess
import sys
from pathlib import Path

child = subprocess.Popen(sys.argv[1:], start_new_session=True)
if os.environ.get("INTERRUPT_CHILD_PID_FILE"):
    Path(os.environ["INTERRUPT_CHILD_PID_FILE"]).write_text(str(child.pid))
root = os.environ.get("INTERRUPT_REGISTRY_ROOT", "")
read_fd, write_fd = os.pipe()
guardian = None
if root:
    guardian = subprocess.Popen([
        sys.executable, str(Path(__file__).with_name("external_guardian.py")),
        str(read_fd), str(child.pid), root,
    ], pass_fds=(read_fd,), start_new_session=True)
os.close(read_fd)

def forward(signum, _frame):
    try: os.killpg(child.pid, signum)
    except ProcessLookupError: pass

signal.signal(signal.SIGINT, forward)
signal.signal(signal.SIGTERM, forward)
status = child.wait()
os.close(write_fd)
if guardian is not None:
    guardian.wait(timeout=10)
raise SystemExit(status)
