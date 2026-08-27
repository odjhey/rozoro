"""H2 home-selection contract for the monitor, daemon, client, and bridge.

Matrix identities: P=public, L=legacy, B=both, E=empty public,
D=default, R=relative, T=tilde, O=explicit override, X=XDG decoy.
"""
import json
import os
import signal
import shutil
import socket
import subprocess
import threading
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
        self.started_at = time.time()
        self.preexisting_locks = {p.resolve() for p in ROOT.rglob("monitor.lock")}

    def tearDown(self):
        # Foreground children are unambiguously ours.
        for process in self.processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)
            for stream in (process.stdout, process.stderr):
                if stream: stream.close()
        # Detached `monitor start` loses its Popen handle. Discover every home
        # selected beneath this test's new private root (including precedence
        # mutants), but never inspect or signal a pre-existing user home.
        owned = []
        candidates = list(self.root.rglob("monitor.lock")) + list(ROOT.rglob("monitor.lock"))
        for lock in candidates:
            try:
                resolved = lock.resolve()
                record = json.loads(lock.read_text()); pid = record["pid"]
                if (resolved not in self.preexisting_locks and
                        lock.stat().st_mtime + 1 >= self.started_at and isinstance(pid, int)):
                    owned.append((lock.parent, pid))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for home, pid in owned:
            try: os.kill(pid, signal.SIGTERM)
            except ProcessLookupError: pass
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try: os.kill(pid, 0)
                except ProcessLookupError: break
                time.sleep(.03)
            else:
                os.kill(pid, signal.SIGKILL)
            self.homes.add(home)
            if home.is_relative_to(ROOT) and not home.is_relative_to(self.root):
                shutil.rmtree(home, ignore_errors=True)
        survivors = [str(p) for p in self.root.rglob("monitor.sock")]
        survivors += [str(p) for p in ROOT.rglob("monitor.sock")
                      if p.parent.joinpath("monitor.lock").resolve() not in self.preexisting_locks]
        self.assertEqual(survivors, [], f"surviving owned sockets: {survivors}")
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
                for cell, raw, explicit in (("O-relative", "explicit/relative", self.cwd / "explicit/relative"),
                                            ("O-tilde", "~/explicit-tilde", self.user / "explicit-tilde")):
                    with self.subTest(cell=cell):
                        path, fd = _open_home(raw)
                        try: self.assertEqual(path, explicit)
                        finally: os.close(fd)
            # A real passwd expansion row kills expand-$HOME-only mutants.
            import pwd
            username = pwd.getpwuid(os.getuid()).pw_name
            account = Path(pwd.getpwnam(username).pw_dir)
            with patch.dict(os.environ, self.env(), clear=True):
                self.assertEqual(resolve_home(f"~{username}/.rozoro-h2-probe"), account / ".rozoro-h2-probe")
                (account / ".rozoro-h2-probe").rmdir()
        finally: os.chdir(old)

    def test_real_monitor_cli_start_status_stop_reset_complete_matrix(self):
        rows = {
            "P": ({"ROZORO_HOME": "mp"}, self.cwd / "mp"),
            "L": ({"RZR_HOME": "ml"}, self.cwd / "ml"),
            "B": ({"ROZORO_HOME": "mb", "RZR_HOME": "decoy-b"}, self.cwd / "mb"),
            "E": ({"ROZORO_HOME": "", "RZR_HOME": "me"}, self.cwd / "me"),
            "D": ({}, self.user / ".rozoro"),
            "R": ({"ROZORO_HOME": "mr/child"}, self.cwd / "mr/child"),
            "T": ({"ROZORO_HOME": "~/mt"}, self.user / "mt"),
            "X": ({"ROZORO_HOME": "mx", "XDG_CONFIG_HOME": str(self.root / "xdg-wrong")}, self.cwd / "mx"),
        }
        for cell, (bits, chosen) in rows.items():
            env = self.env(bits); self.homes.add(chosen)
            try:
                started = self.command([sys.executable, str(MONITOR), "start"], env)
                self.assertEqual(started.returncode, 0, f"{cell}: {started.stderr}")
                status = self.command([sys.executable, str(MONITOR), "status", "--json"], env)
                self.assertEqual(status.returncode, 0, f"{cell}: {status.stderr}")
                self.assertEqual(json.loads(status.stdout)["socket"], str(chosen / "monitor.sock"))
            finally:
                self.command([sys.executable, str(MONITOR), "stop"], env)
            if cell == "B": self.assertFalse((self.cwd / "decoy-b/monitor.sock").exists())
            if cell == "X": self.assertFalse((self.root / "xdg-wrong/monitor.sock").exists())
        reset_home = self.cwd / "reset"
        reset_home.mkdir(mode=0o700); (reset_home / "monitor.db").write_text("fixture")
        reset = self.command([sys.executable, str(MONITOR), "reset", "--force"], self.env({"ROZORO_HOME": "reset"}))
        self.assertEqual(reset.returncode, 0, reset.stderr); self.assertFalse((reset_home / "monitor.db").exists())

    def test_real_rozorod_parser_environment_and_explicit_relative_tilde_rows(self):
        rows = (("P", None, {"ROZORO_HOME": "dp", "RZR_HOME": "wrong"}, self.cwd / "dp"),
                ("L", None, {"RZR_HOME": "dl"}, self.cwd / "dl"),
                ("O-relative", "do/relative", {"ROZORO_HOME": "wrong"}, self.cwd / "do/relative"),
                ("O-tilde", "~/do-tilde", {"ROZORO_HOME": "wrong"}, self.user / "do-tilde"))
        for cell, override, bits, expected in rows:
            command = [sys.executable, str(DAEMON)]
            if override is not None: command += ["--home", override]
            process = subprocess.Popen(command, cwd=self.cwd, env=self.env(bits),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.processes.append(process)
            status = self.wait_up(expected, self.env({"ROZORO_HOME": str(expected)}))
            self.assertEqual(status["socket"], str(expected / "monitor.sock"), cell)
            process.send_signal(signal.SIGTERM); self.assertEqual(process.wait(timeout=3), 0)
        self.assertFalse((self.cwd / "wrong/monitor.sock").exists())
        server = MonitorServer(self.cwd / "server-explicit")
        try: self.assertEqual(server.home, self.cwd / "server-explicit")
        finally:
            if getattr(server, "_home_fd", -1) >= 0:
                os.close(server._home_fd); server._home_fd = -1

    def test_real_bridge_failure_matrix_and_correlated_timeout_cleanup(self):
        rows = (("P", {"ROZORO_HOME": "bp"}, self.cwd / "bp"),
                ("L", {"RZR_HOME": "bl"}, self.cwd / "bl"),
                ("B", {"ROZORO_HOME": "bb", "RZR_HOME": "wrong"}, self.cwd / "bb"),
                ("E", {"ROZORO_HOME": "", "RZR_HOME": "be"}, self.cwd / "be"),
                ("D", {}, self.user / ".rozoro"),
                ("R", {"ROZORO_HOME": "br/child"}, self.cwd / "br/child"),
                ("T", {"ROZORO_HOME": "~/bt"}, self.user / "bt"),
                ("X", {"ROZORO_HOME": "bx", "XDG_CONFIG_HOME": str(self.root / "xdg-bridge")}, self.cwd / "bx"))
        for cell, bits, selected in rows:
            selected.mkdir(parents=True, mode=0o700); selected.chmod(0o700)
            failed = self.command([sys.executable, str(BRIDGE), "status", "--task", "missing"], self.env(bits))
            self.assertEqual(failed.returncode, 2, cell)
            self.assertIn(str(selected / "monitor.sock"), failed.stderr)
            self.assertTrue((selected / "watchtowers").is_dir())
        # A private AF_UNIX peer accepts the real DaemonFlow request but never
        # replies. This is the explicit bridge timeout row, with forced cleanup.
        home = self.cwd / "bridge-timeout"; home.mkdir(mode=0o700); self.homes.add(home)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); connection = None
        listener.bind(str(home / "monitor.sock")); os.chmod(home / "monitor.sock", 0o600); listener.listen()
        release = threading.Event()
        def stall():
            nonlocal connection
            connection, _ = listener.accept(); connection.recv(65536); release.wait(5)
        thread = threading.Thread(target=stall); thread.start()
        try:
            timed = self.command([sys.executable, str(BRIDGE), "status", "--task", "timeout"],
                                 self.env({"ROZORO_HOME": str(home)}), timeout=8)
            self.assertEqual(timed.returncode, 2); self.assertIn("timed out", timed.stderr)
        finally:
            release.set()
            if connection is not None: connection.close()
            listener.close(); thread.join(timeout=2)
            try: (home / "monitor.sock").unlink()
            except FileNotFoundError: pass

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
