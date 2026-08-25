#!/usr/bin/env python3
"""Persist an immutable, owner-private snapshot of explicit Watchtower policy."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

SCRIPT_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPT_REPO))

from lib.rozoro_artifacts.safe_fs import SafeDirectory, UnsafePath  # noqa: E402

SCHEMA = "rozoro.watchtower-policy-snapshot/v2"
SOURCE = "templates/watchtower.md"
PI_LAUNCHER = "bin/rzr-pi-watchtower.sh"
CLAUDE_LAUNCHER = "bin/rzr-claude-watchtower.sh"


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


def git_value(repo: Path, *args: str, input_bytes: bytes | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            input=input_bytes,
            check=True,
            capture_output=True,
            timeout=10,
        )
        return result.stdout.decode("utf-8", "strict").strip() or None
    except (OSError, UnicodeError, subprocess.SubprocessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, help="Rozoro checkout (normally auto-detected)")
    parser.add_argument("--artifact-root", type=Path, help="override $ROZORO_HOME/artifacts")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo_path = Path(os.path.abspath(os.path.expanduser(os.fspath(args.repo_root or SCRIPT_REPO))))
    try:
        with SafeDirectory.open_path(repo_path, create=False, require_owner=True) as repo:
            source_bytes = read_repo_file(repo, SOURCE)
            pi_launcher = read_repo_file(repo, PI_LAUNCHER)
            claude_launcher = read_repo_file(repo, CLAUDE_LAUNCHER)
    except UnsafePath as exc:
        raise SystemExit(str(exc)) from exc

    source_marker = SOURCE.encode()
    if source_marker not in pi_launcher:
        raise SystemExit(f"cannot verify {SOURCE} as the explicit Pi Watchtower policy source")
    pi_captured = True
    claude_captured = source_marker in claude_launcher
    applicable = ["pi"] + (["claude"] if claude_captured else [])

    home = Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    artifact_root = args.artifact_root or home / "artifacts"
    now = utc_now(args.now)
    created_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")

    commit = git_value(repo_path, "rev-parse", "HEAD")
    tracked_blob = git_value(repo_path, "rev-parse", f"HEAD:{SOURCE}")
    current_blob = git_value(repo_path, "hash-object", "--stdin", input_bytes=source_bytes)
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
            "matches_git_commit": tracked_blob == current_blob if tracked_blob and current_blob else None,
        },
        "harness_coverage": {
            "pi": {
                "status": "captured" if pi_captured else "not-captured",
                "launcher": PI_LAUNCHER,
                "launcher_sha256": digest(pi_launcher),
            },
            "claude": {
                "status": "captured" if claude_captured else "no-explicit-reference-to-captured-source",
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
