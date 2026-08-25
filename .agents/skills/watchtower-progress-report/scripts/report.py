#!/usr/bin/env python3
"""Create a conservative dated report from durable Rozoro task folders."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sys
import types
from pathlib import Path
from typing import Any

SCRIPT_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPT_REPO))

from lib.rozoro_artifacts.safe_fs import SafeDirectory, UnsafePath  # noqa: E402

SCHEMA = "rozoro.watchtower-progress-report/v2"
SAFE_TASK = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
BAD_AUXILIARY = {"missing", "unsafe", "unreadable", "malformed"}
NONE = {"", "none", "n/a", "na", "-"}


def utc_now(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reserve_run(root: SafeDirectory, now: dt.datetime) -> tuple[SafeDirectory, str]:
    with root.open_or_create_private_child("watchtower-progress-reports") as category:
        with category.open_or_create_private_child(now.strftime("%Y-%m-%d")) as date_dir:
            stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
            for _ in range(20):
                run_id = f"{stamp}-{secrets.token_hex(4)}"
                try:
                    return date_dir.open_or_create_private_child(run_id, exclusive=True), run_id
                except FileExistsError:
                    continue
    raise SystemExit("could not reserve a unique artifact directory")


def json_shape(task: SafeDirectory, name: str) -> str:
    state, data = task.read_regular(name)
    if state != "regular" or data is None:
        return state
    try:
        return "valid" if isinstance(json.loads(data.decode("utf-8")), dict) else "malformed"
    except (UnicodeError, json.JSONDecodeError):
        return "malformed"


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


def load_handoff_parser(repo: SafeDirectory):
    relative = "lib/rozoro_monitor/handoff.py"
    source = read_repo_file(repo, relative)
    module = types.ModuleType("dated_artifact_handoff")
    module.__file__ = relative
    exec(compile(source, relative, "exec"), module.__dict__)  # noqa: S102 - validated checkout-owned source
    if not hasattr(module, "parse_text"):
        raise SystemExit("canonical handoff parser lacks captured-text support")
    return module


def cursor_value(state: str, data: bytes | None) -> int | str | None:
    if state == "missing":
        return None
    if state != "regular" or data is None:
        return None
    try:
        value = int(data.decode("utf-8").strip())
        if value < 0:
            raise ValueError
        return value
    except (UnicodeError, ValueError):
        return "invalid"


def inspect_task(task_id: str, task: SafeDirectory, parser_module: Any) -> dict[str, Any]:
    handoff_state, handoff_bytes = task.read_regular("handoff.md")
    ack_v2_state, ack_v2_bytes = task.read_regular(".acked-blocks-v2")
    ack_legacy_state, ack_legacy_bytes = task.read_regular(".acked-blocks")
    ack_states = {"v2": ack_v2_state, "legacy": ack_legacy_state}
    record: dict[str, Any] = {
        "task_id": task_id,
        "identity_json": json_shape(task, "identity.json"),
        "session_json": json_shape(task, "session.json"),
        "ack_cursor_files": ack_states,
        "handoff": {
            "file_state": handoff_state,
            "sha256": digest(handoff_bytes) if handoff_bytes is not None else None,
            "bytes": len(handoff_bytes) if handoff_bytes is not None else None,
        },
        "classifications": [],
    }
    if handoff_state != "regular" or handoff_bytes is None:
        record["classifications"].append("unknown-or-malformed")
        return record
    try:
        parsed = parser_module.parse_text(
            handoff_bytes.decode("utf-8"),
            cursor_value(ack_v2_state, ack_v2_bytes),
            cursor_value(ack_legacy_state, ack_legacy_bytes),
        )
    except (UnicodeError, ValueError):
        record["handoff"].update({"parse_state": "unreadable", "protocol_error_count": 1})
        record["classifications"].append("unknown-or-malformed")
        return record

    latest = parsed["latest"]
    open_items = [
        {
            "turn": item["turn"],
            "verdict": item["verdict"].lower(),
            "operator_input_requested": item["inputs_needed"].strip().lower() not in NONE,
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
                "index": latest["index"],
                "turn": latest["turn"],
                "verdict": latest["fields"].get("verdict", "").lower(),
                "valid": latest["valid"],
                "acknowledged": latest["index"] <= parsed["acked_through"],
            },
        }
    )

    evidence_problem = (
        bool(parsed["protocol_errors"])
        or latest is None
        or record["identity_json"] in BAD_AUXILIARY
        or record["session_json"] in BAD_AUXILIARY
        or any(state in {"unsafe", "unreadable"} for state in ack_states.values())
    )
    if evidence_problem:
        record["classifications"].append("unknown-or-malformed")

    latest_unacknowledged = latest is not None and latest["index"] > parsed["acked_through"]
    if latest is not None and not latest_unacknowledged and not evidence_problem:
        record["classifications"].append("acknowledged-report-no-current-outcome")
    if latest is not None and latest["valid"] and latest_unacknowledged and not evidence_problem:
        verdict = latest["fields"].get("verdict", "").lower()
        if verdict == "waiting":
            record["classifications"].append("reported-active-runtime-unverified")
        elif verdict in {"blocked", "failed"}:
            record["classifications"].append("blocker-or-failure")
        elif verdict == "needs-action":
            record["classifications"].append("human-decision-needed")
        elif verdict == "done":
            record["classifications"].append("reported-done-unverified")
    if not evidence_problem:
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


def render_report(created_at: str, records: list[dict[str, Any]], skipped: int, source: dict[str, Any]) -> str:
    canonical = sum(record["handoff"].get("parse_state") == "canonical" for record in records)
    lines = [
        "# Watchtower progress report",
        "",
        f"Generated: `{created_at}`",
        "",
        "This is a point-in-time reading of securely captured durable task files. It does not read live runtime state, repository/PR/CI state, prompts, transcripts, environment variables, or session contents. Free-form handoff text is deliberately excluded.",
        "",
        "## Verified durable facts",
        "",
        f"- Source selection: `{source['selection']}`; root identifier: `{source['root_id']}`.",
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
        "## Acknowledged reports (not current outcomes)",
        "",
        "Task acknowledgement means the report/open item was handled; it does not establish correctness or operator acceptance.",
        "",
        *bullet_tasks(records, "acknowledged-report-no-current-outcome", "None found."),
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
        "- Files are opened without following symlinks and parsed from the captured bytes identified by those digests.",
        "- Brief text, handoff prose, cwd values, session identifiers, credentials, environment, daemon databases, and live host state are excluded.",
        "- Artifacts are owner-private and retained until an operator explicitly deletes the exact run directory.",
        "",
    ]
    return "\n".join(lines)


def source_provenance(tasks: SafeDirectory, explicit: bool) -> dict[str, str]:
    info = tasks.stat()
    root_id = "fs-" + digest(f"{info.st_dev}:{info.st_ino}".encode())[:20]
    return {
        "selection": "explicit-override" if explicit else "default-rozoro-home",
        "display": "<explicit-tasks-root>" if explicit else "$ROZORO_HOME/tasks",
        "root_id": root_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, help="Rozoro checkout (normally auto-detected)")
    parser.add_argument("--tasks-root", type=Path, help="override $ROZORO_HOME/tasks")
    parser.add_argument("--artifact-root", type=Path, help="override $ROZORO_HOME/artifacts")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()

    repo_path = Path(os.path.abspath(os.path.expanduser(os.fspath(args.repo_root or SCRIPT_REPO))))
    try:
        with SafeDirectory.open_path(SCRIPT_REPO, create=False, require_owner=True) as shipped_repo:
            shipped_identity = (shipped_repo.stat().st_dev, shipped_repo.stat().st_ino)
        with SafeDirectory.open_path(repo_path, create=False, require_owner=True) as repo:
            effective_identity = (repo.stat().st_dev, repo.stat().st_ino)
            if effective_identity != shipped_identity:
                raise UnsafePath("--repo-root must identify the checkout that owns this skill")
            parser_module = load_handoff_parser(repo)
    except (OSError, UnsafePath) as exc:
        raise SystemExit(f"cannot safely load canonical handoff parser: {exc}") from exc

    home = Path(os.environ.get("ROZORO_HOME", "~/.rozoro")).expanduser()
    tasks_path = args.tasks_root or home / "tasks"
    artifact_root = args.artifact_root or home / "artifacts"

    records: list[dict[str, Any]] = []
    skipped = 0
    try:
        with SafeDirectory.open_path(tasks_path, create=False, require_owner=True) as tasks:
            source = source_provenance(tasks, args.tasks_root is not None)
            for name in sorted(tasks.list_names()):
                if not SAFE_TASK.fullmatch(name):
                    skipped += 1
                    continue
                try:
                    task = tasks.open_child(name, require_owner=True)
                except (OSError, UnsafePath):
                    skipped += 1
                    continue
                with task:
                    records.append(inspect_task(name, task, parser_module))
    except (OSError, UnsafePath) as exc:
        raise SystemExit(f"cannot safely scan required task root: {exc}") from exc

    now = utc_now(args.now)
    created_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    evidence = {
        "schema": SCHEMA,
        "artifact_type": "watchtower-progress-report-evidence",
        "created_at": created_at,
        "source": source,
        "scan_consistency": "descriptor-captured-per-file-bytes",
        "skipped_unsafe_or_invalid_entries": skipped,
        "tasks": records,
    }
    report_bytes = render_report(created_at, records, skipped, source).encode()

    try:
        with SafeDirectory.open_path(artifact_root, create=True, require_owner=True, private=True) as root:
            run, run_id = reserve_run(root, now)
            with run:
                evidence["run_id"] = run_id
                evidence_bytes = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
                metadata = {
                    "schema": SCHEMA,
                    "artifact_type": "watchtower-progress-report",
                    "created_at": created_at,
                    "run_id": run_id,
                    "source": {**source, "task_count": len(records)},
                    "files": {
                        "report.md": {"sha256": digest(report_bytes), "bytes": len(report_bytes)},
                        "evidence.json": {"sha256": digest(evidence_bytes), "bytes": len(evidence_bytes)},
                    },
                    "privacy": {
                        "included": ["task ids", "handoff structure/status", "ack structure", "file presence and digests"],
                        "excluded": ["free-form task text", "briefs", "cwd values", "session contents", "environment", "credentials", "live runtime and daemon databases", "absolute source paths"],
                    },
                    "retention": "preserve-until-explicit-operator-deletion",
                }
                run.write_exclusive("evidence.json", evidence_bytes)
                run.write_exclusive("report.md", report_bytes)
                run.write_exclusive("metadata.json", (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())
                output = run.path
    except (OSError, UnsafePath) as exc:
        raise SystemExit(f"cannot create safe artifact: {exc}") from exc
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
