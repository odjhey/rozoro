"""Semantic, archive-safe completeness audit for tracked home selectors."""
from __future__ import annotations

import ast
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/watchtower-home-consumers.json"
SOURCE_SUFFIXES = {".py", ".sh", ".ts", ".js", ".bash"}
# .claude is an explicitly ignored/generated compatibility projection of .agents.
ARCHIVE_IGNORES = {".git", ".worktrees", ".claude", "node_modules", "vendor", "dist", "build", "__pycache__", ".pytest_cache"}
ARCHIVE_GENERATED_ALIASES = {"bin/rzr"}


def load_fixture(root: Path = ROOT) -> dict:
    return json.loads((root / FIXTURE.relative_to(ROOT)).read_text(encoding="utf-8"))


def is_source(path: Path, mode_executable: bool) -> bool:
    return mode_executable or path.suffix in SOURCE_SUFFIXES


def git_source_names(root: Path) -> tuple[list[str] | None, list[str]]:
    """None means genuinely no git executable; every git error is fatal."""
    if shutil.which("git") is None:
        return None, []
    run = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=root, capture_output=True)
    if run.returncode:
        detail = run.stderr.decode(errors="replace").strip() or "invalid git inventory"
        return [], [f"git inventory failed closed: {detail}"]
    names = []
    try:
        rows = run.stdout.decode().split("\0")
        for row in rows:
            if not row:
                continue
            metadata, name = row.split("\t", 1)
            fields = metadata.split()
            if len(fields) != 3 or fields[0] not in {"100644", "100755", "120000", "160000"}:
                raise ValueError("invalid ls-files record")
            if fields[0].startswith("100") and is_source(Path(name), fields[0] == "100755"):
                names.append(name)
    except (UnicodeDecodeError, ValueError):
        return [], ["git inventory failed closed: invalid ls-files output"]
    return names, []


def archive_source_names(root: Path) -> list[str]:
    """Independently enumerate all source/executable files present in an archive."""
    names = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (any(part in ARCHIVE_IGNORES for part in relative.parts)
                or relative.as_posix() in ARCHIVE_GENERATED_ALIASES or not path.is_file()):
            continue
        if is_source(path, os.access(path, os.X_OK)):
            names.append(relative.as_posix())
    return sorted(names)


def tracked_sources(root: Path = ROOT, *, mode: str = "auto") -> tuple[dict[str, str], list[str]]:
    manifest = load_fixture(root)["tracked_executable_sources"]
    if mode == "archive":
        actual, errors = archive_source_names(root), []
    else:
        actual, errors = git_source_names(root)
        if actual is None:
            actual = archive_source_names(root)
    if actual != manifest:
        errors.append("tracked-source manifest differs from source surface")
    sources = {}
    for name in actual:
        try:
            sources[name] = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"{name}: source missing or unreadable")
    return sources, errors


def parse_python(text: str) -> ast.AST | None:
    try: return ast.parse(text)
    except SyntaxError: return None


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def env_get_key(call: ast.Call) -> str | None:
    name = dotted(call.func)
    if name not in {"os.environ.get", "os.getenv"} or not call.args:
        return None
    arg = call.args[0]
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def default_path_node(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and node.value == "~/.rozoro": return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return (isinstance(node.right, ast.Constant) and node.right.value == ".rozoro"
                and isinstance(node.left, ast.Call) and dotted(node.left.func) in {"Path.home"})
    return False


def python_default(text: str) -> bool:
    tree = parse_python(text)
    if tree is None: return False
    for statement in ast.walk(tree):
        if not isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Return)): continue
        keys = {key for call in ast.walk(statement) if isinstance(call, ast.Call)
                for key in [env_get_key(call)] if key}
        if {"ROZORO_HOME", "RZR_HOME"} <= keys and any(default_path_node(n) for n in ast.walk(statement)):
            return True
    return False


def python_argument(text: str, value: str) -> bool:
    tree = parse_python(text)
    return bool(tree and any(isinstance(n, ast.Call) and dotted(n.func) and dotted(n.func).endswith(".add_argument")
                             and any(isinstance(a, ast.Constant) and a.value == value for a in n.args)
                             for n in ast.walk(tree)))


def python_call(text: str, value: str) -> bool:
    tree = parse_python(text)
    return bool(tree and any(isinstance(n, ast.Call) and dotted(n.func) == value for n in ast.walk(tree)))


def python_parameter(text: str, value: str) -> bool:
    tree = parse_python(text)
    return bool(tree and any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and any(a.arg == value for a in n.args.args) for n in ast.walk(tree)))


