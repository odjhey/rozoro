#!/usr/bin/env python3
"""Persist an immutable, owner-private snapshot of explicit Watchtower policy."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPT_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPT_REPO))

from lib.rozoro_artifacts.safe_fs import SafeDirectory, UnsafePath  # noqa: E402

SCHEMA = "rozoro.watchtower-policy-snapshot/v3"
SOURCE = "templates/watchtower.md"
PI_LAUNCHER = "bin/rzr-pi-watchtower.sh"
CLAUDE_LAUNCHER = "bin/rzr-claude-watchtower.sh"
POLICY_OPTION = "--append-system-prompt"
POLICY_VALUE = "$ROOT/templates/watchtower.md"


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


def assigned_launcher_args(source: bytes) -> list[str]:
    """Extract shell words assigned to the launcher's args array, excluding comments."""
    try:
        lexer = shlex.shlex(source.decode("utf-8"), posix=True, punctuation_chars="()=+")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
    except (UnicodeError, ValueError) as exc:
        raise UnsafePath("launcher is not valid tokenizable UTF-8 shell source") from exc
    assigned: list[str] = []
    index = 0
    while index + 1 < len(tokens):
        if tokens[index] == "args" and tokens[index + 1] in {"=(", "+=("}:
            index += 2
            depth = 1
            while index < len(tokens) and depth:
                token = tokens[index]
                if token == "(":
                    depth += 1
                elif token == ")":
                    depth -= 1
                    if depth == 0:
                        break
                if depth:
                    assigned.append(token)
                index += 1
        index += 1
    return assigned


def has_policy_argument(source: bytes) -> bool:
    args = assigned_launcher_args(source)
    return any(left == POLICY_OPTION and right == POLICY_VALUE for left, right in zip(args, args[1:]))


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
    return value, "verified"


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
            pi_captured = has_policy_argument(pi_launcher)
            claude_captured = has_policy_argument(claude_launcher)
            if not pi_captured:
                raise UnsafePath(f"cannot verify {SOURCE} as an args-array {POLICY_OPTION} value for Pi")
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
            "validation": "tokenized-shell-args-array-option-value",
            "option": POLICY_OPTION,
            "value": POLICY_VALUE,
            "pi": {
                "status": "captured" if pi_captured else "not-captured",
                "launcher": PI_LAUNCHER,
                "launcher_sha256": digest(pi_launcher),
            },
            "claude": {
                "status": "captured" if claude_captured else "no-policy-argument-for-captured-source",
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
