#!/usr/bin/env python3
"""Forward terminal-style interrupts to an isolated test process group."""
import os
import signal
import subprocess
import sys

child = subprocess.Popen(sys.argv[1:], start_new_session=True)

def forward(signum, _frame):
    try: os.killpg(child.pid, signum)
    except ProcessLookupError: pass

signal.signal(signal.SIGINT, forward)
signal.signal(signal.SIGTERM, forward)
raise SystemExit(child.wait())
