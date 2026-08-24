#!/usr/bin/env python3
"""Prove stock macOS Python 3.9 rejects the monitor before side effects."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
assert sys.version_info[:2] == (3, 9), sys.version

with tempfile.TemporaryDirectory() as temporary:
    home = Path(temporary) / "rozoro"
    env = dict(os.environ, ROZORO_HOME=str(home))
    expected = "Python >=3.10"

    start = subprocess.run(
        [sys.executable, str(ROOT / "bin/rzr-monitor.py"), "start"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert start.returncode == 2, start
    assert expected in start.stderr, start
    assert "brew install python" in start.stderr and "first on PATH" in start.stderr, start
    assert not home.exists(), list(home.parent.iterdir())

    daemon = subprocess.run(
        [sys.executable, str(ROOT / "bin/rozorod.py"), "--home", str(home)],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert daemon.returncode == 2, daemon
    assert expected in daemon.stderr, daemon
    assert "brew install python" in daemon.stderr and "first on PATH" in daemon.stderr, daemon
    assert not home.exists(), list(home.parent.iterdir())
