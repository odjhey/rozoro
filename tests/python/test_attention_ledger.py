from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER_SCRIPT = REPO / ".agents/skills/watchtower-attention-ledger/scripts/ledger.py"

VALID_ITEM = "\n".join(
    [
        "---",
        "schema: rozoro.watchtower-attention-ledger/v1",
        "id: 20260101T000000-task-abcd",
        "task: task",
        "reason: needs-action",
        "priority: normal",
        "status: open",
        "created_utc: 2026-01-01T00:00:00Z",
        "updated_utc: 2026-01-01T00:00:00Z",
        "generation: none",
        "source: manual",
        "superseded_by: none",
        "resume_when: none",
        "tags: [a, b]",
        "---",
        "# a title",
        "",
        "## Snapshot",
        "",
        "snap",
        "",
        "## Handling log",
        "",
        "- 2026-01-01T00:00:00Z new->open: created via manual",
        "",
        "## Context",
        "",
        "",
        "",
    ]
)


class AttentionLedgerTests(unittest.TestCase):
    def run_ledger(self, home: Path, *args: str, expect_success: bool = True, stdin: str | None = None) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["python3", str(LEDGER_SCRIPT), args[0], "--home", str(home), *args[1:]],
            check=False,
            capture_output=True,
            text=True,
            input=stdin,
        )
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def add(self, home: Path, task: str, reason: str, summary: str, nonce: str, now: str, *extra: str, stdin: str | None = None) -> str:
        result = self.run_ledger(
            home, "add", "--task", task, "--reason", reason, "--summary", summary, "--nonce", nonce, "--now", now, *extra, stdin=stdin
        )
        return result.stdout.strip()

    def items_dir(self, home: Path) -> Path:
        return home / "watchtowers" / "attention" / "items"

    def write_raw(self, home: Path, filename: str, text: str) -> None:
        (self.items_dir(home) / filename).write_text(text, encoding="utf-8")

    def show_json(self, home: Path, item_id: str) -> dict:
        return json.loads(self.run_ledger(home, "show", item_id, "--json").stdout)

    def test_round_trip_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            item_id = self.add(
                home,
                "fix-auth",
                "needs-action",
                "Crew asked which matrix entry is authoritative",
                "a1b2",
                "2026-08-25T09:30:12Z",
                "--priority",
                "urgent",
                "--generation",
                "41",
                "--source",
                "reconcile",
                "--tag",
                "pr-63",
                "--tag",
                "review",
                "--snapshot",
                "-",
                stdin="what the wake said\nsecond line\n",
            )
            self.assertEqual(item_id, "20260825T093012-fix-auth-a1b2")

            attention = home / "watchtowers" / "attention"
            for directory in (attention.parent, attention, self.items_dir(home)):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700, directory)
            item_file = self.items_dir(home) / f"{item_id}.md"
            self.assertEqual(stat.S_IMODE(item_file.stat().st_mode), 0o600)

            shown = self.show_json(home, item_id)
            self.assertEqual(shown["frontmatter"]["schema"], "rozoro.watchtower-attention-ledger/v1")
            self.assertEqual(shown["frontmatter"]["priority"], "urgent")
            self.assertEqual(shown["frontmatter"]["generation"], "41")
            self.assertEqual(shown["frontmatter"]["tags"], ["pr-63", "review"])
            self.assertEqual(shown["summary"], "Crew asked which matrix entry is authoritative")
            self.assertEqual(shown["snapshot"], "what the wake said\nsecond line")
            self.assertEqual(len(shown["handling_log"]), 1)

    def test_strict_parser_surfaces_every_violation_as_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            good = self.add(home, "task", "needs-action", "good item", "0001", "2026-01-01T00:00:00Z")

            cases = {
                "bad-enum.md": VALID_ITEM.replace("reason: needs-action", "reason: nonsense"),
                "bad-timestamp.md": VALID_ITEM.replace("created_utc: 2026-01-01T00:00:00Z", "created_utc: 2026-01-01"),
                "bad-charset.md": VALID_ITEM.replace("task: task", "task: bad task"),
                "unknown-key.md": VALID_ITEM.replace("tags: [a, b]", "tags: [a, b]\nextra: 1"),
                "missing-key.md": VALID_ITEM.replace("source: manual\n", ""),
                "bad-tags.md": VALID_ITEM.replace("tags: [a, b]", "tags: a, b"),
                "id-mismatch.md": VALID_ITEM,  # stem will not match frontmatter id
            }
            for filename, text in cases.items():
                self.write_raw(home, filename, text)

            listed = json.loads(self.run_ledger(home, "list", "--status", "open", "--format", "json").stdout)
            self.assertEqual([item["id"] for item in listed["items"]], [good])
            malformed_names = {entry["filename"] for entry in listed["malformed"]}
            self.assertEqual(malformed_names, set(cases))

            doctor = self.run_ledger(home, "doctor", "--json", expect_success=False)
            self.assertEqual(doctor.returncode, 1)
            report = json.loads(doctor.stdout)
            self.assertEqual({entry["filename"] for entry in report["malformed"]}, set(cases))
            self.assertEqual([entry["id"] for entry in report["ok"]], [good])

    def test_supersession_default_and_opt_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            first = self.add(home, "svc", "blocked", "first blocked", "0001", "2026-01-01T00:00:00Z")
            second_out = self.run_ledger(
                home, "add", "--task", "svc", "--reason", "blocked", "--summary", "second", "--nonce", "0002", "--now", "2026-01-01T01:00:00Z", "--json"
            )
            second = json.loads(second_out.stdout)
            self.assertEqual(second["superseded"], [first])

            superseded = self.show_json(home, first)
            self.assertEqual(superseded["frontmatter"]["status"], "superseded")
            self.assertEqual(superseded["frontmatter"]["superseded_by"], second["id"])
            self.assertTrue(any("superseded by" in line for line in superseded["handling_log"]))

            default = json.loads(self.run_ledger(home, "list", "--format", "json").stdout)
            self.assertEqual([item["id"] for item in default["items"]], [second["id"]])

            refused = self.run_ledger(home, "update", first, "--note", "x", "--status", "handled", expect_success=False)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("superseded", refused.stderr)

            kept = json.loads(
                self.run_ledger(
                    home, "add", "--task", "svc", "--reason", "blocked", "--summary", "third", "--nonce", "0003", "--now", "2026-01-01T02:00:00Z", "--no-supersede", "--json"
                ).stdout
            )
            self.assertEqual(kept["superseded"], [])
            self.assertEqual(self.show_json(home, second["id"])["frontmatter"]["status"], "open")

    def test_update_is_append_only_and_guards_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            item_id = self.add(home, "task", "failed", "needs handling", "0001", "2026-01-01T00:00:00Z", "--snapshot", "-", stdin="original snapshot\n")
            before = self.show_json(home, item_id)

            self.run_ledger(home, "update", item_id, "--note", "dispatched scout", "--now", "2026-01-01T00:05:00Z")
            after = self.show_json(home, item_id)
            self.assertEqual(after["snapshot"], before["snapshot"])
            self.assertEqual(after["handling_log"][:1], before["handling_log"])
            self.assertEqual(len(after["handling_log"]), 2)
            self.assertIn("dispatched scout", after["handling_log"][-1])

            missing_note = self.run_ledger(home, "update", item_id, expect_success=False)
            self.assertEqual(missing_note.returncode, 2)  # argparse: --note required

            empty_note = self.run_ledger(home, "update", item_id, "--note", "   ", expect_success=False)
            self.assertEqual(empty_note.returncode, 1)

            no_resume = self.run_ledger(home, "update", item_id, "--note", "deferring", "--status", "deferred", expect_success=False)
            self.assertEqual(no_resume.returncode, 1)
            self.assertIn("resume-when", no_resume.stderr)

            self.run_ledger(home, "update", item_id, "--note", "deferring", "--status", "deferred", "--resume-when", "CI green on PR #63", "--now", "2026-01-01T00:10:00Z")
            self.assertEqual(self.show_json(home, item_id)["frontmatter"]["resume_when"], "CI green on PR #63")

    def test_filtering_combines_and_across_or_within(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            a = self.add(home, "alpha", "failed", "a", "0001", "2026-01-01T00:00:00Z", "--priority", "urgent", "--tag", "x")
            b = self.add(home, "beta", "blocked", "b", "0002", "2026-01-02T00:00:00Z", "--tag", "y")
            c = self.add(home, "alpha", "needs-action", "c", "0003", "2026-01-03T00:00:00Z", "--tag", "z")

            def ids(*flags: str) -> list[str]:
                payload = json.loads(self.run_ledger(home, "list", "--status", "open", "--format", "json", *flags).stdout)
                return [item["id"] for item in payload["items"]]

            self.assertEqual(ids("--task", "alpha"), [c, a])
            self.assertEqual(ids("--priority", "urgent"), [a])
            self.assertEqual(ids("--reason", "failed", "--reason", "blocked"), [b, a])  # OR within reason
            self.assertEqual(ids("--task", "alpha", "--reason", "failed"), [a])  # AND across filters
            self.assertEqual(ids("--tag", "x", "--tag", "y"), [b, a])  # OR within tag
            self.assertEqual(ids("--since", "2026-01-02T00:00:00Z"), [c, b])
            self.assertEqual(ids("--until", "2026-01-02T00:00:00Z"), [b, a])

    def test_pagination_walks_every_item_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            created = []
            for index in range(5):
                created.append(self.add(home, "task", "other", f"item {index}", f"{index:04d}", f"2026-01-0{index + 1}T00:00:00Z", "--no-supersede"))
            expected = list(reversed(created))  # updated_utc desc

            seen: list[str] = []
            cursor: str | None = None
            for _ in range(10):
                flags = ["--status", "open", "--limit", "2", "--format", "json"]
                if cursor is not None:
                    flags += ["--cursor", cursor]
                payload = json.loads(self.run_ledger(home, "list", *flags).stdout)
                seen.extend(item["id"] for item in payload["items"])
                cursor = payload["next_cursor"]
                if cursor is None:
                    break
            self.assertEqual(seen, expected)
            self.assertIsNone(cursor)

    def test_prime_orders_sections_and_marks_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            self.add(home, "urgent-task", "failed", "urgent thing", "0001", "2026-01-01T00:00:00Z", "--priority", "urgent")
            normal = self.add(home, "normal-task", "blocked", "normal thing", "0002", "2026-01-02T00:00:00Z")
            handled = self.add(home, "done-task", "needs-action", "handled thing", "0003", "2026-01-03T00:00:00Z")
            self.run_ledger(home, "update", handled, "--note", "answered crew", "--status", "handled", "--now", "2026-01-03T01:00:00Z")
            self.run_ledger(home, "update", normal, "--note", "waiting on ci", "--status", "deferred", "--resume-when", "ci passes", "--now", "2026-01-02T01:00:00Z")
            self.write_raw(home, "broken.md", "not a valid item")

            text = self.run_ledger(home, "prime").stdout
            self.assertIn("not verified system state", text)
            self.assertLess(text.index("## Urgent open items"), text.index("## Normal open items"))
            self.assertLess(text.index("## Normal open items"), text.index("## Deferred"))
            self.assertLess(text.index("## Deferred"), text.index("## Recently handled"))
            self.assertIn("urgent-task", text.split("## Normal open items")[0])
            self.assertIn("resume_when=ci passes", text)
            self.assertIn("answered crew", text)
            self.assertIn("malformed: 1", text)

            payload = json.loads(self.run_ledger(home, "prime", "--format", "json").stdout)
            self.assertEqual(payload["counts"]["malformed"], 1)
            self.assertEqual([item["id"] for item in payload["urgent_open"]], [json.loads(self.run_ledger(home, "list", "--priority", "urgent", "--format", "json").stdout)["items"][0]["id"]])
            self.assertEqual(payload["deferred"][0]["resume_when"], "ci passes")

    def test_symlinked_entries_are_unsafe_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            home = root / "home"
            home.mkdir()
            good = self.add(home, "task", "other", "safe item", "0001", "2026-01-01T00:00:00Z")

            outside = root / "outside.md"
            outside.write_text(VALID_ITEM, encoding="utf-8")
            (self.items_dir(home) / "linked.md").symlink_to(outside)
            (self.items_dir(home) / "dangling.md").symlink_to(root / "does-not-exist")

            doctor = self.run_ledger(home, "doctor", "--json", expect_success=False)
            report = json.loads(doctor.stdout)
            self.assertEqual([entry["id"] for entry in report["ok"]], [good])
            malformed = {entry["filename"]: entry["reason"] for entry in report["malformed"]}
            self.assertEqual(set(malformed), {"linked.md", "dangling.md"})
            for reason in malformed.values():
                self.assertIn("unsafe", reason)

    def test_symlinked_ancestor_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            real = root / "real-home"
            real.mkdir()
            self.add(real, "task", "other", "x", "0001", "2026-01-01T00:00:00Z")
            alias = root / "alias-home"
            alias.symlink_to(real, target_is_directory=True)

            result = self.run_ledger(alias, "list", expect_success=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr)

    def test_lock_is_held_for_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve() / "home"
            home.mkdir()
            first = self.add(home, "task", "other", "first", "0001", "2026-01-01T00:00:00Z")
            self.run_ledger(home, "update", first, "--note", "second mutation", "--now", "2026-01-01T00:05:00Z")
            self.assertEqual(len(self.show_json(home, first)["handling_log"]), 2)

            lock_path = home / "watchtowers" / "attention" / "attention.lock"
            held = os.open(lock_path, os.O_RDWR)
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                blocked = self.run_ledger(
                    home, "add", "--task", "task", "--reason", "other", "--summary", "blocked", "--nonce", "0002", "--now", "2026-01-01T01:00:00Z", expect_success=False
                )
                self.assertEqual(blocked.returncode, 1)
                self.assertIn("locked by another writer", blocked.stderr)
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
                os.close(held)


if __name__ == "__main__":
    unittest.main()
