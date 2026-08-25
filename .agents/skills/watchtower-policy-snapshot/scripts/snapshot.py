#!/usr/bin/env python3
"""Persist an immutable, owner-private snapshot of the active Watchtower prompt."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import stat
import subprocess
from pathlib import Path

SCHEMA = "rozoro.watchtower-policy-snapshot/v1"
SOURCE = Path("templates/watchtower.md")


def utc_now(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_private_dir(path: Path) -> None:
    if path.is_symlink():
        raise SystemExit(f"refusing symlink artifact directory: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise SystemExit(f"artifact directory is not an owned directory: {path}")
    path.chmod(0o700)


def new_run_dir(root: Path, category: str, now: dt.datetime) -> tuple[Path, str]:
    ensure_private_dir(root)
    category_dir = root / category
    date_dir = category_dir / now.strftime("%Y-%m-%d")
    ensure_private_dir(category_dir)
    ensure_private_dir(date_dir)
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    for _ in range(20):
        run_id = f"{stamp}-{secrets.token_hex(4)}"
        path = date_dir / run_id
        try:
            path.mkdir(mode=0o700)
            return path, run_id
        except FileExistsError:
            continue
    raise SystemExit("could not reserve a unique artifact directory")


def write_private(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def git_value(repo: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, help="Rozoro checkout (normally auto-detected)")
    parser.add_argument("--artifact-root", type=Path, help="override $ROZORO_HOME/artifacts")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo = (args.repo_root or Path(__file__).resolve().parents[4]).resolve()
    source = repo / SOURCE
    if source.is_symlink() or not source.is_file():
        raise SystemExit(f"active Watchtower policy source is not a regular file: {source}")
    source_bytes = source.read_bytes()

    home = Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    artifact_root = (args.artifact_root or home / "artifacts").expanduser()
    now = utc_now(args.now)
    created_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    run_dir, run_id = new_run_dir(artifact_root, "watchtower-policy-snapshots", now)

    snapshot_name = "watchtower-policy.md"
    write_private(run_dir / snapshot_name, source_bytes)
    commit = git_value(repo, "rev-parse", "HEAD")
    tracked_blob = git_value(repo, "rev-parse", f"HEAD:{SOURCE.as_posix()}")
    current_blob = git_value(repo, "hash-object", "--", str(source))
    metadata = {
        "schema": SCHEMA,
        "artifact_type": "watchtower-policy-snapshot",
        "created_at": created_at,
        "run_id": run_id,
        "source": {
            "repository_relative_path": SOURCE.as_posix(),
            "role": "launch-time Watchtower system prompt",
            "sha256": digest(source_bytes),
            "bytes": len(source_bytes),
            "git_commit": commit,
            "git_blob_at_commit": tracked_blob,
            "git_blob_current": current_blob,
            "matches_git_commit": tracked_blob == current_blob if tracked_blob and current_blob else None,
        },
        "files": {snapshot_name: {"sha256": digest(source_bytes), "bytes": len(source_bytes)}},
        "privacy": {
            "included": [SOURCE.as_posix()],
            "excluded": ["environment", "credentials", "task data", "session data", "repository paths"],
        },
        "retention": "preserve-until-explicit-operator-deletion",
    }
    encoded = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    write_private(run_dir / "metadata.json", encoded)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
