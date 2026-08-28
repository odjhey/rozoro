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
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/watchtower-home-consumers.json"
SOURCE_SUFFIXES = {".py", ".sh", ".ts", ".js", ".bash"}
# Exact repository metadata/worktree artifacts and generated compatibility aliases.
# No directory-name class (vendor/cache/build/etc.) is exempt from archive parity.
ARCHIVE_ARTIFACT_ROOTS = {".git", ".worktrees"}
ARCHIVE_GENERATED_ALIASES = {"bin/rzr", ".claude/skills"}


def load_fixture(root: Path = ROOT) -> dict:
    return json.loads((root / FIXTURE.relative_to(ROOT)).read_text(encoding="utf-8"))


def is_source(path: Path, mode_executable: bool) -> bool:
    return mode_executable or path.suffix in SOURCE_SUFFIXES


def parse_git_records(data: bytes, root: Path) -> list[str]:
    names, seen = [], {}
    for raw in data.split(b"\0"):
        if not raw: continue
        row = raw.decode("utf-8", errors="strict")
        metadata, name = row.split("\t", 1)
        fields = metadata.split()
        if (len(fields) != 3 or fields[0] not in {"100644", "100755", "120000", "160000"}
                or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", fields[1]) or fields[2] != "0"):
            raise ValueError("invalid record metadata")
        pure = PurePosixPath(name)
        if (not name or name.startswith("/") or "\\" in name or any(p in {"", ".", ".."} for p in pure.parts)
                or pure.as_posix() != name or name in seen):
            raise ValueError("invalid or duplicate record name")
        seen[name] = fields[0]
        if fields[0] == "120000" and name not in ARCHIVE_GENERATED_ALIASES:
            link = root / name
            if not link.is_symlink(): raise ValueError("missing source symlink")
            resolved = link.resolve(strict=True)
            try: resolved.relative_to(root.resolve())
            except ValueError as exc: raise ValueError("outside source symlink") from exc
        if fields[0].startswith("100") and is_source(Path(name), fields[0] == "100755"):
            names.append(name)
    return names


def git_source_names(root: Path) -> tuple[list[str] | None, list[str]]:
    """None means genuinely no git executable; every git error is fatal."""
    if shutil.which("git") is None: return None, []
    try: run = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=root, capture_output=True)
    except OSError as exc: return [], [f"git inventory failed closed: {exc}"]
    if run.returncode:
        detail = run.stderr.decode(errors="replace").strip() or "invalid git inventory"
        return [], [f"git inventory failed closed: {detail}"]
    try: return parse_git_records(run.stdout, root), []
    except (UnicodeDecodeError, ValueError, OSError):
        return [], ["git inventory failed closed: invalid ls-files output"]


def archive_source_names(root: Path) -> list[str]:
    """Independently enumerate with lstat only; never follow a source symlink."""
    names = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        kept = []
        for entry in dirs:
            path = base / entry; name = path.relative_to(root).as_posix()
            if (name in ARCHIVE_ARTIFACT_ROOTS
                    or any(name == alias or name.startswith(alias + "/") for alias in ARCHIVE_GENERATED_ALIASES)):
                continue
            if path.is_symlink():
                if path.suffix in SOURCE_SUFFIXES: raise ValueError(f"archive source symlink: {name}")
                continue
            kept.append(entry)
        dirs[:] = kept
        for entry in files:
            path = base / entry; name = path.relative_to(root).as_posix()
            if any(name == alias or name.startswith(alias + "/") for alias in ARCHIVE_GENERATED_ALIASES): continue
            info = path.lstat()
            if __import__("stat").S_ISLNK(info.st_mode):
                if path.suffix in SOURCE_SUFFIXES: raise ValueError(f"archive source symlink: {name}")
                continue
            if __import__("stat").S_ISREG(info.st_mode) and is_source(path, bool(info.st_mode & 0o111)):
                names.append(name)
    return sorted(names)


