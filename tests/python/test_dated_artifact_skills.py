from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POLICY_SCRIPT = REPO / ".agents/skills/watchtower-policy-snapshot/scripts/snapshot.py"
REPORT_SCRIPT = REPO / ".agents/skills/watchtower-progress-report/scripts/report.py"
NOW = "2026-08-24T03:25:36.123456Z"


def handoff(turn: int, verdict: str, *, reason: str = "", pending: str = "none", needed: str = "none", did: str = "work") -> str:
    return "\n".join(
        [
            f"## turn {turn} — report",
            f"verdict:       {verdict}",
            f"reason:        {reason}",
            f"did:           {did}",
            f"pending:       {pending}",
            f"inputs-needed: {needed}",
            "artifacts:     none",
            "",
        ]
    )


class DatedArtifactSkillTests(unittest.TestCase):
    def run_script(self, script: Path, *args: str, env: dict[str, str] | None = None) -> Path:
        result = subprocess.run(
            ["python3", str(script), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return Path(result.stdout.strip())

    def assert_private_tree(self, run: Path) -> None:
        self.assertEqual(stat.S_IMODE(run.stat().st_mode), 0o700)
        for child in run.iterdir():
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o600, child)

    def test_policy_snapshot_captures_current_source_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "checkout"
            (checkout / "templates").mkdir(parents=True)
            source = checkout / "templates/watchtower.md"
            current = b"current working-tree policy\n"
            source.write_bytes(current)
            artifact_root = root / "artifacts"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *'HEAD:templates/watchtower.md'*) echo committedblob ;;\n"
                "  *'rev-parse HEAD'*) echo commitsha ;;\n"
                "  *'hash-object'*) echo currentblob ;;\n"
                "  *) exit 1 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            env = dict(os.environ, PATH=f"{fake_bin}:{os.environ.get('PATH', '')}")

            first = self.run_script(
                POLICY_SCRIPT,
                "--repo-root",
                str(checkout),
                "--artifact-root",
                str(artifact_root),
                "--now",
                NOW,
                env=env,
            )
            second = self.run_script(
                POLICY_SCRIPT,
                "--repo-root",
                str(checkout),
                "--artifact-root",
                str(artifact_root),
                "--now",
                NOW,
                env=env,
            )

            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, second.parent)
            self.assertEqual(first.parent.name, "2026-08-24")
            self.assertRegex(first.name, r"^20260824T032536\.123456Z-[0-9a-f]{8}$")
            self.assertEqual((first / "watchtower-policy.md").read_bytes(), current)
            metadata = json.loads((first / "metadata.json").read_text())
            self.assertEqual(metadata["schema"], "rozoro.watchtower-policy-snapshot/v1")
            self.assertEqual(metadata["source"]["repository_relative_path"], "templates/watchtower.md")
            self.assertFalse(metadata["source"]["matches_git_commit"])
            self.assertNotIn(str(checkout), (first / "metadata.json").read_text())
            self.assert_private_tree(first)

    def test_progress_report_separates_states_and_excludes_freeform_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tasks = root / "tasks"
            artifacts = root / "artifacts"
            tasks.mkdir(mode=0o700)
            secret = "ghp_DO_NOT_PERSIST_THIS_SENTINEL"

            fixtures = {
                "done-task": handoff(1, "done", did=f"finished {secret}"),
                "waiting-task": handoff(1, "waiting", reason="job runs", pending="consume result"),
                "blocked-task": handoff(1, "blocked", reason=f"blocked {secret}", pending="operator choice", needed=f"choose {secret}"),
                "action-task": handoff(1, "needs-action", reason="decision", pending="choice", needed="choose A or B"),
                "malformed-task": handoff(2, "blocked", reason="bad sequence", pending="choice", needed="operator input"),
            }
            for task_id, text in fixtures.items():
                task = tasks / task_id
                task.mkdir()
                (task / "handoff.md").write_text(text, encoding="utf-8")
                (task / "identity.json").write_text(json.dumps({"cwd": f"/private/{secret}"}), encoding="utf-8")
                (task / "session.json").write_text(json.dumps({"token": secret}), encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            (outside / "handoff.md").write_text(handoff(1, "done", did=secret), encoding="utf-8")
            (tasks / "unsafe-link").symlink_to(outside, target_is_directory=True)

            run = self.run_script(
                REPORT_SCRIPT,
                "--repo-root",
                str(REPO),
                "--tasks-root",
                str(tasks),
                "--artifact-root",
                str(artifacts),
                "--now",
                NOW,
            )
            report = (run / "report.md").read_text()
            evidence = json.loads((run / "evidence.json").read_text())
            metadata = json.loads((run / "metadata.json").read_text())
            all_artifact_text = "\n".join(path.read_text() for path in run.iterdir())

            self.assertEqual(metadata["schema"], "rozoro.watchtower-progress-report/v1")
            self.assertEqual(evidence["skipped_unsafe_or_invalid_entries"], 1)
            self.assertNotIn(secret, all_artifact_text)
            self.assertNotIn("/private/", all_artifact_text)
            self.assertIn("A `done` report is not acceptance", report)
            by_id = {task["task_id"]: set(task["classifications"]) for task in evidence["tasks"]}
            self.assertIn("reported-done-unverified", by_id["done-task"])
            self.assertIn("reported-active-runtime-unverified", by_id["waiting-task"])
            self.assertIn("blocker-or-failure", by_id["blocked-task"])
            self.assertIn("human-decision-needed", by_id["blocked-task"])
            self.assertIn("human-decision-needed", by_id["action-task"])
            self.assertEqual(by_id["malformed-task"], {"unknown-or-malformed"})
            self.assertNotIn("unsafe-link", by_id)
            self.assert_private_tree(run)

    def test_progress_runs_are_unique_and_task_root_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tasks = root / "tasks"
            tasks.mkdir()
            artifacts = root / "artifacts"
            args = (
                "--repo-root",
                str(REPO),
                "--tasks-root",
                str(tasks),
                "--artifact-root",
                str(artifacts),
                "--now",
                NOW,
            )
            first = self.run_script(REPORT_SCRIPT, *args)
            second = self.run_script(REPORT_SCRIPT, *args)
            self.assertNotEqual(first, second)

            linked = root / "linked-tasks"
            linked.symlink_to(tasks, target_is_directory=True)
            result = subprocess.run(
                [
                    "python3",
                    str(REPORT_SCRIPT),
                    "--repo-root",
                    str(REPO),
                    "--tasks-root",
                    str(linked),
                    "--artifact-root",
                    str(artifacts),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing symlink task root", result.stderr)


if __name__ == "__main__":
    unittest.main()
