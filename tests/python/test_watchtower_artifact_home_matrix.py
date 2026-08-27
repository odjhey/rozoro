import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / ".agents/skills/watchtower-policy-snapshot/scripts/snapshot.py"
PROGRESS = ROOT / ".agents/skills/watchtower-progress-report/scripts/report.py"
NOW = "2026-01-02T03:04:05Z"


@contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class WatchtowerArtifactHomeMatrixTests(unittest.TestCase):
    def run_cli(self, script, initial, env, *args):
        return subprocess.run(
            [sys.executable, str(script), "--repo-root", str(ROOT), "--now", NOW, *map(str, args)],
            cwd=initial, env=env, text=True, capture_output=True, timeout=30,
        )

    def assert_snapshot(self, run):
        self.assertEqual(run.returncode, 0, run.stderr)
        artifact = Path(run.stdout.strip())
        self.assertTrue((artifact / "watchtower-policy.md").is_file())
        metadata = json.loads((artifact / "metadata.json").read_text())
        self.assertEqual(metadata["artifact_type"], "watchtower-policy-snapshot")
        self.assertTrue((artifact / "missions" / "delivery.md").is_file())
        return artifact

    def assert_progress(self, run, tasks, explicit):
        self.assertEqual(run.returncode, 0, run.stderr)
        artifact = Path(run.stdout.strip())
        for name in ("report.md", "evidence.json", "metadata.json"):
            self.assertTrue((artifact / name).is_file(), name)
        evidence = json.loads((artifact / "evidence.json").read_text())
        source = evidence["source"]
        info = tasks.stat()
        expected_id = "fs-" + __import__("hashlib").sha256(f"{info.st_dev}:{info.st_ino}".encode()).hexdigest()[:20]
        self.assertEqual(source["root_id"], expected_id)
        self.assertEqual(source["selection"], "explicit-override" if explicit else "default-rozoro-home")
        return artifact

    def test_real_mains_cover_P_L_B_E_D_R_T_X(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "user"; initial = root / "initial"
            home.mkdir(); initial.mkdir()
            rows = {
                "P": ({"ROZORO_HOME": "public"}, initial / "public"),
                "L": ({"RZR_HOME": "legacy"}, initial / "legacy"),
                "B": ({"ROZORO_HOME": "public", "RZR_HOME": "ignored"}, initial / "public"),
                "E": ({"ROZORO_HOME": "", "RZR_HOME": "legacy"}, initial / "legacy"),
                "D-unset": ({}, home / ".rozoro"),
                "D-empty": ({"ROZORO_HOME": "", "RZR_HOME": ""}, home / ".rozoro"),
                "R": ({"ROZORO_HOME": "relative/home"}, initial / "relative/home"),
                "T": ({"ROZORO_HOME": "~/tilde-home"}, home / "tilde-home"),
                "X": ({"ROZORO_HOME": "public-x", "XDG_CONFIG_HOME": str(root / "decoy")}, initial / "public-x"),
            }
            for cell, (bits, selected) in rows.items():
                tasks = selected / "tasks"; tasks.mkdir(parents=True, exist_ok=True)
                env = {"HOME": str(home), **bits}
                with self.subTest(cell=cell, main="snapshot"):
                    artifact = self.assert_snapshot(self.run_cli(SNAPSHOT, initial, env))
                    self.assertTrue(artifact.is_relative_to(selected / "artifacts"))
                with self.subTest(cell=cell, main="progress"):
                    artifact = self.assert_progress(self.run_cli(PROGRESS, initial, env), tasks, False)
                    self.assertTrue(artifact.is_relative_to(selected / "artifacts"))

    def test_O_real_overrides_are_independent_relative_and_tilde(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "user"; initial = root / "initial"
            home.mkdir(); initial.mkdir()
            wrong = root / "wrong"; (wrong / "tasks").mkdir(parents=True)
            env = {"HOME": str(home), "ROZORO_HOME": str(wrong)}

            snapshot = self.assert_snapshot(self.run_cli(SNAPSHOT, initial, env, "--artifact-root", "relative-snap"))
            self.assertTrue(snapshot.is_relative_to(initial / "relative-snap"))
            tilde_snapshot = self.assert_snapshot(self.run_cli(SNAPSHOT, initial, env, "--artifact-root", "~/tilde-snap"))
            self.assertTrue(tilde_snapshot.is_relative_to(home / "tilde-snap"))

            relative_tasks = initial / "relative-tasks"; relative_tasks.mkdir()
            tilde_tasks = home / "tilde-tasks"; tilde_tasks.mkdir()
            cases = (
                (["--tasks-root", "relative-tasks"], relative_tasks, wrong / "artifacts", True),
                (["--artifact-root", "relative-artifacts"], wrong / "tasks", initial / "relative-artifacts", False),
                (["--tasks-root", "relative-tasks", "--artifact-root", "relative-both"], relative_tasks, initial / "relative-both", True),
                (["--tasks-root", "~/tilde-tasks", "--artifact-root", "~/tilde-both"], tilde_tasks, home / "tilde-both", True),
            )
            for args, tasks, artifacts, explicit_tasks in cases:
                with self.subTest(args=args):
                    artifact = self.assert_progress(self.run_cli(PROGRESS, initial, env, *args), tasks, explicit_tasks)
                    self.assertTrue(artifact.is_relative_to(artifacts))

    def test_real_mains_hold_resolved_roots_after_cwd_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "home"; initial = root / "initial"; later = root / "later"
            home.mkdir(); initial.mkdir(); later.mkdir()
            (initial / "tasks").mkdir()
            for script, expected_calls in ((SNAPSHOT, 3), (PROGRESS, 4)):
                main = runpy.run_path(str(script))["main"]
                production_globals = main.__globals__
                original = production_globals["normalized_path"]
                resolved = []
                def moving_normalizer(value):
                    result = original(value)
                    resolved.append(result)
                    if len(resolved) == expected_calls:
                        os.chdir(later)
                    return result
                argv = [str(script), "--repo-root", str(ROOT), "--artifact-root", "artifacts", "--now", NOW]
                if script == PROGRESS:
                    argv += ["--tasks-root", "tasks"]
                with self.subTest(script=script.name), cwd(initial), patch.dict(os.environ, {"HOME": str(home)}, clear=True), patch.object(sys, "argv", argv), patch.dict(production_globals, {"normalized_path": moving_normalizer}), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(), 0)
                    artifact = Path(output.getvalue().strip())
                    self.assertEqual(len(resolved), expected_calls)
                    expected_paths = ([ROOT, home / ".rozoro", initial / "artifacts"] if script == SNAPSHOT else
                                      [ROOT, home / ".rozoro", initial / "tasks", initial / "artifacts"])
                    self.assertEqual(resolved, expected_paths)
                    self.assertTrue(artifact.is_relative_to(initial / "artifacts"))
                    self.assertFalse((later / "artifacts").exists())
                    if script == PROGRESS:
                        evidence = json.loads((artifact / "evidence.json").read_text())
                        info = (initial / "tasks").stat()
                        expected = "fs-" + __import__("hashlib").sha256(f"{info.st_dev}:{info.st_ino}".encode()).hexdigest()[:20]
                        self.assertEqual(evidence["source"]["root_id"], expected)

    def test_unresolved_home_or_override_creates_no_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "home"; initial = root / "initial"
            home.mkdir(); initial.mkdir()
            bad = "~rozoro-no-such-user-h6/artifacts"
            valid_tasks = root / "valid-tasks"
            task = valid_tasks / "valid-task"; task.mkdir(parents=True)
            (task / "identity.json").write_text("{}\n")
            (task / "session.json").write_text("{}\n")
            (task / "handoff.md").write_text(
                "## turn 1 — complete\nverdict:       done\ndid:           test\npending:       none\n"
                "inputs-needed: none\nartifacts:     none\n"
            )
            cases = (
                (SNAPSHOT, {"HOME": str(home), "ROZORO_HOME": bad}, []),
                (PROGRESS, {"HOME": str(home), "ROZORO_HOME": bad}, []),
                (SNAPSHOT, {"HOME": str(home)}, ["--artifact-root", bad]),
                (PROGRESS, {"HOME": str(home)}, ["--artifact-root", bad, "--tasks-root", bad]),
                (PROGRESS, {"HOME": str(home)}, ["--tasks-root", str(valid_tasks), "--artifact-root", bad]),
            )
            for script, env, args in cases:
                with self.subTest(script=script.name, args=args):
                    result = self.run_cli(script, initial, env, *args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse(any(root.rglob("watchtower-policy-snapshots")))
                    self.assertFalse(any(root.rglob("watchtower-progress-reports")))

    def test_forced_write_failures_leave_no_fixture_residue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve(); home = root / "home"; initial = root / "initial"
            home.mkdir(); initial.mkdir()
            tasks = root / "tasks"; tasks.mkdir()
            for script in (SNAPSHOT, PROGRESS):
                artifact_root = root / f"failed-{script.stem}"
                main = runpy.run_path(str(script))["main"]
                production_globals = main.__globals__
                safe_directory = production_globals["SafeDirectory"]
                argv = [str(script), "--repo-root", str(ROOT), "--artifact-root", str(artifact_root), "--now", NOW]
                if script == PROGRESS:
                    argv += ["--tasks-root", str(tasks)]
                with self.subTest(script=script.name), cwd(initial), patch.dict(os.environ, {"HOME": str(home)}, clear=True), patch.object(sys, "argv", argv), patch.object(safe_directory, "write_exclusive", side_effect=OSError("forced write failure")):
                    with self.assertRaisesRegex(SystemExit, "cannot create safe artifact: forced write failure"):
                        main()
                category = "watchtower-policy-snapshots" if script == SNAPSHOT else "watchtower-progress-reports"
                runs = list((artifact_root / category).glob("*/*"))
                self.assertEqual(len(runs), 1)
                self.assertTrue(runs[0].is_dir())
                self.assertEqual(list(runs[0].iterdir()), [])
                # The product's failed reservation is observed above.  This
                # test owns the root, so remove only its fixture and prove it
                # cannot pollute a later matrix cell.
                shutil.rmtree(artifact_root)
                self.assertFalse(artifact_root.exists())


if __name__ == "__main__":
    unittest.main()
