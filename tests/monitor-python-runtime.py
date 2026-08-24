#!/usr/bin/env python3
"""Process regression for the documented minimum monitor Python runtime."""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.rozoro_monitor.store import _MIGRATIONS, SCHEMA_VERSION

if os.environ.get("ROZORO_REQUIRE_PYTHON_39") == "1":
    assert sys.version_info[:2] == (3, 9), sys.version
else:
    assert sys.version_info >= (3, 9), sys.version


def run(*args, home, check=True):
    env = dict(os.environ, ROZORO_HOME=str(home))
    return subprocess.run(
        [sys.executable, *map(str, args)], env=env, check=check,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


with tempfile.TemporaryDirectory() as temporary:
    python_bin = Path(temporary) / "bin"
    python_bin.mkdir()
    (python_bin / "python3").symlink_to(sys.executable)
    os.environ["PATH"] = f"{python_bin}{os.pathsep}{os.environ['PATH']}"
    home = Path(temporary) / "rozoro"
    home.mkdir(mode=0o700)
    database = sqlite3.connect(home / "monitor.db")
    database.executescript(_MIGRATIONS[1])
    database.execute("PRAGMA user_version=1")
    database.commit()
    database.close()
    os.chmod(home / "monitor.db", 0o600)

    started = run(ROOT / "bin/rzr-monitor.py", "start", home=home)
    assert "monitor started" in started.stdout, started
    status = run(ROOT / "bin/rzr-monitor.py", "status", "--json", home=home)
    assert f'"schema_version":{SCHEMA_VERSION}' in status.stdout, status

    # Exercises real socket events, delivery/ack, dirty refusal, and clean
    # cutover rollback through the public CLI.
    run(ROOT / "tests/rollback-process.py", ROOT, home, home=home)

    stopped = run(ROOT / "bin/rzr-monitor.py", "stop", home=home)
    assert "monitor stopped" in stopped.stdout, stopped
    reset = run(ROOT / "bin/rzr-monitor.py", "reset", "--force", home=home)
    assert "database reset" in reset.stdout, reset