def monitor_home_delegate(text: str) -> bool:
    tree = parse_python(text)
    if tree is None or not python_argument(text, "--home"): return False
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and dotted(n.func) == "MonitorServer":
            if any(dotted(a) in {"args.home", "home"} for a in n.args): return True
            if any(k.arg == "home" and dotted(k.value) in {"args.home", "home"} for k in n.keywords): return True
    return False


def shell_statements(text: str) -> list[tuple[str, list[str]]]:
    logical = re.sub(r"\\\n", " ", text)
    result = []
    for line in logical.splitlines():
        try: tokens = shlex.split(line, comments=True, posix=True)
        except ValueError: continue
        if tokens: result.append((line, tokens))
    return result


def shell_default(text: str) -> bool:
    for raw, tokens in shell_statements(text):
        if not re.match(r"\s*[A-Za-z_][A-Za-z0-9_]*=", raw): continue
        assignment = tokens[0]
        if "${ROZORO_HOME" in assignment and "${RZR_HOME" in assignment and ".rozoro" in assignment:
            return True
    return False


def shell_argument(text: str, value: str) -> bool:
    return any(value in tokens and any(t in {"python", "python3", "$PYTHON"} or t.endswith(".py") for t in tokens)
               for _, tokens in shell_statements(text))


def shell_export(text: str, value: str) -> bool:
    return any(tokens[0] == "export" and any(t.split("=", 1)[0] == value for t in tokens[1:])
               for _, tokens in shell_statements(text))


def shell_source(text: str, value: str) -> bool:
    return any(tokens[0] in {".", "source"} and any(value in token for token in tokens[1:])
               for _, tokens in shell_statements(text))


def ts_tokens(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"/\*.*?\*/|//[^\n]*|(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|[A-Za-z_$][\w$]*|\S", re.S)
    out = []
    for match in pattern.finditer(text):
        token = match.group()
        if token.startswith(("//", "/*")): continue
        out.append(("string" if token[:1] in {'\"', "'"} else "code", token))
    return out


def typescript_default(text: str) -> bool:
    tokens = ts_tokens(text)
    code = [v for kind, v in tokens if kind == "code"]
    strings = {v[1:-1] for kind, v in tokens if kind == "string"}
    joined = " ".join(code)
    return ("process . env . ROZORO_HOME" in joined and "process . env . RZR_HOME" in joined
            and "homedir ( )" in joined and ".rozoro" in strings)


EVIDENCE = {
    "python_default": lambda t, v=None: python_default(t),
    "python_argument": python_argument, "python_call": python_call, "python_parameter": python_parameter,
    "shell_default": lambda t, v=None: shell_default(t), "shell_argument": shell_argument,
    "shell_export": shell_export, "shell_source": shell_source,
    "typescript_default": lambda t, v=None: typescript_default(t),
    "monitor_home_delegate": lambda t, v=None: monitor_home_delegate(t),
}


def direct_kind(path: str, text: str) -> str | None:
    if path.endswith(".py") and python_default(text): return "python_default"
    if path.endswith((".sh", ".bash")) and shell_default(text): return "shell_default"
    if path.endswith((".ts", ".js")) and typescript_default(text): return "typescript_default"
    if path.endswith(".py") and monitor_home_delegate(text): return "monitor_home_delegate"
    return None


def audit(inventory: dict, sources: dict[str, str], source_errors: list[str] | None = None) -> list[str]:
    errors, memberships = list(source_errors or []), {}
    for section in ("direct_default", "inherited_explicit_only", "excluded"):
        for path, evidence in inventory[section].items():
            if path in memberships: errors.append(f"{path}: classified twice")
            memberships[path] = section
            text = sources.get(path)
            if text is None: errors.append(f"{path}: fixture entry is not source surface")
            elif evidence.get("kind") not in EVIDENCE or not EVIDENCE[evidence["kind"]](text, evidence.get("value")):
                errors.append(f"{path}: fixture {section} entry has no semantic source evidence")
    selectors = {p for p, text in sources.items() if not p.startswith("tests/") and direct_kind(p, text)}
    for path in sorted(selectors - set(inventory["direct_default"])):
        errors.append(f"{path}: tracked default-home selector absent from direct_default")
    for path in inventory["inherited_explicit_only"]:
        if path in selectors: errors.append(f"{path}: direct selector mislabeled inherited/explicit-only")
    return errors