def tracked_sources(root: Path = ROOT, *, mode: str = "auto") -> tuple[dict[str, str], list[str]]:
    manifest = load_fixture(root)["tracked_executable_sources"]
    if mode == "archive":
        try: actual, errors = archive_source_names(root), []
        except (OSError, ValueError) as exc: actual, errors = [], [f"archive inventory failed closed: {exc}"]
    else:
        actual, errors = git_source_names(root)
        if actual is None:
            try: actual = archive_source_names(root)
            except (OSError, ValueError) as exc: actual, errors = [], [f"archive inventory failed closed: {exc}"]
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
    if isinstance(node, ast.Call) and dotted(node.func) == "str" and len(node.args) == 1:
        return default_path_node(node.args[0])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return (isinstance(node.right, ast.Constant) and node.right.value == ".rozoro"
                and isinstance(node.left, ast.Call) and dotted(node.left.func) == "Path.home")
    return False


def home_selector_expression(node: ast.AST) -> bool:
    """Require one contiguous OR dataflow chain ending env/env/default."""
    if (isinstance(node, ast.Call) and dotted(node.func) == "normalized_path"
            and len(node.args) == 1):
        return home_selector_expression(node.args[0])
    if isinstance(node, ast.IfExp):
        return home_selector_expression(node.orelse)
    if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or): return False
    operands = []
    def flatten(value: ast.AST) -> None:
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
            for child in value.values: flatten(child)
        else: operands.append(value)
    flatten(node)
    if len(operands) < 3: return False
    tail = operands[-3:]
    def selector_key(value: ast.AST) -> str | None:
        if isinstance(value, ast.Call): return env_get_key(value)
        if isinstance(value, ast.IfExp) and isinstance(value.orelse, ast.Call):
            return env_get_key(value.orelse)
        return None
    keys = [selector_key(n) for n in tail[:2]]
    return keys == ["ROZORO_HOME", "RZR_HOME"] and default_path_node(tail[2])


def python_default(text: str) -> bool:
    tree = parse_python(text)
    if tree is None: return False
    for statement in ast.walk(tree):
        value = (statement.value if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Return)) else None)
        if value is not None and home_selector_expression(value): return True
    return False


def python_argument(text: str, value: str) -> bool:
    tree = parse_python(text)
    return bool(tree and any(isinstance(n, ast.Call) and dotted(n.func) and dotted(n.func).endswith(".add_argument")
                             and any(isinstance(a, ast.Constant) and a.value == value for a in n.args)
                             for n in ast.walk(tree)))


def python_call(text: str, value: str) -> bool:
    tree = parse_python(text)
    return bool(tree and any(isinstance(n, ast.Call) and dotted(n.func) == value for n in ast.walk(tree)))


