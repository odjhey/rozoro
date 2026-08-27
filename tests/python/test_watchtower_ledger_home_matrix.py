from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".agents/skills/watchtower-attention-ledger/scripts/ledger.py"


class WatchtowerLedgerHomeMatrixTests(unittest.TestCase):
    def command(
        self, cwd: Path, env: dict[str, str], subcommand: str, *args: str,
        home: str | None = None, success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(LEDGER), subcommand]
        if home is not None:
            command += ["--home", home]
        result = subprocess.run(command + list(args), cwd=cwd, env=env, text=True,
                                capture_output=True, timeout=20)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("Traceback", result.stderr)
        return result

    @staticmethod
    def tree_bytes(path: Path) -> dict[str, bytes]:
        return {str(entry.relative_to(path)): entry.read_bytes()
                for entry in path.rglob("*") if entry.is_file()}

    def exercise_sequence(
        self, cell: str, selected: Path, cwd: Path, env: dict[str, str],
        *, home: str | None = None, change_cwd_after_add: Path | None = None,
    ) -> None:
        decoy = cwd.parent / f"decoy-{cell}-{uuid.uuid4().hex}"
        decoy.mkdir()
        decoy_id = self.command(
            cwd, env, "add", "--task", f"decoy-{cell.lower()}", "--reason", "other",
            "--summary", f"never-selected-{cell}", "--now", "2026-08-26T12:00:00Z",
            "--nonce", uuid.uuid4().hex[:8], home=str(decoy),
        ).stdout.strip()
        before = self.tree_bytes(decoy)
        item_id = self.command(
            cwd, env, "add", "--task", f"home-{cell.lower()}", "--reason", "other",
            "--summary", f"selected-{cell}", "--now", "2026-08-27T12:00:00Z",
            "--nonce", uuid.uuid4().hex[:8], home=home,
        ).stdout.strip()
        if change_cwd_after_add is not None:
            change_cwd_after_add.mkdir()
            cwd = change_cwd_after_add
            # The selected relative value is normalized once at ingress and inherited
            # as an absolute value; later commands must not reinterpret it after cwd.
            env = dict(env, ROZORO_HOME=str(selected))
            if home is not None:
                home = str(selected)
        listed = json.loads(self.command(cwd, env, "list", "--format", "json", home=home).stdout)
        self.assertEqual([item["id"] for item in listed["items"]], [item_id], cell)
        shown = json.loads(self.command(cwd, env, "show", item_id, "--json", home=home).stdout)
        self.assertEqual(shown["summary"], f"selected-{cell}")
        primed = json.loads(self.command(cwd, env, "prime", "--format", "json", home=home).stdout)
        self.assertEqual([item["id"] for item in primed["normal_open"]], [item_id])
        doctor = json.loads(self.command(cwd, env, "doctor", "--json", home=home).stdout)
        self.assertEqual([item["id"] for item in doctor["ok"]], [item_id])
        exported = json.loads(self.command(cwd, env, "export", "--format", "json", home=home).stdout)
        self.assertEqual([item["frontmatter"]["id"] for item in exported["items"]], [item_id])
        item_file = selected / "watchtowers" / "attention" / "items" / f"{item_id}.md"
        self.assertTrue(item_file.is_file(), f"{cell}: selected root was not written")
        self.assertIn(f"selected-{cell}", item_file.read_text())
        self.assertNotIn(decoy_id, [item["frontmatter"]["id"] for item in exported["items"]])
        self.assertEqual(self.tree_bytes(decoy), before, f"{cell}: decoy changed")

    def test_real_cli_P_L_B_E_D_R_T_O_X(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            account_home = root / "home"
            initial = root / "initial"
            account_home.mkdir()
            initial.mkdir()
            rows = (
                ("P", {"ROZORO_HOME": "public"}, "cwd/public", None),
                ("L", {"RZR_HOME": "legacy"}, "cwd/legacy", None),
                ("B", {"ROZORO_HOME": "public", "RZR_HOME": "legacy-decoy"}, "cwd/public", None),
                ("E", {"ROZORO_HOME": "", "RZR_HOME": "legacy"}, "cwd/legacy", None),
                ("D-unset", {}, "home/.rozoro", None),
                ("D-empty", {"ROZORO_HOME": "", "RZR_HOME": ""}, "home/.rozoro", None),
                ("R", {"ROZORO_HOME": "relative/root"}, "cwd/relative/root", None),
                ("T", {"ROZORO_HOME": "~/tilde-root"}, "home/tilde-root", None),
                ("O", {"ROZORO_HOME": "environment-decoy"}, "cwd/override-root", "override-root"),
                ("X", {}, "home/.rozoro", None),
            )
            for cell, additions, selected_suffix, override in rows:
                with self.subTest(cell=cell):
                    cell_root = root / f"cell-{cell}"
                    cell_home = cell_root / "home"
                    cell_cwd = cell_root / "cwd"
                    cell_home.mkdir(parents=True)
                    cell_cwd.mkdir()
                    selected = cell_root / selected_suffix
                    xdg = cell_root / "xdg-decoy"
                    env = {"HOME": str(cell_home), "XDG_CONFIG_HOME": str(xdg), **additions}
                    later_cwd = cell_root / "later-cwd" if cell in {"R", "O"} else None
                    self.exercise_sequence(cell, selected, cell_cwd, env, home=override,
                                           change_cwd_after_add=later_cwd)
                    self.assertFalse((xdg / "watchtowers").exists())
                    if cell == "B":
                        self.assertFalse((cell_cwd / "legacy-decoy" / "watchtowers").exists())
                    if cell == "O":
                        self.assertFalse((cell_cwd / "environment-decoy" / "watchtowers").exists())

    def test_explicit_tilde_supported_user_and_unresolved_user(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fake_home = root / "home"
            initial = root / "initial"
            fake_home.mkdir()
            initial.mkdir()
            env = {"HOME": str(fake_home), "ROZORO_HOME": str(root / "environment-decoy")}
            self.exercise_sequence("O-tilde", fake_home / "explicit-tilde", initial, env,
                                   home="~/explicit-tilde")

            try:
                username = pwd.getpwuid(os.getuid()).pw_name
                real_account_home = Path(pwd.getpwnam(username).pw_dir)
            except KeyError:  # The pinned uid-only CI image intentionally has no passwd row.
                username = None
            if username is not None:
                fixture = real_account_home / f".rzr-ledger-h7-{uuid.uuid4().hex}"
                sibling = real_account_home / f".rzr-ledger-h7-sentinel-{uuid.uuid4().hex}"
                sibling.write_text("must survive", encoding="utf-8")
                self.assertFalse(fixture.exists())
                try:
                    try:
                        fixture.mkdir(mode=0o700)
                        self.exercise_sequence("T-user", fixture, initial, env,
                                               home=f"~{username}/{fixture.name}")
                    finally:
                        shutil.rmtree(fixture, ignore_errors=True)
                    self.assertFalse(fixture.exists())

                    with self.assertRaisesRegex(RuntimeError, "forced account fixture failure"):
                        try:
                            fixture.mkdir(mode=0o700)
                            raise RuntimeError("forced account fixture failure")
                        finally:
                            shutil.rmtree(fixture, ignore_errors=True)
                    self.assertFalse(fixture.exists())
                    self.assertEqual(sibling.read_text(encoding="utf-8"), "must survive")
                finally:
                    shutil.rmtree(fixture, ignore_errors=True)
                    sibling.unlink(missing_ok=True)
                self.assertFalse(fixture.exists())
                self.assertFalse(sibling.exists())

            unresolved = f"~rozoro-no-such-user-{uuid.uuid4().hex}/ledger"
            commands = (
                ("add", "--task", "bad", "--reason", "other", "--summary", "bad"),
                ("list",), ("show", "missing"), ("prime",), ("doctor",), ("export",),
            )
            for args in commands:
                with self.subTest(unresolved_command=args[0]):
                    self.command(initial, env, args[0], *args[1:], home=unresolved, success=False)
            self.assertFalse((root / "environment-decoy" / "watchtowers").exists())


if __name__ == "__main__":
    unittest.main()
