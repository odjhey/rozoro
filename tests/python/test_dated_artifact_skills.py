from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from lib.rozoro_artifacts.safe_fs import SafeDirectory

REPO = Path(__file__).resolve().parents[2]
POLICY_SCRIPT = REPO / ".agents/skills/watchtower-policy-snapshot/scripts/snapshot.py"
REPORT_SCRIPT = REPO / ".agents/skills/watchtower-progress-report/scripts/report.py"
PI_LAUNCHER_BYTES = (REPO / "bin/rzr-pi-watchtower.sh").read_bytes()
CLAUDE_LAUNCHER_BYTES = (REPO / "bin/rzr-claude-watchtower.sh").read_bytes()
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
    def test_policy_snapshot_emits_launcher_contract_metadata(self) -> None:
        claude_script = REPO / ".claude/skills/watchtower-policy-snapshot/scripts/snapshot.py"
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary).resolve() / "artifacts"
            runs = [
                self.run_script(POLICY_SCRIPT, "--repo-root", str(REPO), "--artifact-root", str(artifact_root), "--now", NOW),
                self.run_script(claude_script, "--repo-root", str(REPO), "--artifact-root", str(artifact_root), "--now", NOW),
            ]
            expected_sha = hashlib.sha256(PI_LAUNCHER_BYTES).hexdigest()
            for run in runs:
                metadata = json.loads((run / "metadata.json").read_text())
                coverage = metadata["harness_coverage"]["pi"]
                self.assertEqual(coverage["status"], "captured")
                self.assertEqual(coverage["launcher"], "bin/rzr-pi-watchtower.sh")
                self.assertEqual(coverage["launcher_sha256"], expected_sha)

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
        for directory in (run, run.parent, run.parent.parent, run.parent.parent.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700, directory)
        for child in run.rglob("*"):
            expected = 0o700 if child.is_dir() else 0o600
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), expected, child)

    def test_policy_snapshot_captures_current_source_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            (checkout / "templates/missions").mkdir(parents=True)
            (checkout / "bin").mkdir()
            source = checkout / "templates/watchtower.md"
            current = b"current working-tree policy\n"
            source.write_bytes(current)
            mission_bytes = b"current delivery mission policy\n"
            triage_bytes = b"current triage mission policy\n"
            (checkout / "templates/missions/delivery.md").write_bytes(mission_bytes)
            (checkout / "templates/missions/triage.md").write_bytes(triage_bytes)
            (checkout / "bin/rzr-pi-watchtower.sh").write_bytes(PI_LAUNCHER_BYTES)
            (checkout / "bin/rzr-claude-watchtower.sh").write_bytes(CLAUDE_LAUNCHER_BYTES)
            artifact_root = root / "artifacts"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *'HEAD:templates/missions/delivery.md'*) printf '%040d\\n' 4 ;;\n"
                "  *'HEAD:templates/missions/triage.md'*) printf '%040d\\n' 5 ;;\n"
                "  *'HEAD:templates/watchtower.md'*) printf '%040d\\n' 2 ;;\n"
                "  *'rev-parse HEAD'*) printf '%040d\\n' 1 ;;\n"
                "  *'hash-object'*) printf '%040d\\n' 3 ;;\n"
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
            self.assertEqual((first / "missions/delivery.md").read_bytes(), mission_bytes)
            self.assertEqual((first / "missions/triage.md").read_bytes(), triage_bytes)
            metadata = json.loads((first / "metadata.json").read_text())
            self.assertEqual(metadata["schema"], "rozoro.watchtower-policy-snapshot/v9")
            self.assertEqual(metadata["source"]["repository_relative_path"], "templates/watchtower.md")
            self.assertEqual(metadata["source"]["applies_to_harnesses"], ["pi"])
            self.assertEqual(metadata["default_mission"], "delivery")
            mission_meta = metadata["missions"]["templates/missions/delivery.md"]
            self.assertEqual(mission_meta["mission"], "delivery")
            self.assertEqual(mission_meta["sha256"], hashlib.sha256(mission_bytes).hexdigest())
            self.assertEqual(
                mission_meta["composed_policy_sha256"],
                hashlib.sha256(current + mission_bytes).hexdigest(),
            )
            self.assertFalse(mission_meta["matches_git_commit"])
            self.assertEqual(metadata["files"]["missions/delivery.md"]["bytes"], len(mission_bytes))
            triage_meta = metadata["missions"]["templates/missions/triage.md"]
            self.assertEqual(triage_meta["sha256"], hashlib.sha256(triage_bytes).hexdigest())
            self.assertEqual(triage_meta["composed_policy_sha256"], hashlib.sha256(current + triage_bytes).hexdigest())
            self.assertEqual(metadata["files"]["missions/triage.md"]["bytes"], len(triage_bytes))
            self.assertEqual(metadata["harness_coverage"]["pi"]["status"], "captured")
            self.assertEqual(metadata["harness_coverage"]["claude"]["status"], "unverified-no-consumed-policy-args-array")
            self.assertEqual(metadata["harness_coverage"]["validation"], "exact-shipped-pi-launcher-sha256-plus-grammar-v2")
            self.assertEqual(metadata["harness_coverage"]["mission_sources"]["operator_status"], "not-captured")
            self.assertEqual(metadata["git_provenance"]["status"], "verified")
            self.assertFalse(metadata["source"]["matches_git_commit"])
            self.assertNotIn(str(checkout), (first / "metadata.json").read_text())
            self.assert_private_tree(first)

            (checkout / "bin/rzr-pi-watchtower.sh").write_text(
                "args=(--approve)\n# --append-system-prompt $ROOT/templates/watchtower.md\nexec env ROZORO_WATCHTOWER=1 pi \"${args[@]}\" \"$@\"\n",
                encoding="utf-8",
            )
            substring_only = subprocess.run(
                [
                    "python3",
                    str(POLICY_SCRIPT),
                    "--repo-root",
                    str(checkout),
                    "--artifact-root",
                    str(artifact_root),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(substring_only.returncode, 0)
            self.assertIn("strict shipped launcher contract", substring_only.stderr)

    def test_policy_coverage_requires_policy_on_array_consumed_by_pi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            (checkout / "templates/missions").mkdir(parents=True)
            (checkout / "bin").mkdir()
            (checkout / "templates/watchtower.md").write_text("policy\n", encoding="utf-8")
            (checkout / "templates/missions/delivery.md").write_text("mission\n", encoding="utf-8")
            (checkout / "bin/rzr-claude-watchtower.sh").write_text(
                'args=(--settings overlay.json)\nexec "$CLAUDE_BIN" "${args[@]}"\n', encoding="utf-8"
            )
            launchers = {
                "false-only-assignment": (
                    "if false; then\n"
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "fi\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "uncalled-function": (
                    "configure_args() {\n"
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "}\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "echo-pi-decoy": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    'echo pi "${args[@]}"\n'
                ),
                "dead-invocation": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "if false; then\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                    "fi\n"
                ),
                "scalar-assignment": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "args=--approve\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "unset-array": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "unset args\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "indexed-assignment": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "args[0]=--approve\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "eval-unset": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "eval 'unset args'\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "source-mutator": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "source ./mutate-args.sh\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "dot-mutator": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    ". ./mutate-args.sh\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "called-function-mutator": (
                    "mutate_args() { unset args; }\n"
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "mutate_args\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "command-substitution-eval": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "eval \"$(printf 'unset args')\"\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "reassigned": (
                    'if false; then args=(--append-system-prompt "$ROOT/templates/watchtower.md"); fi\n'
                    "args=(--approve)\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"\n'
                ),
                "unused-array": (
                    'args=(--append-system-prompt "$ROOT/templates/watchtower.md")\n'
                    "other=(--approve)\n"
                    'exec env ROZORO_WATCHTOWER=1 pi "${other[@]}" "$@"\n'
                ),
            }
            for name, launcher in launchers.items():
                with self.subTest(name=name):
                    (checkout / "bin/rzr-pi-watchtower.sh").write_text(launcher, encoding="utf-8")
                    artifact_root = root / f"artifacts-{name}"
                    result = subprocess.run(
                        [
                            "python3",
                            str(POLICY_SCRIPT),
                            "--repo-root",
                            str(checkout),
                            "--artifact-root",
                            str(artifact_root),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("strict shipped launcher contract", result.stderr)
                    self.assertFalse(artifact_root.exists())

    def test_policy_git_provenance_becomes_indeterminate_on_repo_path_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            held = root / "checkout-held"
            (checkout / "templates/missions").mkdir(parents=True)
            (checkout / "bin").mkdir()
            policy = b"held policy bytes\n"
            (checkout / "templates/watchtower.md").write_bytes(policy)
            (checkout / "templates/missions/delivery.md").write_bytes(b"held mission bytes\n")
            (checkout / "bin/rzr-pi-watchtower.sh").write_bytes(PI_LAUNCHER_BYTES)
            (checkout / "bin/rzr-claude-watchtower.sh").write_bytes(CLAUDE_LAUNCHER_BYTES)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "mv \"$SWAP_REPO\" \"$SWAP_HELD\"\n"
                "mkdir \"$SWAP_REPO\"\n"
                "echo forged-git-output\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            env = dict(
                os.environ,
                PATH=f"{fake_bin}:{os.environ.get('PATH', '')}",
                SWAP_REPO=str(checkout),
                SWAP_HELD=str(held),
            )
            run = self.run_script(
                POLICY_SCRIPT,
                "--repo-root",
                str(checkout),
                "--artifact-root",
                str(root / "artifacts"),
                "--now",
                NOW,
                env=env,
            )
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertEqual((run / "watchtower-policy.md").read_bytes(), policy)
            self.assertEqual(metadata["git_provenance"]["status"], "indeterminate")
            self.assertIn("identity-mismatch-after-read", metadata["git_provenance"]["reason"])
            self.assertIsNone(metadata["source"]["git_commit"])
            self.assertIsNone(metadata["source"]["git_blob_at_commit"])
            self.assertIsNone(metadata["source"]["git_blob_current"])
            self.assertIsNone(metadata["source"]["matches_git_commit"])

    def test_policy_git_provenance_rejects_successful_empty_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            checkout = root / "checkout"
            (checkout / "templates/missions").mkdir(parents=True)
            (checkout / "bin").mkdir()
            (checkout / "templates/watchtower.md").write_text("policy\n", encoding="utf-8")
            (checkout / "templates/missions/delivery.md").write_text("mission\n", encoding="utf-8")
            (checkout / "bin/rzr-pi-watchtower.sh").write_bytes(PI_LAUNCHER_BYTES)
            (checkout / "bin/rzr-claude-watchtower.sh").write_bytes(CLAUDE_LAUNCHER_BYTES)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            env = dict(os.environ, PATH=f"{fake_bin}:{os.environ.get('PATH', '')}")
            run = self.run_script(
                POLICY_SCRIPT,
                "--repo-root",
                str(checkout),
                "--artifact-root",
                str(root / "artifacts"),
                "--now",
                NOW,
                env=env,
            )
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertEqual(metadata["git_provenance"]["status"], "indeterminate")
            self.assertIn("git-read-failed", metadata["git_provenance"]["reason"])
            self.assertIn("empty-or-invalid-object-id", metadata["git_provenance"]["reason"])
            for field in ("git_commit", "git_blob_at_commit", "git_blob_current", "matches_git_commit"):
                self.assertIsNone(metadata["source"][field], field)

    def test_report_repo_override_cannot_execute_another_checkout_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            malicious = root / "malicious"
            parser_dir = malicious / "lib/rozoro_monitor"
            parser_dir.mkdir(parents=True)
            sentinel = root / "executed"
            (parser_dir / "handoff.py").write_text(
                "from pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('executed')\n",
                encoding="utf-8",
            )
            tasks = root / "tasks"
            tasks.mkdir()
            output = root / "artifacts"
            result = subprocess.run(
                [
                    "python3",
                    str(REPORT_SCRIPT),
                    "--repo-root",
                    str(malicious),
                    "--tasks-root",
                    str(tasks),
                    "--artifact-root",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must identify the checkout that owns this skill", result.stderr)
            self.assertFalse(sentinel.exists())
            self.assertFalse(output.exists())

    def test_progress_report_separates_states_and_excludes_freeform_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
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

            self.assertEqual(metadata["schema"], "rozoro.watchtower-progress-report/v2")
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

    def test_progress_report_gates_unsafe_malformed_and_acknowledged_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            tasks = root / "tasks"
            artifacts = root / "artifacts"
            tasks.mkdir(mode=0o700)

            def task(task_id: str, report: str) -> Path:
                folder = tasks / task_id
                folder.mkdir()
                (folder / "handoff.md").write_text(report, encoding="utf-8")
                (folder / "identity.json").write_text("{}", encoding="utf-8")
                (folder / "session.json").write_text("{}", encoding="utf-8")
                return folder

            malformed_identity = task("malformed-identity", handoff(1, "done"))
            (malformed_identity / "identity.json").write_text("{", encoding="utf-8")
            malformed_session = task("malformed-session", handoff(1, "blocked", reason="blocked", pending="input", needed="choice"))
            (malformed_session / "session.json").write_text("[]", encoding="utf-8")
            missing_identity = task("missing-identity", handoff(1, "done"))
            (missing_identity / "identity.json").unlink()
            missing_session = task("missing-session", handoff(1, "blocked", reason="blocked", pending="input", needed="choice"))
            (missing_session / "session.json").unlink()

            dangling_identity = task("dangling-identity", handoff(1, "done"))
            (dangling_identity / "identity.json").unlink()
            (dangling_identity / "identity.json").symlink_to(root / "does-not-exist-identity")
            dangling_session = task("dangling-session", handoff(1, "blocked", reason="blocked", pending="input", needed="choice"))
            (dangling_session / "session.json").unlink()
            (dangling_session / "session.json").symlink_to(root / "does-not-exist-session")
            dangling_handoff = task("dangling-handoff", handoff(1, "done"))
            (dangling_handoff / "handoff.md").unlink()
            (dangling_handoff / "handoff.md").symlink_to(root / "does-not-exist-handoff")
            dangling_ack = task("dangling-ack", handoff(1, "done"))
            (dangling_ack / ".acked-blocks-v2").symlink_to(root / "does-not-exist-ack")

            acked_done = task("acked-done", handoff(1, "done"))
            (acked_done / ".acked-blocks-v2").write_text("1\n", encoding="utf-8")
            acked_blocked = task("acked-blocked", handoff(1, "blocked", reason="blocked", pending="input", needed="choice"))
            (acked_blocked / ".acked-blocks-v2").write_text("1\n", encoding="utf-8")
            partial = task(
                "partially-acked",
                handoff(1, "blocked", reason="old blocker", pending="input", needed="choice") + handoff(2, "done"),
            )
            (partial / ".acked-blocks-v2").write_text("1\n", encoding="utf-8")

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
            evidence = json.loads((run / "evidence.json").read_text())
            records = {record["task_id"]: record for record in evidence["tasks"]}
            classes = {task_id: set(record["classifications"]) for task_id, record in records.items()}

            for task_id in ("malformed-identity", "malformed-session", "missing-identity", "missing-session", "dangling-identity", "dangling-session", "dangling-handoff", "dangling-ack"):
                self.assertEqual(classes[task_id], {"unknown-or-malformed"}, task_id)
            self.assertEqual(records["dangling-identity"]["identity_json"], "unsafe")
            self.assertEqual(records["dangling-session"]["session_json"], "unsafe")
            self.assertEqual(records["dangling-handoff"]["handoff"]["file_state"], "unsafe")
            self.assertEqual(records["dangling-ack"]["ack_cursor_files"]["v2"], "unsafe")
            self.assertEqual(classes["acked-done"], {"acknowledged-report-no-current-outcome"})
            self.assertEqual(classes["acked-blocked"], {"acknowledged-report-no-current-outcome"})
            self.assertEqual(classes["partially-acked"], {"reported-done-unverified"})

    def test_roots_fail_closed_on_missing_and_symlinked_ancestors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            real = root / "real"
            tasks = real / "tasks"
            tasks.mkdir(parents=True)
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)

            missing_result = subprocess.run(
                [
                    "python3",
                    str(REPORT_SCRIPT),
                    "--repo-root",
                    str(REPO),
                    "--tasks-root",
                    str(root / "missing-tasks"),
                    "--artifact-root",
                    str(root / "missing-output"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(missing_result.returncode, 0)
            self.assertIn("required directory does not exist", missing_result.stderr)
            self.assertFalse((root / "missing-output").exists())

            task_alias_result = subprocess.run(
                [
                    "python3",
                    str(REPORT_SCRIPT),
                    "--repo-root",
                    str(REPO),
                    "--tasks-root",
                    str(alias / "tasks"),
                    "--artifact-root",
                    str(root / "task-alias-output"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(task_alias_result.returncode, 0)
            self.assertIn("symlink", task_alias_result.stderr)
            self.assertFalse((root / "task-alias-output").exists())

            artifact_alias_result = subprocess.run(
                [
                    "python3",
                    str(REPORT_SCRIPT),
                    "--repo-root",
                    str(REPO),
                    "--tasks-root",
                    str(tasks),
                    "--artifact-root",
                    str(alias / "artifacts"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(artifact_alias_result.returncode, 0)
            self.assertIn("symlink", artifact_alias_result.stderr)
            self.assertFalse((real / "artifacts").exists())

            policy_alias_result = subprocess.run(
                [
                    "python3",
                    str(POLICY_SCRIPT),
                    "--repo-root",
                    str(REPO),
                    "--artifact-root",
                    str(alias / "policy-artifacts"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(policy_alias_result.returncode, 0)
            self.assertIn("symlink", policy_alias_result.stderr)
            self.assertFalse((real / "policy-artifacts").exists())

    def test_directory_descriptors_resist_pathname_swap_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            managed = root / "managed"
            held = root / "held"
            outside = root / "outside"
            managed.mkdir()
            outside.mkdir()
            with SafeDirectory.open_path(managed, create=False, require_owner=True, private=True) as opened:
                managed.rename(held)
                managed.symlink_to(outside, target_is_directory=True)
                with opened.open_or_create_private_child("created-after-swap") as child:
                    child.write_exclusive("proof", b"safe\n")
            self.assertEqual((held / "created-after-swap/proof").read_bytes(), b"safe\n")
            self.assertFalse((outside / "created-after-swap").exists())

    def test_effective_task_root_provenance_is_accurate_without_path_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            tasks = root / "private-source-name" / "tasks"
            tasks.mkdir(parents=True)
            run = self.run_script(
                REPORT_SCRIPT,
                "--repo-root",
                str(REPO),
                "--tasks-root",
                str(tasks),
                "--artifact-root",
                str(root / "artifacts"),
                "--now",
                NOW,
            )
            evidence = json.loads((run / "evidence.json").read_text())
            metadata = json.loads((run / "metadata.json").read_text())
            self.assertEqual(evidence["source"], {key: metadata["source"][key] for key in evidence["source"]})
            self.assertEqual(evidence["source"]["selection"], "explicit-override")
            self.assertEqual(evidence["source"]["display"], "<explicit-tasks-root>")
            self.assertRegex(evidence["source"]["root_id"], r"^fs-[0-9a-f]{20}$")
            artifact_text = "\n".join(path.read_text() for path in run.iterdir())
            self.assertNotIn(str(tasks), artifact_text)
            self.assertNotIn("private-source-name", artifact_text)

            home = root / "home"
            (home / "tasks").mkdir(parents=True)
            env = dict(os.environ, ROZORO_HOME=str(home))
            default_run = self.run_script(REPORT_SCRIPT, "--repo-root", str(REPO), "--now", NOW, env=env)
            default_evidence = json.loads((default_run / "evidence.json").read_text())
            self.assertEqual(default_evidence["source"]["selection"], "default-rozoro-home")
            self.assertEqual(default_evidence["source"]["display"], "$ROZORO_HOME/tasks")

    def test_progress_runs_are_unique_and_task_root_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
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
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr)


if __name__ == "__main__":
    unittest.main()