def python_event_store_path(text: str, value: str) -> bool:
    tree = parse_python(text)
    if tree is None: return False
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "EventStore"):
        for fn in (n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__init__"):
            if any(a.arg == value for a in fn.args.args):
                # The parameter must participate in an executable call, not merely exist.
                return any(isinstance(call, ast.Call) and any(isinstance(a, ast.Name) and a.id == value
                           for a in call.args) for call in ast.walk(fn))
    return False


def monitor_home_delegate(text: str) -> bool:
    tree = parse_python(text)
    if tree is None or not python_argument(text, "--home"): return False
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and dotted(n.func) == "MonitorServer":
            if any(dotted(a) in {"args.home", "home"} for a in n.args): return True
            if any(k.arg == "home" and dotted(k.value) in {"args.home", "home"} for k in n.keywords): return True
    return False


def shell_active_text(line: str) -> str:
    """Keep unquoted/double-quoted shell syntax; erase single quotes/comments."""
    out, quote, escaped = [], None, False
    for char in line:
        if escaped:
            if quote != "'": out.append(char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True; out.append(char); continue
        if char == "#" and quote is None: break
        if char == "'" and quote is None: quote = "'"; continue
        if char == "'" and quote == "'": quote = None; continue
        if char == '"' and quote is None: quote = '"'; continue
        if char == '"' and quote == '"': quote = None; continue
        if quote != "'": out.append(char)
    return "".join(out)


def shell_statements(text: str) -> list[tuple[str, list[str]]]:
    logical = re.sub(r"\\\n", " ", text)
    result = []
    for line in logical.splitlines():
        active = shell_active_text(line)
        try: tokens = shlex.split(line, comments=True, posix=True)
        except ValueError: continue
        if tokens: result.append((active, tokens))
    return result


def shell_default(text: str) -> bool:
    # Quotes may differ, but the one active assignment must itself carry the
    # complete public -> legacy -> HOME default dataflow. Neighboring commands
    # and detached expansions cannot lend it evidence.
    direct = re.compile(
        r"\s*RZR_HOME_RAW\s*=\s*"
        r"\$\{ROZORO_HOME:-\$\{RZR_HOME:-(?:\$HOME|\$\{HOME\})/\.rozoro\}\}\s*"
    )
    assignments = []
    for active, _ in shell_statements(text):
        if re.match(r"\s*RZR_HOME_RAW\s*=", active): assignments.append(active)
    return len(assignments) == 1 and direct.fullmatch(assignments[0]) is not None


def shell_argument(text: str, value: str) -> bool:
    return any(value in active.split() and any(t in {"python", "python3", "$PYTHON"} or t.endswith(".py") for t in tokens)
               for active, tokens in shell_statements(text))


def shell_export(text: str, value: str) -> bool:
    return any(re.match(rf"\s*export\s+{re.escape(value)}=", active) is not None
               for active, _ in shell_statements(text))


def shell_source(text: str, value: str) -> bool:
    return any(re.match(r"\s*(?:\.|source)\s+", active) and value in active
               for active, _ in shell_statements(text))


def ts_tokens(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"/\*.*?\*/|//[^\n]*|`(?:\\.|[^`\\])*`|"
        r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"
        r"/(?:\\.|[^/\\\n])+/[a-z]*|\|\||[A-Za-z_$][\w$]*|\S", re.S
    )
    out = []
    for match in pattern.finditer(text):
        token = match.group()
        if token.startswith(("//", "/*")): continue
        inert = token[:1] in {'\"', "'", "`"} or (token.startswith("/") and token.count("/") >= 2)
        out.append(("inert" if inert else "code", token))
    return out


def ts_scalar_selector(tokens: list[tuple[str, str]]) -> bool:
    values = [value for _, value in tokens]
    # Allow only one single-argument repository path normalizer wrapper.
    wrappers = (["resolve"], ["path", ".", "resolve"])
    for wrapper in wrappers:
        if values[:len(wrapper) + 1] == wrapper + ["("] and values[-1:] == [")"]:
            inner = tokens[len(wrapper) + 1:-1]
            depth = 0
            for _, value in inner:
                if value in "([{": depth += 1
                elif value in ")]}": depth -= 1
                elif value == "," and depth == 0: return False
            return ts_scalar_selector(inner)
    depth, parts, current = 0, [], []
    for token in tokens:
        value = token[1]
        if value in "([{": depth += 1
        elif value in ")]}": depth -= 1
        if value == "||" and depth == 0: parts.append(current); current = []
        else: current.append(token)
    parts.append(current)
    if len(parts) != 3: return False
    code = [[v for kind, v in part if kind == "code"] for part in parts]
    return (code[0] == ["process", ".", "env", ".", "ROZORO_HOME"]
            and code[1] == ["process", ".", "env", ".", "RZR_HOME"]
            and code[2] == ["join", "(", "homedir", "(", ")", ",", ")"]
            and [v[1:-1] for kind, v in parts[2] if kind == "inert" and v[:1] in {'\"', "'"}] == [".rozoro"])


def typescript_default(text: str) -> bool:
    # Physical newlines and semicolons are hard ASI boundaries.
    for physical in text.splitlines():
        statement = []
        for token in ts_tokens(physical) + [("code", ";")]:
            statement.append(token)
            if token != ("code", ";"): continue
            values = [v for _, v in statement]
            start = None
            if values[:1] == ["return"]: start = 1
            else:
                for i, value in enumerate(values):
                    if value == "=" and i >= 2 and re.search(r"[Hh]ome", values[i - 1]): start = i + 1; break
            if start is not None and ts_scalar_selector(statement[start:-1]): return True
            statement = []
    return False


EVIDENCE = {
    "python_default": lambda t, v=None: python_default(t),
    "python_argument": python_argument, "python_call": python_call, "python_event_store_path": python_event_store_path,
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
        manifest = load_fixture()["tracked_executable_sources"]
        git_names, git_errors = git_source_names(ROOT)
        if git_names is None:
            self.fail("NEEDS_GATE: git executable required for independent count parity")
        archive_names = archive_source_names(ROOT)
        self.assertEqual(git_errors, [])
        inventory = load_fixture()
        self.assertEqual((len(inventory["direct_default"]), len(inventory["inherited_explicit_only"]), len(inventory["excluded"])), (11, 8, 1))
        self.assertEqual(
            102, len(manifest),
            "bound 94 + H2 monitor matrix + H3 extension matrix/child TypeScript sources + lineage pair"
            " + follow-up delivery trio (send-status verb, its tests, fake Herdr daemon)",
        )
        for names in (manifest, git_names, archive_names):
            self.assertEqual(names, sorted(set(names)))
            self.assertEqual(len(names), 102)
            self.assertEqual(names, manifest)
        self.assertEqual((len(manifest), len(git_names), len(archive_names)), (102, 102, 102))
        for mode in ("auto", "archive"):
            sources, errors = self.current(mode)
            self.assertEqual(audit(load_fixture(), sources, errors), [])

    def test_git_failure_and_invalid_output_fail_closed(self):
        with mock.patch("shutil.which", return_value="/fake/git"):
            with mock.patch("subprocess.run", side_effect=OSError("exec failed")):
                _, errors = self.current()
                self.assertTrue(any("git inventory failed closed: exec failed" in e for e in errors))
            with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 2, b"", b"boom")):
                _, errors = self.current()
                self.assertTrue(any("git inventory failed closed" in e for e in errors))
            bad = subprocess.CompletedProcess([], 0, b"garbage\0", b"")
            with mock.patch("subprocess.run", return_value=bad):
                _, errors = self.current()
                self.assertTrue(any("invalid ls-files output" in e for e in errors))

    def test_git_record_validation_and_outside_symlink_fail_closed(self):
        sha = "a" * 40
        malformed = [
            f"100644 {sha} 0\t/absolute.py\0", f"100644 {sha} 0\ta/../escape.py\0",
            f"100644 {sha} 0\ta//noncanonical.py\0", f"100999 {sha} 0\tbad.py\0",
            f"100644 xyz 0\tbad.py\0", f"100644 {sha} 1\tstage.py\0",
            f"100644 {sha} 0\tdup.py\0" * 2,
            f"100644 {sha} 0\tconflict.py\0" + f"100755 {'b' * 40} 0\tconflict.py\0",
            f"100644 {'a' * 41} 0\tlength41.py\0", f"100644 {'a' * 63} 0\tlength63.py\0",
            f"100644 {'A' * 40} 0\tuppercase.py\0",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for data in malformed:
                with self.assertRaises((ValueError, UnicodeDecodeError)): parse_git_records(data.encode(), root)
            with self.assertRaises(UnicodeDecodeError): parse_git_records(b"100644 " + b"a" * 40 + b" 0\tbad\xff.py\0", root)
            outside = root.parent / "h8-outside.py"; outside.write_text("print('outside')\n")
            link = root / "outside.py"; link.symlink_to(outside)
            try:
                with self.assertRaises(ValueError): archive_source_names(root)
                with self.assertRaises(ValueError):
                    parse_git_records(f"120000 {sha} 0\toutside.py\0".encode(), root)
            finally:
                link.unlink(missing_ok=True); outside.unlink(missing_ok=True)
            with self.assertRaises(ValueError):
                parse_git_records(f"120000 {sha} 0\tmissing.py\0".encode(), root)
            internal = root / "real.py"; internal.write_text("print('not symlink evidence')\n")
            link = root / "internal.py"; link.symlink_to("real.py")
            self.assertEqual(parse_git_records(f"120000 {sha} 0\tinternal.py\0".encode(), root), [])

    def test_archive_uses_stored_executable_mode_not_effective_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); tool = root / "tool"
            tool.write_text("#!/bin/sh\nexit 0\n"); tool.chmod(0o755)
            with mock.patch("os.access", return_value=False):
                self.assertEqual(archive_source_names(root), ["tool"])

    def test_archive_omission_outside_root_addition_and_missing_file_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shutil.copytree(ROOT, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", ".worktrees", "__pycache__"))
            (root / "tools").mkdir(); (root / "tools/new.py").write_text("print('x')\n")
            (root / "vendor").mkdir(exist_ok=True); (root / "vendor/hidden.py").write_text("print('tracked archive authority')\n")
            self.assertIn("vendor/hidden.py", archive_source_names(root))
            _, errors = tracked_sources(root, mode="archive")
            self.assertIn("tracked-source manifest differs from source surface", errors)
            (root / "tools/new.py").unlink(); (root / "vendor/hidden.py").unlink(); (root / "bin/rzr-monitor.py").unlink()
            _, errors = tracked_sources(root, mode="archive")
            self.assertIn("tracked-source manifest differs from source surface", errors)

    def test_real_git_boundary_excludes_tracked_untracked_and_ignored(self):
        if shutil.which("git") is None:
            self.fail("NEEDS_GATE: git executable required for tracked classification")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text("ignored.py\n")
            tracked, untracked, ignored = (root / name for name in ("tracked.py", "untracked.py", "ignored.py"))
            try:
                for path in (tracked, untracked, ignored): path.write_text("print('candidate')\n")
                subprocess.run(["git", "add", ".gitignore", "tracked.py"], cwd=root, check=True)
                self.assertEqual(subprocess.run(["git", "check-ignore", "-q", "ignored.py"], cwd=root).returncode, 0)
                names, errors = git_source_names(root)
                self.assertEqual(errors, [])
                self.assertIn("tracked.py", names)
                self.assertNotIn("untracked.py", names)
                self.assertNotIn("ignored.py", names)
            finally:
                for path in (tracked, untracked, ignored): path.unlink(missing_ok=True)

    def test_injected_git_boundary_excludes_real_untracked_and_ignored_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked, untracked, ignored = (root / name for name in ("tracked.py", "untracked.py", "ignored.py"))
            try:
                for path in (tracked, untracked, ignored): path.write_text("print('real candidate')\n")
                self.assertTrue(all(path.is_file() for path in (tracked, untracked, ignored)))
                supplied_ignored = {"ignored.py"}
                self.assertIn(ignored.name, supplied_ignored)
                record = f"100644 {'a' * 40} 0\ttracked.py\0".encode()
                self.assertEqual(parse_git_records(record, root), ["tracked.py"])
                self.assertNotIn("untracked.py", parse_git_records(record, root))
                self.assertNotIn("ignored.py", parse_git_records(record, root))
            finally:
                for path in (tracked, untracked, ignored): path.unlink(missing_ok=True)

    def test_semantic_decoys_are_rejected_for_every_language(self):
        full = 'os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") or "~/.rozoro"'
        for decoy in (f'NOTE={full!r}\n', f'NOTE=({full!r}, "ROZORO_HOME", "RZR_HOME", "~/.rozoro")\n',
                      f'"""{full}"""\n',
                      'NOTE=(os.environ.get("ROZORO_HOME"), os.environ.get("RZR_HOME"), "~/.rozoro")\n',
                      'NOTE={"calls": [os.environ.get("ROZORO_HOME"), os.environ.get("RZR_HOME")], "default": "~/.rozoro"}\n'):
            self.assertFalse(python_default(decoy))
        shell = "${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}"
        self.assertTrue(shell_default(f'RZR_HOME_RAW="{shell}"\n'))
        self.assertTrue(shell_default(f'RZR_HOME_RAW={shell}\n'))
        self.assertTrue(shell_default('RZR_HOME_RAW="${ROZORO_HOME:-${RZR_HOME:-${HOME}/.rozoro}}"\n'))
        for decoy in (
            f"# RZR_HOME_RAW={shell}\nRZR_HOME_RAW='{shell}'\nNOTE=\"{shell}\"\n",
            f'RZR_HOME_RAW="$(printf %s "{shell}")"\n',
            f'RZR_HOME_RAW=wrong; printf %s "{shell}"\n',
            f'RZR_HOME_RAW=wrong\nprintf %s "{shell}"\n',
            f'RZR_HOME_RAW=wrong\nNOTE="{shell}"\n',
            '${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}\n',
            'RZR_HOME_RAW=${RZR_HOME:-${ROZORO_HOME:-$HOME/.rozoro}}\n',
            'RZR_HOME_RAW=${ROZORO_HOME:-${RZR_HOME:-$HOME/other}}\n',
            'RZR_HOME_RAW=${ROZORO_HOME-${RZR_HOME:-$HOME/.rozoro}}\n',
            f'RZR_HOME_RAW={shell}\nRZR_HOME_RAW={shell}\n',
            f'RZR_HOME_RAW={shell}; true\n',
        ):
            self.assertFalse(shell_default(decoy))
        ts = 'process.env.ROZORO_HOME || process.env.RZR_HOME || join(homedir(), ".rozoro")'
        for decoy in (f'const selectedHome = "{ts}";', f'const selectedHome = `{ts}`;',
                      f'const selectedHome = [{ts}];', f'const selectedHome = {{value: {ts}}};',
                      f'const selectedHome = arbitrary({ts});', f'const selectedHome = resolve({ts}, "extra");',
                      r'const selectedHome = /process.env.ROZORO_HOME.*process.env.RZR_HOME.*homedir.*\\.rozoro/;',
                      'const selectedHome = process.env.ROZORO_HOME\nprocess.env.RZR_HOME || join(homedir(), ".rozoro")',
                      'const selectedHome = process.env.ROZORO_HOME // split by ASI\n|| process.env.RZR_HOME || join(homedir(), ".rozoro")'):
            self.assertFalse(typescript_default(decoy))
        self.assertTrue(typescript_default(f'const selectedHome = {ts};'))
        self.assertTrue(typescript_default(f'const selectedHome = resolve({ts});'))
        self.assertTrue(typescript_default(f'return path.resolve({ts});'))
        self.assertFalse(monitor_home_delegate('NOTE=("--home", "MonitorServer", "args.home")\n'))
        self.assertFalse(python_argument('# parser.add_argument("--store")\nNOTE="--store"\n', "--store"))

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
        assignment = 'RZR_HOME_RAW="${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}"'
        reviewer = 'RZR_HOME_RAW=wrong; printf %s "${ROZORO_HOME:-${RZR_HOME:-$HOME/.rozoro}}"'
        for path in ("bin/rzr-lib.sh", "bin/rzr-doctor.sh"):
            mutant = dict(sources)
            self.assertEqual(mutant[path].count(assignment), 1)
            mutant[path] = mutant[path].replace(assignment, reviewer)
            self.assertTrue(any(path in e and "no semantic source evidence" in e
                                for e in audit(load_fixture(), mutant)))
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