class HomeSourceAuditTests(unittest.TestCase):
    def current(self, mode="auto"): return tracked_sources(mode=mode)

    def test_git_and_independent_archive_surfaces_are_complete(self):
        for mode in ("auto", "archive"):
            sources, errors = self.current(mode)
            self.assertEqual(audit(load_fixture(), sources, errors), [])

    def test_git_failure_and_invalid_output_fail_closed(self):
        with mock.patch("shutil.which", return_value="/fake/git"):
            with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 2, b"", b"boom")):
                _, errors = self.current()
                self.assertTrue(any("git inventory failed closed" in e for e in errors))
            bad = subprocess.CompletedProcess([], 0, b"garbage\0", b"")
            with mock.patch("subprocess.run", return_value=bad):
                _, errors = self.current()
                self.assertTrue(any("invalid ls-files output" in e for e in errors))

    def test_archive_omission_outside_root_addition_and_missing_file_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shutil.copytree(ROOT, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", ".worktrees", "__pycache__"))
            (root / "tools").mkdir(); (root / "tools/new.py").write_text("print('x')\n")
            _, errors = tracked_sources(root, mode="archive")
            self.assertIn("tracked-source manifest differs from source surface", errors)
            (root / "tools/new.py").unlink(); (root / "bin/rzr-monitor.py").unlink()
            _, errors = tracked_sources(root, mode="archive")
            self.assertIn("tracked-source manifest differs from source surface", errors)

    def test_git_mode_ignores_actual_untracked_and_ignored_files(self):
        sources, errors = self.current()
        self.assertEqual(audit(load_fixture(), sources, errors), [])
        self.assertNotIn("ignored/decoy.py", sources)

    def test_semantic_decoys_are_rejected_for_every_language(self):
        self.assertFalse(python_default('("ROZORO_HOME", "RZR_HOME", "~/.rozoro")\n'))
        self.assertFalse(python_default('"""os.environ.get(\"ROZORO_HOME\") or ~/.rozoro"""\n'))
        self.assertFalse(shell_default('# X=${ROZORO_HOME:-${RZR_HOME:-~/.rozoro}}\nX="ROZORO_HOME RZR_HOME ~/.rozoro"\n'))
        self.assertFalse(typescript_default('// process.env.ROZORO_HOME || process.env.RZR_HOME || join(homedir(), ".rozoro")\nconst x="process.env.ROZORO_HOME process.env.RZR_HOME homedir() .rozoro"'))
        self.assertFalse(monitor_home_delegate('NOTE=("--home", "MonitorServer", "args")\n'))
        self.assertFalse(python_argument('# --store\nNOTE="--store"\n', "--store"))

    def test_tracked_source_outside_prior_roots_is_detected(self):
        sources, _ = self.current(); sources["tools/new-home.py"] = 'home=os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") or "~/.rozoro"\n'
        self.assertIn("tools/new-home.py: tracked default-home selector absent from direct_default", audit(load_fixture(), sources))

    def test_removal_rename_stale_and_direct_binding_mutants(self):
        sources, _ = self.current("archive")
        for path in ("bin/rzr-event-bus-client.py", "bin/rozorod.py"):
            removed = dict(sources); removed[path] = "#!/usr/bin/env python3\n"
            self.assertTrue(any(path in e and "no semantic source evidence" in e for e in audit(load_fixture(), removed)))
            renamed = dict(sources); renamed[path + ".renamed"] = renamed.pop(path)
            self.assertTrue(any(path in e and "not source surface" in e for e in audit(load_fixture(), renamed)))
        inventory = load_fixture(); del inventory["direct_default"]["bin/rzr-event-bus-client.py"]
        self.assertTrue(any("event-bus-client.py: tracked default-home selector absent" in e for e in audit(inventory, sources)))
        stale = load_fixture(); stale["direct_default"]["bin/removed.py"] = {"kind":"python_default"}
        self.assertTrue(any("bin/removed.py: fixture entry is not source surface" == e for e in audit(stale, sources)))

    def test_direct_as_inherited_and_codex_exclusion_in_both_modes(self):
        inventory = load_fixture(); inventory["inherited_explicit_only"]["bin/rzr-lib.sh"] = inventory["direct_default"].pop("bin/rzr-lib.sh")
        sources, _ = self.current("archive")
        self.assertIn("bin/rzr-lib.sh: direct selector mislabeled inherited/explicit-only", audit(inventory, sources))
        expected = {"bin/rzr-codex-event-adapter.py": {"kind":"python_argument", "value":"--store"}}
        self.assertEqual(load_fixture()["excluded"], expected)
        for mode in ("auto", "archive"):
            sources, errors = self.current(mode); self.assertEqual(audit(load_fixture(), sources, errors), [])


if __name__ == "__main__": unittest.main()
