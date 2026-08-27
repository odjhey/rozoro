"""Archive-safe completeness audit for tracked ROZORO_HOME selectors only."""
from __future__ import annotations

import ast
import copy
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/watchtower-home-consumers.json"
SOURCE_SUFFIXES = {".py", ".sh", ".ts", ".js", ".bash"}


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def git_source_names(root: Path) -> list[str] | None:
    """Return the exact git-index source surface, or None in an archive."""
    if not shutil.which("git"):
        return None
    run = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=root, capture_output=True)
    if run.returncode:
        return None
    names = []
    for row in run.stdout.decode().split("\0"):
        if not row:
            continue
        metadata, name = row.split("\t", 1)
        mode = metadata.split()[0]
        if mode == "100755" or Path(name).suffix in SOURCE_SUFFIXES:
            names.append(name)
    return names


def tracked_sources(root: Path = ROOT, *, git_names: list[str] | None | object = ...) -> tuple[dict[str, str], list[str]]:
    inventory = load_fixture()
    manifest = inventory["tracked_executable_sources"]
    actual = git_source_names(root) if git_names is ... else git_names
    errors = []
    if actual is not None and actual != manifest:
        errors.append("tracked-source manifest differs from git index")
    names = manifest if actual is None else actual
    sources = {}
    for name in names:
        path = root / name
        try:
            sources[name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"{name}: tracked source missing or unreadable")
    return sources, errors


