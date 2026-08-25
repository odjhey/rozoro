#!/usr/bin/env python3
"""Create a conservative dated report from durable Rozoro task folders."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

SCHEMA = "rozoro.watchtower-progress-report/v1"
SAFE_TASK = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


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


def new_run_dir(root: Path, now: dt.datetime) -> tuple[Path, str]:
    ensure_private_dir(root)
    category = root / "watchtower-progress-reports"
    date_dir = category / now.strftime("%Y-%m-%d")
    ensure_private_dir(category)
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


def json_shape(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_symlink() or not path.is_file():
        return "unsafe"
    try:
        return "valid" if isinstance(json.loads(path.read_text(encoding="utf-8")), dict) else "malformed"
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "malformed"


def regular_bytes(path: Path) -> bytes | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def load_handoff_parser(repo: Path):
    location = repo / "lib/rozoro_monitor/handoff.py"
    spec = importlib.util.spec_from_file_location("dated_artifact_handoff", location)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load canonical handoff parser: {location}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_task(task: Path, parser_module: Any) -> dict[str, Any]:
    handoff = task / "handoff.md"
    handoff_bytes = regular_bytes(handoff)
    ack_v2 = task / ".acked-blocks-v2"
    ack_legacy = task / ".acked-blocks"
    ack_states = {
        "v2": "missing" if not ack_v2.exists() else ("regular" if regular_bytes(ack_v2) is not None else "unsafe"),
        "legacy": "missing" if not ack_legacy.exists() else ("regular" if regular_bytes(ack_legacy) is not None else "unsafe"),
    }
    record: dict[str, Any] = {
        "task_id": task.name,
        "identity_json": json_shape(task / "identity.json"),
        "session_json": json_shape(task / "session.json"),
        "ack_cursor_files": ack_states,
        "handoff": {
            "file_state": "regular" if handoff_bytes is not None else ("missing" if not handoff.exists() else "unsafe"),
            "sha256": digest(handoff_bytes) if handoff_bytes is not None else None,
            "bytes": len(handoff_bytes) if handoff_bytes is not None else None,
        },
        "classifications": [],
    }
    if handoff_bytes is None:
        record["classifications"].append("unknown-or-malformed")
        return record
    try:
        if "unsafe" in ack_states.values():
            parsed = parser_module.parse(handoff)
        else:
            parsed = parser_module.parse_task_report(task)
    except (OSError, UnicodeError, ValueError):
        record["handoff"].update({"parse_state": "unreadable", "protocol_error_count": 1})
        record["classifications"].append("unknown-or-malformed")
        return record

    latest = parsed["latest"]
    open_items = [
        {
            "turn": item["turn"],
            "verdict": item["verdict"].lower(),
            "operator_input_requested": bool(item["inputs_needed"].strip().lower() not in {"", "none", "n/a", "na", "-"}),
        }
        for item in parsed["open_items"]
    ]
    record["handoff"].update(
        {
            "parse_state": "canonical" if not parsed["protocol_errors"] else "malformed",
            "blocks": parsed["blocks"],
            "acked_through": parsed["acked_through"],
            "acked_source": parsed["acked_source"],
            "unresolved": parsed["unresolved"],
            "protocol_error_count": len(parsed["protocol_errors"]),
            "open_items": open_items,
            "latest": None
            if latest is None
            else {
                "turn": latest["turn"],
                "verdict": latest["fields"].get("verdict", "").lower(),
                "valid": latest["valid"],
            },
        }
    )

    evidence_problem = (
        bool(parsed["protocol_errors"])
        or latest is None
        or record["identity_json"] in {"unsafe", "malformed"}
        or record["session_json"] in {"unsafe", "malformed"}
        or "unsafe" in ack_states.values()
    )
    if evidence_problem:
        record["classifications"].append("unknown-or-malformed")
    if latest is not None and latest["valid"] and not parsed["protocol_errors"]:
        verdict = latest["fields"].get("verdict", "").lower()
        if verdict == "waiting":
            record["classifications"].append("reported-active-runtime-unverified")
        elif verdict in {"blocked", "failed"}:
            record["classifications"].append("blocker-or-failure")
        elif verdict == "needs-action":
            record["classifications"].append("human-decision-needed")
        elif verdict == "done":
            record["classifications"].append("reported-done-unverified")
    if not parsed["protocol_errors"]:
        if any(item["operator_input_requested"] or item["verdict"] == "needs-action" for item in open_items):
            if "human-decision-needed" not in record["classifications"]:
                record["classifications"].append("human-decision-needed")
        if any(item["verdict"] in {"blocked", "failed"} for item in open_items):
            if "blocker-or-failure" not in record["classifications"]:
                record["classifications"].append("blocker-or-failure")
    return record


def bullet_tasks(records: list[dict[str, Any]], classification: str, empty: str) -> list[str]:
    selected = [record for record in records if classification in record["classifications"]]
    if not selected:
        return [f"- {empty}"]
    lines = []
    for record in selected:
        handoff = record["handoff"]
        latest = handoff.get("latest")
        detail = f"latest turn {latest['turn']}, verdict `{latest['verdict']}`" if latest else handoff["file_state"]
        if handoff.get("unresolved"):
            detail += f", {handoff['unresolved']} unresolved open item(s)"
        lines.append(f"- `{record['task_id']}` — {detail}.")
    return lines


def render_report(created_at: str, records: list[dict[str, Any]], skipped: int) -> str:
    canonical = sum(record["handoff"].get("parse_state") == "canonical" for record in records)
    lines = [
        "# Watchtower progress report",
        "",
        f"Generated: `{created_at}`",
        "",
        "This is a point-in-time, best-effort reading of durable task folders. It does not read live runtime state, repository/PR/CI state, prompts, transcripts, environment variables, or session contents. Free-form handoff text is deliberately excluded.",
        "",
        "## Verified durable facts",
        "",
        f"- Read {len(records)} safe task director{'y' if len(records) == 1 else 'ies'}; skipped {skipped} unsafe or invalid task entries.",
        f"- {canonical} task handoff(s) passed the canonical parser without protocol errors.",
        "- No task outcome is marked verified or operator-accepted by the evidence boundary used here. A `done` report is not acceptance.",
        "",
        "## Reported active work (runtime unverified)",
        "",
        "A valid `waiting` handoff is listed here only as a crew report. Durable task folders cannot certify current foreground/background activity.",
        "",
        *bullet_tasks(records, "reported-active-runtime-unverified", "None reported."),
        "",
        "## Blockers and failures",
        "",
        *bullet_tasks(records, "blocker-or-failure", "None found in canonical unacknowledged evidence."),
        "",
        "## Human decisions or input needed",
        "",
        "Question text remains in the source handoff and is not copied into this artifact.",
        "",
        *bullet_tasks(records, "human-decision-needed", "None found in canonical unacknowledged evidence."),
        "",
        "## Reported done (unverified and unaccepted)",
        "",
        *bullet_tasks(records, "reported-done-unverified", "None reported."),
        "",
        "## Unknown or malformed task state",
        "",
        *bullet_tasks(records, "unknown-or-malformed", "None found."),
        "",
        "## Provenance and safety",
        "",
        "- Machine-readable classifications and per-handoff SHA-256 digests are in `evidence.json`.",
        "- The scan is not transactional; each digest identifies the handoff bytes observed immediately before parsing, and a task may change during the scan.",
        "- Brief text, handoff prose, cwd values, session identifiers, credentials, environment, daemon databases, and live host state are excluded.",
        "- Artifacts are owner-private and retained until an operator explicitly deletes the exact run directory.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, help="Rozoro checkout (normally auto-detected)")
    parser.add_argument("--tasks-root", type=Path, help="override $ROZORO_HOME/tasks")
    parser.add_argument("--artifact-root", type=Path, help="override $ROZORO_HOME/artifacts")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo = (args.repo_root or Path(__file__).resolve().parents[4]).resolve()
    home = Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    tasks_root = (args.tasks_root or home / "tasks").expanduser()
    artifact_root = (args.artifact_root or home / "artifacts").expanduser()
    if tasks_root.is_symlink():
        raise SystemExit(f"refusing symlink task root: {tasks_root}")
    if tasks_root.exists() and (not tasks_root.is_dir() or tasks_root.stat().st_uid != os.geteuid()):
        raise SystemExit(f"task root is not an owned directory: {tasks_root}")

    parser_module = load_handoff_parser(repo)
    records: list[dict[str, Any]] = []
    skipped = 0
    if tasks_root.exists():
        for entry in sorted(tasks_root.iterdir(), key=lambda path: path.name):
            if (
                entry.is_symlink()
                or not entry.is_dir()
                or entry.stat(follow_symlinks=False).st_uid != os.geteuid()
                or not SAFE_TASK.fullmatch(entry.name)
            ):
                skipped += 1
                continue
            records.append(inspect_task(entry, parser_module))

    now = utc_now(args.now)
    created_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    run_dir, run_id = new_run_dir(artifact_root, now)
    evidence = {
        "schema": SCHEMA,
        "artifact_type": "watchtower-progress-report-evidence",
        "created_at": created_at,
        "run_id": run_id,
        "evidence_boundary": "$ROZORO_HOME/tasks safe regular files only",
        "scan_consistency": "point-in-time-best-effort-pre-parse-file-digests",
        "skipped_unsafe_or_invalid_entries": skipped,
        "tasks": records,
    }
    evidence_bytes = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
    report_bytes = render_report(created_at, records, skipped).encode()
    write_private(run_dir / "evidence.json", evidence_bytes)
    write_private(run_dir / "report.md", report_bytes)
    metadata = {
        "schema": SCHEMA,
        "artifact_type": "watchtower-progress-report",
        "created_at": created_at,
        "run_id": run_id,
        "source": {"task_root": "$ROZORO_HOME/tasks", "task_count": len(records)},
        "files": {
            "report.md": {"sha256": digest(report_bytes), "bytes": len(report_bytes)},
            "evidence.json": {"sha256": digest(evidence_bytes), "bytes": len(evidence_bytes)},
        },
        "privacy": {
            "included": ["task ids", "handoff structure/status", "ack structure", "file presence and digests"],
            "excluded": ["free-form task text", "briefs", "cwd values", "session contents", "environment", "credentials", "live runtime and daemon databases"],
        },
        "retention": "preserve-until-explicit-operator-deletion",
    }
    write_private(run_dir / "metadata.json", (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
