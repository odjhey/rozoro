import os
import runpy
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / ".agents/skills/watchtower-policy-snapshot/scripts/snapshot.py"
PROGRESS = ROOT / ".agents/skills/watchtower-progress-report/scripts/report.py"
LEDGER = ROOT / ".agents/skills/watchtower-attention-ledger/scripts/ledger.py"
MONITOR = ROOT / "bin/rzr-monitor.py"


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
