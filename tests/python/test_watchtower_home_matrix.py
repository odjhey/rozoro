import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from lib.rozoro_monitor.client import resolve_home as client_resolve_home

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / ".agents/skills/watchtower-policy-snapshot/scripts/snapshot.py"
PROGRESS = ROOT / ".agents/skills/watchtower-progress-report/scripts/report.py"
LEDGER = ROOT / ".agents/skills/watchtower-attention-ledger/scripts/ledger.py"
MONITOR = ROOT / "bin/rzr-monitor.py"
EVENT_BRIDGE = ROOT / "bin/rzr-event-bus-client.py"


@contextmanager
def cwd(path: Path):
    old = Path.cwd(); os.chdir(path)
    try: yield
    finally: os.chdir(old)


class WatchtowerHomeMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        snapshot_path = runpy.run_path(str(SNAPSHOT))["normalized_path"]
        progress_path = runpy.run_path(str(PROGRESS))["normalized_path"]
        selected = lambda: os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") or "~/.rozoro"
        cls.normalizers = {
            "snapshot": lambda value=None: snapshot_path(selected() if value is None else value),
            "progress": lambda value=None: progress_path(selected() if value is None else value),
            "ledger": runpy.run_path(str(LEDGER))["resolve_home"],
            "monitor-client": client_resolve_home,
            "monitor": runpy.run_path(str(MONITOR))["home_path"],
        }

    def test_python_consumers_share_complete_home_precedence_and_normalization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); user_home = root / "user"; user_home.mkdir()
            cases = (
                ("public", "legacy", user_home / "public"),
                ("", "legacy", user_home / "legacy"),
                (None, "legacy", user_home / "legacy"),
                ("public", None, user_home / "public"),
                ("", "", user_home / ".rozoro"),
                (None, None, user_home / ".rozoro"),
                ("~/public", "legacy", user_home / "public"),
            )
            for consumer, function in self.normalizers.items():
                for public, legacy, expected in cases:
                    env = {"HOME": str(user_home), "XDG_CONFIG_HOME": str(root / "xdg")}
                    if public is not None: env["ROZORO_HOME"] = public
                    if legacy is not None: env["RZR_HOME"] = legacy
                    with self.subTest(consumer=consumer, public=public, legacy=legacy), patch.dict(os.environ, env, clear=True), cwd(user_home):
                        value = function(None) if consumer == "ledger" else function()
                        self.assertEqual(Path(value), expected)

    def test_explicit_and_relative_values_anchor_once_and_unresolved_user_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "home"; initial = root / "initial"; later = root / "later"
            home.mkdir(); initial.mkdir(); later.mkdir()
            for consumer in ("snapshot", "progress"):
                function = self.normalizers[consumer]
                with self.subTest(consumer=consumer), patch.dict(os.environ, {"HOME": str(home)}, clear=True), cwd(initial):
                    held = function("relative/path")
                    os.chdir(later)
                    self.assertEqual(held, initial / "relative/path")
                    self.assertEqual(function("~/explicit"), home / "explicit")
                    with self.assertRaisesRegex(Exception, "unresolved user path"):
                        function("~rozoro-no-such-user-129/path")
            with patch.dict(os.environ, {"HOME": str(home)}, clear=True), cwd(initial):
                self.assertEqual(self.normalizers["ledger"]("relative/path"), initial / "relative/path")
                self.assertEqual(self.normalizers["ledger"]("~/explicit"), home / "explicit")

    def test_snapshot_and_progress_main_select_real_environment_and_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); user_home = root / "user"; initial = root / "initial"
            user_home.mkdir(); initial.mkdir()
            cases = [
                ({"RZR_HOME": "legacy"}, initial / "legacy"),
                ({"ROZORO_HOME": "", "RZR_HOME": "legacy"}, initial / "legacy"),
                ({"ROZORO_HOME": "", "RZR_HOME": ""}, user_home / ".rozoro"),
                ({"RZR_HOME": "~/legacy"}, user_home / "legacy"),
            ]
            # A current-UID passwd entry exists on macOS and ordinary Linux.
            # The pinned uid-only container intentionally has none.
            try:
                import pwd
                username = pwd.getpwuid(os.getuid()).pw_name
            except KeyError:
                username = None
            if username:
                cases.append(({"RZR_HOME": f"~{username}/rzr-entrypoint-matrix"},
                              Path(pwd.getpwnam(username).pw_dir) / "rzr-entrypoint-matrix"))
            for env_bits, selected in cases:
                env = dict(os.environ, HOME=str(user_home), XDG_CONFIG_HOME=str(root / "xdg"))
                env.pop("ROZORO_HOME", None); env.pop("RZR_HOME", None); env.update(env_bits)
                (selected / "tasks").mkdir(parents=True, exist_ok=True)
                for script, args in ((SNAPSHOT, ["--repo-root", str(ROOT)]),
                                     (PROGRESS, ["--repo-root", str(ROOT), "--now", "2026-01-01T00:00:00Z"])):
                    with self.subTest(script=script.name, env=env_bits):
                        result = subprocess.run(["python3", str(script), *args], cwd=initial, env=env,
                                                text=True, capture_output=True, timeout=20)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertTrue(Path(result.stdout.strip()).is_relative_to(selected / "artifacts"))
            explicit = root / "explicit"
            env = dict(os.environ, HOME=str(user_home), ROZORO_HOME=str(root / "wrong"), RZR_HOME=str(root / "also-wrong"))
            for script, args in ((SNAPSHOT, ["--repo-root", str(ROOT)]),
                                 (PROGRESS, ["--repo-root", str(ROOT), "--tasks-root", str(initial), "--now", "2026-01-01T00:00:00Z"])):
                result = subprocess.run(["python3", str(script), *args, "--artifact-root", str(explicit)], cwd=initial,
                                        env=env, text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(Path(result.stdout.strip()).is_relative_to(explicit))
            bad = dict(os.environ, HOME=str(user_home), RZR_HOME="~rozoro-no-such-user-129/home")
            bad.pop("ROZORO_HOME", None)
            for script in (SNAPSHOT, PROGRESS):
                result = subprocess.run(["python3", str(script), "--repo-root", str(ROOT)], cwd=initial,
                                        env=bad, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0); self.assertNotIn("Traceback", result.stderr)

    def test_monitor_and_event_bridge_mains_select_home_without_test_selector(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "home"; initial = root / "initial"; home.mkdir(); initial.mkdir()
            cases = (({"RZR_HOME": "legacy"}, initial / "legacy"),
                     ({"ROZORO_HOME": "", "RZR_HOME": "legacy"}, initial / "legacy"),
                     ({"ROZORO_HOME": "public", "RZR_HOME": "legacy"}, initial / "public"),
                     ({"ROZORO_HOME": "", "RZR_HOME": ""}, home / ".rozoro"),
                     ({"RZR_HOME": "~/legacy"}, home / "legacy"))
            for bits, expected in cases:
                env = {"HOME": str(home), "XDG_CONFIG_HOME": str(root / "xdg"), **bits}
                with self.subTest(entry="monitor", bits=bits), patch.dict(os.environ, env, clear=True), cwd(initial):
                    ns = runpy.run_path(str(MONITOR)); seen = []
                    ns["main"].__globals__["health"] = lambda selected: seen.append(selected) or {"running": True}
                    with patch.object(sys, "argv", [str(MONITOR), "status", "--json"]), redirect_stdout(io.StringIO()):
                        self.assertEqual(ns["main"](), 0)
                    self.assertEqual(seen, [expected])
                with self.subTest(entry="event-bridge", bits=bits), patch.dict(os.environ, env, clear=True), cwd(initial):
                    ns = runpy.run_path(str(EVENT_BRIDGE)); seen = []
                    class Boundary:
                        def __init__(self, fd): pass
                        def __enter__(self): return self
                        def __exit__(self, *args): pass
                        def require_clean(self, driver): pass
                        def activate(self, driver): pass
                    class Flow:
                        def __init__(self, selected, fd): seen.append(selected)
                        def request(self, request): return {"authority": "active"}
                    globals_ = ns["main"].__globals__
                    globals_["_open_home"] = lambda raw, create=False: (Path(os.path.abspath(os.path.expanduser(raw))), os.open(initial, os.O_RDONLY))
                    globals_["AuthorityBoundary"] = Boundary; globals_["DaemonFlow"] = Flow
                    with patch.object(sys, "argv", [str(EVENT_BRIDGE), "authority-activate", "--driver", "d"]), redirect_stdout(io.StringIO()):
                        try: ns["main"]()
                        except Exception: pass
                    self.assertEqual(seen, [expected])

    def test_shell_library_and_doctor_use_the_same_selected_absolute_home(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "user"; initial = root / "initial"; home.mkdir(); initial.mkdir()
            cases = (("public", "legacy", initial / "public"), ("", "legacy", initial / "legacy"), ("", "", home / ".rozoro"), ("~/chosen", "legacy", home / "chosen"))
            for public, legacy, expected in cases:
                env = dict(os.environ, HOME=str(home), ROZORO_HOME=public, RZR_HOME=legacy, XDG_CONFIG_HOME=str(root / "xdg"))
                expected.mkdir(parents=True, exist_ok=True); expected.chmod(0o700)
                lib = subprocess.run(["bash", "-c", f'cd {initial!s}; source {ROOT}/bin/rzr-lib.sh; printf "%s" "$RZR_HOME"'], env=env, text=True, capture_output=True)
                self.assertEqual(lib.returncode, 0, lib.stderr); self.assertEqual(lib.stdout, str(expected))
                doctor = subprocess.run(["bash", str(ROOT / "bin/rzr-doctor.sh")], cwd=initial, env=env, text=True, capture_output=True)
                self.assertIn(f"home: {expected}", doctor.stdout)


if __name__ == "__main__": unittest.main()
