"""H2 home-selection contract for the monitor, daemon, client, and bridge.

Matrix identities: P=public, L=legacy, B=both, E=empty public,
D=default, R=relative, T=tilde, O=explicit override, X=XDG decoy.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.rozoro_monitor.client import _open_home, resolve_home
from lib.rozoro_monitor.server import MonitorServer

ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "bin/rzr-monitor.py"
DAEMON = ROOT / "bin/rozorod.py"
BRIDGE = ROOT / "bin/rzr-event-bus-client.py"


class WatchtowerMonitorHomeMatrix(unittest.TestCase):
    def setUp(self):
        # AF_UNIX is limited to 104 bytes on macOS; keep private fixtures short.
        self.tmp = tempfile.TemporaryDirectory(prefix="h2-", dir="/tmp")
        self.root = Path(self.tmp.name).resolve()
        self.user = self.root / "user"; self.user.mkdir(mode=0o700)
        self.cwd = self.root / "cwd"; self.cwd.mkdir(mode=0o700)
        self.processes = []
        self.homes = set()

    def tearDown(self):
        # This cleanup is intentionally unconditional: failed assertions and
        # timeouts must not leave a daemon or AF_UNIX endpoint behind.
        for process in self.processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)
            for stream in (process.stdout, process.stderr):
                if stream: stream.close()
        for home in self.homes:
            self.assertFalse((home / "monitor.sock").exists(), f"surviving socket: {home}")
        self.tmp.cleanup()

    def env(self, bits=None):
        env = dict(os.environ, HOME=str(self.user), XDG_CONFIG_HOME=str(self.root / "xdg-decoy"))
        env.pop("ROZORO_HOME", None); env.pop("RZR_HOME", None)
        env.update(bits or {})
        return env

    def command(self, command, env, timeout=15):
        return subprocess.run(command, cwd=self.cwd, env=env, text=True,
                              capture_output=True, timeout=timeout)

    def wait_up(self, home, env):
        self.homes.add(home)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = self.command([sys.executable, str(MONITOR), "status", "--json"], env)
            if result.returncode == 0: return json.loads(result.stdout)
            time.sleep(.04)
        self.fail(f"daemon did not become healthy at {home}")

    def test_client_api_and_open_home_cover_P_L_B_E_D_R_T_X_and_override_mutant(self):
        rows = {
            "P": ({"ROZORO_HOME": "public"}, self.cwd / "public"),
            "L": ({"RZR_HOME": "legacy"}, self.cwd / "legacy"),
            "B": ({"ROZORO_HOME": "public", "RZR_HOME": "legacy"}, self.cwd / "public"),
            "E": ({"ROZORO_HOME": "", "RZR_HOME": "legacy"}, self.cwd / "legacy"),
            "D": ({}, self.user / ".rozoro"),
            "R": ({"ROZORO_HOME": "relative/home"}, self.cwd / "relative/home"),
            "T": ({"ROZORO_HOME": "~/tilde"}, self.user / "tilde"),
            "X": ({"ROZORO_HOME": "public", "XDG_CONFIG_HOME": str(self.root / "wrong")}, self.cwd / "public"),
        }
        old = Path.cwd()
        try:
            os.chdir(self.cwd)
            for cell, (bits, expected) in rows.items():
                with self.subTest(cell=cell), patch.dict(os.environ, self.env(bits), clear=True):
                    self.assertEqual(resolve_home(), expected)
                    path, fd = _open_home(None)
                    try: self.assertEqual(path, expected)
                    finally: os.close(fd)
                    self.assertEqual(expected.stat().st_mode & 0o777, 0o700)
            # O kills the mutant that consults environment before an API override.
            with patch.dict(os.environ, self.env({"ROZORO_HOME": "wrong"}), clear=True):
                explicit = self.root / "explicit"
                path, fd = _open_home(explicit)
                try: self.assertEqual(path, explicit)
                finally: os.close(fd)
        finally: os.chdir(old)

    def test_real_monitor_cli_start_status_stop_reset_obeys_public_precedence(self):
        chosen = self.cwd / "chosen"
        env = self.env({"ROZORO_HOME": "chosen", "RZR_HOME": "mutant-legacy"})
        started = self.command([sys.executable, str(MONITOR), "start"], env)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.homes.add(chosen)
        try:
            status = self.command([sys.executable, str(MONITOR), "status", "--json"], env)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["socket"], str(chosen / "monitor.sock"))
            self.assertFalse((self.cwd / "mutant-legacy/monitor.sock").exists())
            stopped = self.command([sys.executable, str(MONITOR), "stop"], env)
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
            reset = self.command([sys.executable, str(MONITOR), "reset", "--force"], env)
            self.assertEqual(reset.returncode, 0, reset.stderr)
            self.assertFalse((chosen / "monitor.db").exists())
        finally:
            # Detached start is not in self.processes, so use the real stop path
            # even after a failed assertion, then verify endpoint disappearance.
            self.command([sys.executable, str(MONITOR), "stop"], env)
            deadline = time.monotonic() + 3
            while (chosen / "monitor.sock").exists() and time.monotonic() < deadline: time.sleep(.03)

    def test_real_rozorod_parser_home_override_and_monitor_server_identity(self):
        explicit = self.root / "O-explicit"
        env = self.env({"ROZORO_HOME": str(self.root / "mutant-env")})
        process = subprocess.Popen([sys.executable, str(DAEMON), "--home", str(explicit)],
                                   cwd=self.cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        status = self.wait_up(explicit, self.env({"ROZORO_HOME": str(explicit)}))
        self.assertEqual(status["socket"], str(explicit / "monitor.sock"))
        self.assertFalse((self.root / "mutant-env/monitor.sock").exists())
        server = MonitorServer(explicit)
        try: self.assertEqual(server.home, explicit)
        finally:
            if getattr(server, "_home_fd", -1) >= 0:
                os.close(server._home_fd); server._home_fd = -1

    def test_real_bridge_boundary_daemonflow_and_socket_exchange_use_selected_home(self):
        home = self.cwd / "bridge-public"
        env = self.env({"ROZORO_HOME": "bridge-public", "RZR_HOME": "mutant-legacy"})
        process = subprocess.Popen([sys.executable, str(DAEMON), "--home", str(home)], cwd=self.cwd, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process); self.homes.add(home)
        deadline = time.monotonic() + 8
        while not (home / "monitor.sock").exists() and time.monotonic() < deadline:
            if process.poll() is not None: self.fail(process.stderr.read().decode())
            time.sleep(.04)
        self.assertTrue((home / "monitor.sock").is_socket())
        result = self.command([sys.executable, str(BRIDGE), "status", "--task", "task-h2"], env)
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertEqual(reply["task_id"], "task-h2")
        self.assertTrue((home / "watchtowers/.authority.lock").is_file())
        self.assertTrue((home / "monitor.sock").is_socket())
        self.assertFalse((self.cwd / "mutant-legacy/watchtowers").exists())


if __name__ == "__main__": unittest.main()
