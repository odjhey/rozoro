#!/usr/bin/env python3
"""Process regression for the documented minimum monitor Python runtime."""
import asyncio
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.rozoro_monitor.herdr import MembershipMonitor
from lib.rozoro_monitor.store import _MIGRATIONS, SCHEMA_VERSION

if os.environ.get("ROZORO_REQUIRE_PYTHON_311") == "1":
    assert sys.version_info[:2] == (3, 11), sys.version
else:
    assert sys.version_info >= (3, 11), sys.version


async def prove_periodic_runner_survives_deadlines():
    scans = 0
    monitor = MembershipMonitor(
        ".", lambda _panes: None, lambda _pane: None, lambda _task, _level: None,
        scan_interval=0.02, hint_interval=1.0, debounce=0, drain_interval=0,
    )

    async def scan(*, force=False):
        nonlocal scans
        scans += 1

    monitor.scan = scan
    await monitor.start()
    await asyncio.sleep(0.09)
    assert scans >= 3, scans
    assert monitor._runner is not None and not monitor._runner.done()
    await monitor.close()


asyncio.run(prove_periodic_runner_survives_deadlines())

# These process tests drive real server read deadlines and constrained-FD
# refusal behavior. On Python 3.10 they reproduce uncaught asyncio timeouts;
# the supported 3.11 floor must return protocol errors rather than EOF.
subprocess.run([
    sys.executable, "-m", "unittest",
    "tests.python.test_server.ServerProcessTests.test_idle_deadline_and_client_cap_refuse_deterministically",
    "tests.python.test_server.ServerProcessTests.test_low_fd_limit_reserves_capacity_and_refuses_before_emfile",
], cwd=ROOT, check=True)


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
    # The public `rozoro` rollback CLI is a herdr orchestrator front-end that
    # refuses to run unless `herdr` is on PATH, even though the rollback verb
    # only drives the pure-Python daemon bridge. CI hosts do not install herdr,
    # so expose the repository's fake (as the bats suite does via tests/fakes)
    # to exercise the real public CLI path deterministically.
    (python_bin / "herdr").symlink_to(ROOT / "tests/fakes/herdr")
    os.environ["FAKE_HERDR_ROOT"] = str(Path(temporary) / "fake-herdr")
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
