#!/usr/bin/env python3
"""Run a test group with an external pipe-liveness cleanup guardian."""
import os
import secrets
import signal
import subprocess
import sys
from pathlib import Path

child_token = secrets.token_hex(16)
child_env = os.environ.copy()
child_env["ROZORO_TEST_GUARDIAN_TOKEN"] = child_token
child = subprocess.Popen(sys.argv[1:], start_new_session=True, env=child_env)
if os.environ.get("INTERRUPT_CHILD_PID_FILE"):
    Path(os.environ["INTERRUPT_CHILD_PID_FILE"]).write_text(str(child.pid))
root = os.environ.get("INTERRUPT_REGISTRY_ROOT", "")
read_fd, write_fd = os.pipe()
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_helper.process_cleanup import _birth
child_birth = _birth(child.pid, child_token)
if child_birth is None:
    status = child.wait()
    os.close(read_fd)
    os.close(write_fd)
    raise SystemExit(status)
guardian = None
if root:
    guardian = subprocess.Popen([
        sys.executable, str(Path(__file__).with_name("external_guardian.py")),
        str(read_fd), str(child.pid), root, child_birth, child_token,
    ], pass_fds=(read_fd,), start_new_session=True)
os.close(read_fd)

def forward(signum, _frame):
    try: os.killpg(child.pid, signum)
    except ProcessLookupError: pass

signal.signal(signal.SIGINT, forward)
signal.signal(signal.SIGTERM, forward)
status = child.wait()
os.write(write_fd, b"graceful")
os.close(write_fd)
if guardian is not None:
    guardian.wait(timeout=10)
raise SystemExit(status)