def python_default(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Return)):
            continue
        values = {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        rendered = ast.dump(node, include_attributes=False)
        if {"ROZORO_HOME", "RZR_HOME"} <= values and (
            "~/.rozoro" in values or ("home" in rendered and ".rozoro" in values)
        ):
            return True
    return False


def shell_default(text: str) -> bool:
    return any(
        not line.lstrip().startswith("#") and "${ROZORO_HOME" in line
        and "${RZR_HOME" in line and ".rozoro" in line
        for line in text.splitlines()
    )


def typescript_default(text: str) -> bool:
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    return any("process.env.ROZORO_HOME" in line and "process.env.RZR_HOME" in line
               and "homedir()" in line and '".rozoro"' in line and "=" in line
               for line in code.splitlines())


def monitor_home_delegate(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    dump = ast.dump(tree, include_attributes=False)
    return "--home" in dump and "MonitorServer" in dump and "args" in dump


EVIDENCE = {
    "python_default": python_default,
    "shell_default": shell_default,
    "typescript_default": typescript_default,
    "monitor_home_delegate": monitor_home_delegate,
}


def direct_kind(path: str, text: str) -> str | None:
    if path.endswith(".py") and python_default(text): return "python_default"
    if path.endswith((".sh", ".bash")) and shell_default(text): return "shell_default"
    if path.endswith((".ts", ".js")) and typescript_default(text): return "typescript_default"
    if path.endswith(".py") and monitor_home_delegate(text): return "monitor_home_delegate"
    return None


def audit(inventory: dict, sources: dict[str, str], source_errors: list[str] | None = None) -> list[str]:
    errors = list(source_errors or [])
    memberships = {}
    for section in ("direct_default", "inherited_explicit_only", "excluded"):
        for path, evidence in inventory[section].items():
            if path in memberships: errors.append(f"{path}: classified twice")
            memberships[path] = section
            text = sources.get(path)
            if text is None:
                errors.append(f"{path}: fixture entry is not tracked source")
            elif section == "direct_default":
                kind = evidence["kind"]
                if kind not in EVIDENCE or not EVIDENCE[kind](text):
                    errors.append(f"{path}: fixture direct entry has no exact source evidence")
            elif any(needle not in text for needle in evidence):
                errors.append(f"{path}: fixture selector has no source match")
    selectors = {
        path for path, text in sources.items()
        if not path.startswith("tests/") and direct_kind(path, text)
    }
    for path in sorted(selectors - set(inventory["direct_default"])):
        errors.append(f"{path}: tracked default-home selector absent from direct_default")
    for path in inventory["inherited_explicit_only"]:
        if path in selectors: errors.append(f"{path}: direct selector mislabeled inherited/explicit-only")
    return errors


class HomeSourceAuditTests(unittest.TestCase):
    def sources(self, *, git_names: list[str] | None | object = ...):
        return tracked_sources(git_names=git_names)

    def test_git_and_archive_inventory_are_complete(self):
        sources, errors = self.sources()
        self.assertEqual(audit(load_fixture(), sources, errors), [])
        archived, errors = self.sources(git_names=None)
        self.assertEqual(audit(load_fixture(), archived, errors), [])

    def test_manifest_parity_and_missing_archive_source_fail_closed(self):
        manifest = load_fixture()["tracked_executable_sources"]
        _, errors = self.sources(git_names=manifest + ["tools/new-consumer.py"])
        self.assertIn("tracked-source manifest differs from git index", errors)
        with tempfile.TemporaryDirectory() as tmp:
            _, errors = tracked_sources(Path(tmp), git_names=None)
            self.assertTrue(any("missing or unreadable" in e for e in errors))

    def test_untracked_ignored_and_comment_string_decoys_do_not_count(self):
        sources, _ = self.sources(git_names=None)
        sources["ignored/new.py"] = '# os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") or "~/.rozoro"\n'
        sources["untracked/new.ts"] = 'const note = "ROZORO_HOME RZR_HOME ~/.rozoro";\n'
        self.assertEqual(audit(load_fixture(), {k: v for k, v in sources.items() if k not in {"ignored/new.py", "untracked/new.ts"}}), [])
        self.assertFalse(python_default(sources["ignored/new.py"]))
        self.assertFalse(typescript_default(sources["untracked/new.ts"]))

    def test_tracked_source_outside_prior_roots_is_detected(self):
        sources, _ = self.sources(git_names=None)
        sources["tools/new-home.py"] = 'home = os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") or "~/.rozoro"\n'
        self.assertIn("tools/new-home.py: tracked default-home selector absent from direct_default", audit(load_fixture(), sources))

    def test_direct_source_removal_rename_and_fixture_mutants_fail(self):
        sources, _ = self.sources(git_names=None)
        for path in ("bin/rzr-event-bus-client.py", "bin/rozorod.py"):
            removed = dict(sources); removed[path] = "#!/usr/bin/env python3\n"
            self.assertIn(
                f"{path}: fixture direct entry has no exact source evidence",
                audit(load_fixture(), removed),
            )
            renamed = dict(sources); renamed[path + ".renamed"] = renamed.pop(path)
            self.assertIn(
                f"{path}: fixture entry is not tracked source",
                audit(load_fixture(), renamed),
            )
        inventory = load_fixture(); del inventory["direct_default"]["bin/rzr-event-bus-client.py"]
        self.assertTrue(any("event-bus-client.py: tracked default-home selector absent" in e for e in audit(inventory, sources)))
        stale = load_fixture(); stale["direct_default"]["bin/removed.py"] = {"kind": "python_default"}
        self.assertIn("bin/removed.py: fixture entry is not tracked source", audit(stale, sources))

    def test_direct_as_inherited_mutant_is_rejected(self):
        inventory = load_fixture(); evidence = inventory["direct_default"].pop("bin/rzr-lib.sh")
        inventory["inherited_explicit_only"]["bin/rzr-lib.sh"] = ["ROZORO_HOME"]
        sources, _ = self.sources(git_names=None)
        self.assertIn("bin/rzr-lib.sh: direct selector mislabeled inherited/explicit-only", audit(inventory, sources))

    def test_codex_store_adapter_is_excluded_exactly_in_both_modes(self):
        inventory = load_fixture()
        self.assertEqual(inventory["excluded"], {"bin/rzr-codex-event-adapter.py": ["--store"]})
        for mode in (..., None):
            sources, errors = self.sources(git_names=mode)
            self.assertEqual(audit(inventory, sources, errors), [])
            self.assertNotIn("bin/rzr-codex-event-adapter.py", inventory["direct_default"])
