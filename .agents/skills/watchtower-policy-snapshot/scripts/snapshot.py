#!/usr/bin/env python3
"""Persist an immutable, owner-private snapshot of explicit Watchtower policy."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPT_REPO))

from lib.rozoro_artifacts.safe_fs import SafeDirectory, UnsafePath  # noqa: E402

SCHEMA = "rozoro.watchtower-policy-snapshot/v8"
SOURCE = "templates/watchtower.md"
PI_LAUNCHER = "bin/rzr-pi-watchtower.sh"
PI_LAUNCHER_SHA256 = "3281261fcd02c9041593df78acc9c9d11b2fe533c4672a73813b6ab022de8ee5"
CLAUDE_LAUNCHER = "bin/rzr-claude-watchtower.sh"
POLICY_OPTION = "--append-system-prompt"
POLICY_VALUE = "$ROOT/templates/watchtower.md"
GIT_OBJECT_ID = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")


def utc_now(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_repo_file(repo: SafeDirectory, relative: str) -> bytes:
    parts = relative.split("/")
    current = repo
    opened: list[SafeDirectory] = []
    try:
        for component in parts[:-1]:
            current = current.open_child(component, require_owner=True)
            opened.append(current)
        state, data = current.read_regular(parts[-1])
        if state != "regular" or data is None:
            raise UnsafePath(f"required repository source {relative} is {state}")
        return data
    finally:
        for directory in reversed(opened):
            directory.close()


def shell_tokens(line: str) -> list[str]:
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars="();=+")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        return list(lexer)
    except ValueError as exc:
        raise UnsafePath("launcher is not valid tokenizable shell source") from exc


def pi_launcher_contract_has_policy(source: bytes) -> bool:
    """Validate the one shipped top-level args + exec-env-pi contract, or fail closed."""
    try:
        lines = source.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise UnsafePath("launcher is not valid UTF-8 shell source") from exc
    block_depth = 0
    args: list[str] = []
    writes_valid = True
    invocation_results: list[bool] = []
    expected_invocation = ["exec", "env", "ROZORO_WATCHTOWER", "=", "1", "pi", "${args[@]}", "$@"]
    openers = {"if", "case", "for", "while", "until", "select"}
    closers = {"fi", "esac", "done"}

    for line in lines:
        tokens = shell_tokens(line)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token == "args":
                if index + 1 >= len(tokens) or tokens[index + 1] not in {"=(", "+=("}:
                    writes_valid = False
                    index += 1
                    continue
                operation = tokens[index + 1]
                cursor = index + 2
                depth = 1
                values: list[str] = []
                while cursor < len(tokens) and depth:
                    current = tokens[cursor]
                    if current == "(":
                        depth += 1
                    elif current == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    if depth:
                        values.append(current)
                    cursor += 1
                if depth != 0:
                    writes_valid = False
                    break
                complete_top_level = block_depth == 0 and index == 0 and cursor == len(tokens) - 1
                if operation == "=(":
                    if complete_top_level:
                        args = values
                    else:
                        writes_valid = False
                elif complete_top_level:
                    args.extend(values)
                index = cursor
            elif token.startswith("args["):
                writes_valid = False
            index += 1
        if block_depth == 0 and tokens == expected_invocation:
            invocation_results.append(
                any(left == POLICY_OPTION and right == POLICY_VALUE for left, right in zip(args, args[1:], strict=False))
            )
        for token in tokens:
            if token in openers or token == "{":
                block_depth += 1
            elif token in closers or token == "}":
                block_depth = max(0, block_depth - 1)
    return writes_valid and len(invocation_results) == 1 and invocation_results[0]


def reserve_run(root: SafeDirectory, now: dt.datetime) -> tuple[SafeDirectory, str]:
    with root.open_or_create_private_child("watchtower-policy-snapshots") as category:
        with category.open_or_create_private_child(now.strftime("%Y-%m-%d")) as date_dir:
            stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
            for _ in range(20):
                run_id = f"{stamp}-{secrets.token_hex(4)}"
                try:
                    return date_dir.open_or_create_private_child(run_id, exclusive=True), run_id
                except FileExistsError:
                    continue
    raise SystemExit("could not reserve a unique artifact directory")


def repo_identity(repo: SafeDirectory) -> tuple[int, int]:
    info = repo.stat()
    return info.st_dev, info.st_ino


def path_matches_identity(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with SafeDirectory.open_path(path, create=False, require_owner=True) as reopened:
            return repo_identity(reopened) == expected
    except (OSError, UnsafePath):
        return False


def bound_git_value(
    repo_path: Path,
    expected: tuple[int, int],
    *args: str,
    input_bytes: bytes | None = None,
) -> tuple[str | None, str]:
    """Accept Git output only while the lexical path stays bound to the held repo inode."""
    if not path_matches_identity(repo_path, expected):
        return None, "repository-path-identity-mismatch-before-read"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            input=input_bytes,
            check=True,
            capture_output=True,
            timeout=10,
        )
        value = result.stdout.decode("utf-8", "strict").strip() or None
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return None, "git-read-failed"
    if not path_matches_identity(repo_path, expected):
        return None, "repository-path-identity-mismatch-after-read"
    if value is None or not GIT_OBJECT_ID.fullmatch(value):
        return None, "git-read-failed-empty-or-invalid-object-id"
    return value.lower(), "verified"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, help="Rozoro checkout (normally auto-detected)")
    parser.add_argument("--artifact-root", type=Path, help="override $ROZORO_HOME/artifacts")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo_path = Path(os.path.abspath(os.path.expanduser(os.fspath(args.repo_root or SCRIPT_REPO))))
    try:
        with SafeDirectory.open_path(repo_path, create=False, require_owner=True) as repo:
            identity = repo_identity(repo)
            source_bytes = read_repo_file(repo, SOURCE)
            pi_launcher = read_repo_file(repo, PI_LAUNCHER)
            claude_launcher = read_repo_file(repo, CLAUDE_LAUNCHER)
            exact_pi_launcher = digest(pi_launcher) == PI_LAUNCHER_SHA256
            pi_captured = exact_pi_launcher and pi_launcher_contract_has_policy(pi_launcher)
            claude_captured = False
            if not exact_pi_launcher:
                raise UnsafePath("Pi launcher bytes do not match the strict shipped launcher contract")
            if not pi_captured:
                raise UnsafePath(f"cannot verify {SOURCE} in an args array consumed by the Pi invocation")
            commit_read = bound_git_value(repo_path, identity, "rev-parse", "HEAD")
            tracked_read = bound_git_value(repo_path, identity, "rev-parse", f"HEAD:{SOURCE}")
            current_read = bound_git_value(repo_path, identity, "hash-object", "--stdin", input_bytes=source_bytes)
    except (OSError, UnsafePath) as exc:
        raise SystemExit(str(exc)) from exc

    git_reads = (commit_read, tracked_read, current_read)
    git_verified = all(status == "verified" for _, status in git_reads)
    git_reason = None if git_verified else ";".join(sorted({status for _, status in git_reads if status != "verified"}))
    commit, tracked_blob, current_blob = (read[0] for read in git_reads) if git_verified else (None, None, None)
    applicable = ["pi"] + (["claude"] if claude_captured else [])
    identity_id = "fs-" + digest(f"{identity[0]}:{identity[1]}".encode())[:20]

    home = Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    artifact_root = args.artifact_root or home / "artifacts"
    now = utc_now(args.now)
    created_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    snapshot_name = "watchtower-policy.md"
    metadata = {
        "schema": SCHEMA,
        "artifact_type": "watchtower-policy-snapshot",
        "created_at": created_at,
        "source": {
            "repository_relative_path": SOURCE,
            "role": "explicit Watchtower launch policy source",
            "applies_to_harnesses": applicable,
            "sha256": digest(source_bytes),
            "bytes": len(source_bytes),
            "git_commit": commit,
            "git_blob_at_commit": tracked_blob,
            "git_blob_current": current_blob,
            "matches_git_commit": tracked_blob == current_blob if git_verified and tracked_blob and current_blob else None,
        },
        "git_provenance": {
            "status": "verified" if git_verified else "indeterminate",
            "method": "held-directory-identity-verified-before-and-after-each-git-read",
            "repository_identity": identity_id,
            "reason": git_reason,
        },
        "harness_coverage": {
            "validation": "exact-shipped-pi-launcher-sha256-plus-grammar-v1",
            "expected_pi_launcher_sha256": PI_LAUNCHER_SHA256,
            "option": POLICY_OPTION,
            "value": POLICY_VALUE,
            "pi": {
                "status": "captured" if pi_captured else "unverified-no-consumed-policy-args-array",
                "launcher": PI_LAUNCHER,
                "launcher_sha256": digest(pi_launcher),
            },
            "claude": {
                "status": "captured" if claude_captured else "unverified-no-consumed-policy-args-array",
                "launcher": CLAUDE_LAUNCHER,
                "launcher_sha256": digest(claude_launcher),
            },
        },
        "files": {snapshot_name: {"sha256": digest(source_bytes), "bytes": len(source_bytes)}},
        "privacy": {
            "included": [SOURCE, "non-content launcher hashes and coverage"],
            "excluded": ["environment", "credentials", "task data", "session data", "absolute repository paths"],
        },
        "retention": "preserve-until-explicit-operator-deletion",
    }

    try:
        with SafeDirectory.open_path(artifact_root, create=True, require_owner=True, private=True) as root:
            run, run_id = reserve_run(root, now)
            with run:
                metadata["run_id"] = run_id
                run.write_exclusive(snapshot_name, source_bytes)
                run.write_exclusive("metadata.json", (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())
                output = run.path
    except (OSError, UnsafePath) as exc:
        raise SystemExit(f"cannot create safe artifact: {exc}") from exc
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
