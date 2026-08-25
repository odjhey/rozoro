#!/usr/bin/env python3
"""Durable, file-based attention ledger for the Rozoro watchtower.

Interim, driver-private notebook that records the driver's own handling decisions and
observations as one markdown file per attention item under
``$ROZORO_HOME/watchtowers/attention/items/``. It approximates the ADR-0004 mailbox
*capability* so a fresh, cycled, or compacted watchtower session can re-prime from disk
instead of relying on its context window. It records driver decisions, never system truth:
it is not consumed by rozorod, does not replace ``rozoro ack`` / ``rozoro reconcile`` /
handoff verdicts, and acceptance still belongs to the operator.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import fcntl
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPT_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SCRIPT_REPO))

from lib.rozoro_artifacts.safe_fs import SafeDirectory, UnsafePath  # noqa: E402

SCHEMA = "rozoro.watchtower-attention-ledger/v1"

SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
GENERATION = re.compile(r"^\d{1,18}$")
FRONTMATTER_LINE = re.compile(r"^([a-z_]+): (.*)$")

REASONS = {
    "needs-action",
    "failed",
    "blocked",
    "quiescent",
    "missing-report",
    "malformed-report",
    "gone",
    "waiting-background",
    "no-mistakes",
    "operator",
    "other",
}
PRIORITIES = {"urgent", "normal"}
STATUSES = {"open", "handled", "deferred", "superseded"}
SOURCES = {"reconcile", "status", "operator", "manual"}

# Canonical frontmatter order; also the exact required key set.
FRONTMATTER_ORDER = [
    "schema",
    "id",
    "task",
    "reason",
    "priority",
    "status",
    "created_utc",
    "updated_utc",
    "generation",
    "source",
    "superseded_by",
    "resume_when",
    "tags",
]

SECTIONS = ("Snapshot", "Handling log", "Context")
NONE_TOKENS = {"", "none"}
DEFAULT_FIELDS = ["id", "task", "reason", "priority", "status", "updated_utc", "summary"]
LIST_FIELDS = set(FRONTMATTER_ORDER) | {"summary"}
LOCK_ATTEMPTS = 20
LOCK_INTERVAL = 0.05

DISCLAIMER = (
    "These are driver-recorded decisions and observations, not verified system state. "
    "`handled` here is not task open-item resolution, generation ACK, a handoff verdict, "
    "or operator acceptance."
)


class Malformed(Exception):
    """An item file violated the strict ledger contract."""


# --------------------------------------------------------------------------- time


def utc_now(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def stamp_seconds(now: dt.datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_compact(now: dt.datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S")


# ------------------------------------------------------------------------- parse


def sanitize_line(value: str) -> str:
    """Collapse a free-text field to a single stripped line for frontmatter/title use."""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def strip_outer_blanks(lines: list[str]) -> str:
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(lines[start:end])


def split_frontmatter(raw: bytes) -> tuple[list[str], list[str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Malformed("file is not valid UTF-8") from exc
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise Malformed("missing frontmatter opening '---'")
    try:
        close = lines.index("---", 1)
    except ValueError as exc:
        raise Malformed("missing frontmatter closing '---'") from exc
    return lines[1:close], lines[close + 1 :]


def parse_tags(value: str) -> list[str]:
    if not (value.startswith("[") and value.endswith("]")):
        raise Malformed("tags must be an inline list '[a, b]'")
    inner = value[1:-1].strip()
    if inner == "":
        return []
    tags: list[str] = []
    for token in inner.split(","):
        item = token.strip()
        if not SAFE_TOKEN.fullmatch(item):
            raise Malformed(f"tag not in the safe character class: {item!r}")
        tags.append(item)
    return tags


def parse_frontmatter(fm_lines: list[str], stem: str | None) -> dict[str, Any]:
    fm: dict[str, str] = {}
    for line in fm_lines:
        match = FRONTMATTER_LINE.match(line)
        if not match:
            raise Malformed(f"invalid frontmatter line: {line!r}")
        key, value = match.group(1), match.group(2)
        if key in fm:
            raise Malformed(f"duplicate frontmatter key: {key}")
        fm[key] = value
    present = set(fm)
    expected = set(FRONTMATTER_ORDER)
    missing = expected - present
    if missing:
        raise Malformed(f"missing frontmatter keys: {', '.join(sorted(missing))}")
    extra = present - expected
    if extra:
        raise Malformed(f"unexpected frontmatter keys: {', '.join(sorted(extra))}")

    result: dict[str, Any] = {}
    if fm["schema"] != SCHEMA:
        raise Malformed(f"schema must be {SCHEMA}")
    result["schema"] = fm["schema"]
    for field in ("id", "task"):
        if not SAFE_TOKEN.fullmatch(fm[field]):
            raise Malformed(f"{field} not in the safe character class: {fm[field]!r}")
        result[field] = fm[field]
    if stem is not None and fm["id"] != stem:
        raise Malformed(f"filename stem {stem!r} does not match frontmatter id {fm['id']!r}")
    if fm["reason"] not in REASONS:
        raise Malformed(f"reason not recognized: {fm['reason']!r}")
    if fm["priority"] not in PRIORITIES:
        raise Malformed(f"priority not recognized: {fm['priority']!r}")
    if fm["status"] not in STATUSES:
        raise Malformed(f"status not recognized: {fm['status']!r}")
    for field in ("created_utc", "updated_utc"):
        if not TIMESTAMP.fullmatch(fm[field]):
            raise Malformed(f"{field} must be strict YYYY-MM-DDTHH:MM:SSZ: {fm[field]!r}")
        result[field] = fm[field]
    if fm["generation"] != "none" and not GENERATION.fullmatch(fm["generation"]):
        raise Malformed(f"generation must be a non-negative integer or none: {fm['generation']!r}")
    if fm["source"] not in SOURCES:
        raise Malformed(f"source not recognized: {fm['source']!r}")
    if fm["superseded_by"] != "none" and not SAFE_TOKEN.fullmatch(fm["superseded_by"]):
        raise Malformed(f"superseded_by must be none or an item id: {fm['superseded_by']!r}")
    for field in ("reason", "priority", "status", "generation", "source", "superseded_by"):
        result[field] = fm[field]
    # resume_when is a single-line free-text condition; the parser only sees one line.
    result["resume_when"] = fm["resume_when"]
    result["tags"] = parse_tags(fm["tags"])
    return result


def parse_title(body_lines: list[str]) -> tuple[str, list[str]]:
    index = 0
    while index < len(body_lines) and body_lines[index].strip() == "":
        index += 1
    if index >= len(body_lines) or not body_lines[index].startswith("# "):
        raise Malformed("missing '# <summary>' title line")
    summary = body_lines[index][2:].strip()
    if summary == "":
        raise Malformed("summary title is empty")
    return summary, body_lines[index + 1 :]


def parse_sections(rest: list[str]) -> tuple[str, list[str], str]:
    buckets: dict[str, list[str]] = {name: [] for name in SECTIONS}
    current: str | None = None
    for line in rest:
        header = re.match(r"^## (.+)$", line)
        if header:
            name = header.group(1).strip()
            if name not in buckets:
                raise Malformed(f"unknown body section: {name!r}")
            current = name
            continue
        if current is None:
            if line.strip() == "":
                continue
            raise Malformed("body content before the first section header")
        buckets[current].append(line)
    snapshot = strip_outer_blanks(buckets["Snapshot"])
    context = strip_outer_blanks(buckets["Context"])
    handling = [line for line in buckets["Handling log"] if line.strip() != ""]
    return snapshot, handling, context


def parse_header(raw: bytes, stem: str | None) -> dict[str, Any]:
    fm_lines, body_lines = split_frontmatter(raw)
    fm = parse_frontmatter(fm_lines, stem)
    summary, _ = parse_title(body_lines)
    return {**fm, "summary": summary}


def parse_full(raw: bytes, stem: str | None) -> dict[str, Any]:
    fm_lines, body_lines = split_frontmatter(raw)
    fm = parse_frontmatter(fm_lines, stem)
    summary, rest = parse_title(body_lines)
    snapshot, handling, context = parse_sections(rest)
    return {
        **fm,
        "summary": summary,
        "snapshot": snapshot,
        "handling_log": handling,
        "context": context,
    }


# --------------------------------------------------------------------- serialize


def serialize_item(item: dict[str, Any]) -> bytes:
    lines = ["---"]
    for key in FRONTMATTER_ORDER:
        if key == "tags":
            lines.append(f"tags: [{', '.join(item['tags'])}]")
        else:
            lines.append(f"{key}: {item[key]}")
    lines.append("---")
    lines.append(f"# {item['summary']}")
    lines.append("")
    lines.append("## Snapshot")
    lines.append("")
    lines.append(item["snapshot"])
    lines.append("")
    lines.append("## Handling log")
    lines.append("")
    lines.extend(item["handling_log"])
    lines.append("")
    lines.append("## Context")
    lines.append("")
    lines.append(item["context"])
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def log_line(now: dt.datetime, old: str, new: str, note: str) -> str:
    return f"- {stamp_seconds(now)} {old}->{new}: {sanitize_line(note)}"


# --------------------------------------------------------------- safe filesystem


def resolve_home(value: str | None) -> Path:
    raw = value or os.environ.get("ROZORO_HOME", "~/.rozoro")
    return Path(os.path.abspath(os.path.expanduser(raw)))


def open_write_items(home: Path) -> tuple[SafeDirectory, SafeDirectory, SafeDirectory]:
    """Open (attention, items) for mutation, creating the private tree on first write."""
    root = SafeDirectory.open_path(home, create=True, require_owner=True)
    try:
        watchtowers = root.open_or_create_private_child("watchtowers")
    finally:
        root.close()
    try:
        attention = watchtowers.open_or_create_private_child("attention")
    finally:
        watchtowers.close()
    items = attention.open_or_create_private_child("items")
    return attention, items


def close_all(*directories: SafeDirectory | None) -> None:
    for directory in directories:
        if directory is not None:
            directory.close()


def acquire_lock(attention: SafeDirectory) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open("attention.lock", flags, 0o600, dir_fd=attention.fd)
    for _ in range(LOCK_ATTEMPTS):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError:
            time.sleep(LOCK_INTERVAL)
    os.close(fd)
    raise SystemExit("attention ledger is locked by another writer; retry shortly")


def atomic_write(directory: SafeDirectory, name: str, data: bytes) -> None:
    tmp = f".tmp-{secrets.token_hex(6)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600, dir_fd=directory.fd)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, name, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
    os.fsync(directory.fd)


def load_items(home: Path, parser: Callable[[bytes, str | None], dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Read every item under items/ using the given parser; never follow symlinks."""
    records: list[dict[str, Any]] = []
    malformed: list[dict[str, str]] = []
    try:
        root = SafeDirectory.open_path(home, create=False, require_owner=True)
    except UnsafePath:
        # A missing home means an untouched ledger; a symlinked home is unsafe.
        if not os.path.islink(home) and not home.exists():
            return records, malformed
        raise
    chain = [root]
    try:
        current = root
        for child in ("watchtowers", "attention", "items"):
            try:
                current = current.open_child(child, require_owner=True)
            except FileNotFoundError:
                return records, malformed
            chain.append(current)
        items = current
        for name in sorted(items.list_names()):
            state, raw = items.read_regular(name)
            if state != "regular" or raw is None:
                malformed.append({"filename": name, "reason": f"unsafe or unreadable ({state})"})
                continue
            if not name.endswith(".md"):
                malformed.append({"filename": name, "reason": "not a .md item file"})
                continue
            stem = name[:-3]
            try:
                records.append({**parser(raw, stem), "filename": name})
            except Malformed as exc:
                malformed.append({"filename": name, "reason": str(exc)})
    finally:
        close_all(*reversed(chain))
    return records, malformed


# --------------------------------------------------------------------- rendering


def display_value(record: dict[str, Any], field: str) -> str:
    value = record.get(field, "")
    if field == "tags":
        return ",".join(value)
    return str(value)


def render_md_table(records: list[dict[str, Any]], fields: list[str]) -> list[str]:
    if not records:
        return ["_no items_"]
    header = "| " + " | ".join(fields) + " |"
    divider = "| " + " | ".join("---" for _ in fields) + " |"
    rows = [header, divider]
    for record in records:
        cells = [display_value(record, field).replace("|", "\\|") for field in fields]
        rows.append("| " + " | ".join(cells) + " |")
    return rows


def render_tsv(records: list[dict[str, Any]], fields: list[str]) -> list[str]:
    rows = ["\t".join(fields)]
    for record in records:
        rows.append("\t".join(display_value(record, field).replace("\t", " ") for field in fields))
    return rows


def project(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: record.get(field) for field in fields}


# ----------------------------------------------------------------------- cursors


def encode_cursor(record: dict[str, Any]) -> str:
    token = f"{record['updated_utc']}/{record['id']}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def decode_cursor(token: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise SystemExit(f"invalid --cursor token: {token!r}") from exc
    updated, sep, item_id = raw.partition("/")
    if not sep:
        raise SystemExit(f"invalid --cursor token: {token!r}")
    return updated, item_id


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: (record["updated_utc"], record["id"]), reverse=True)


# --------------------------------------------------------------------- subcommands


def read_snapshot(args: argparse.Namespace) -> str:
    if args.snapshot_file is not None and args.snapshot is not None:
        raise SystemExit("use only one of --snapshot-file or --snapshot")
    if args.snapshot == "-":
        data = sys.stdin.buffer.read()
    elif args.snapshot is not None:
        raise SystemExit("--snapshot only accepts '-' (stdin); use --snapshot-file for a path")
    elif args.snapshot_file is not None:
        data = Path(args.snapshot_file).read_bytes()
    else:
        return ""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit("snapshot input is not valid UTF-8") from exc
    return strip_outer_blanks(text.split("\n"))


def collect_tags(raw: list[str] | None) -> list[str]:
    tags: list[str] = []
    for value in raw or []:
        for token in value.split(","):
            item = token.strip()
            if item == "":
                continue
            if not SAFE_TOKEN.fullmatch(item):
                raise SystemExit(f"tag not in the safe character class: {item!r}")
            if item not in tags:
                tags.append(item)
    return tags


def cmd_add(args: argparse.Namespace) -> int:
    now = utc_now(args.now)
    task = args.task
    if not SAFE_TOKEN.fullmatch(task):
        raise SystemExit(f"--task not in the safe character class: {task!r}")
    if args.reason not in REASONS:
        raise SystemExit(f"--reason not recognized: {args.reason!r}")
    if args.source not in SOURCES:
        raise SystemExit(f"--source not recognized: {args.source!r}")
    summary = sanitize_line(args.summary)
    if summary == "":
        raise SystemExit("--summary must not be empty")
    generation = "none" if args.generation is None else str(args.generation)
    if args.generation is not None and args.generation < 0:
        raise SystemExit("--generation must be non-negative")
    snapshot = read_snapshot(args)
    tags = collect_tags(args.tag)
    nonce = args.nonce or secrets.token_hex(2)
    if not re.fullmatch(r"[0-9a-f]{1,16}", nonce):
        raise SystemExit(f"--nonce must be lowercase hex: {nonce!r}")
    stamp = stamp_seconds(now)
    item_id = f"{stamp_compact(now)}-{task}-{nonce}"
    if not SAFE_TOKEN.fullmatch(item_id):
        raise SystemExit(f"derived item id is not a safe token: {item_id!r}")

    item = {
        "schema": SCHEMA,
        "id": item_id,
        "task": task,
        "reason": args.reason,
        "priority": args.priority,
        "status": "open",
        "created_utc": stamp,
        "updated_utc": stamp,
        "generation": generation,
        "source": args.source,
        "superseded_by": "none",
        "resume_when": "none",
        "tags": tags,
        "summary": summary,
        "snapshot": snapshot,
        "handling_log": [log_line(now, "new", "open", f"created via {args.source}")],
        "context": "",
    }

    attention = items = None
    lock_fd = None
    try:
        attention, items = open_write_items(args.home)
        lock_fd = acquire_lock(attention)
        superseded: list[str] = []
        if not args.no_supersede:
            superseded = supersede_matches(items, task, args.reason, item_id, now)
        try:
            items.write_exclusive(f"{item_id}.md", serialize_item(item))
        except FileExistsError as exc:
            raise SystemExit(f"item id already exists: {item_id}") from exc
    except UnsafePath as exc:
        raise SystemExit(f"cannot open attention ledger for writing: {exc}") from exc
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        close_all(items, attention)

    if args.json:
        print(json.dumps({"id": item_id, "superseded": superseded}, sort_keys=True))
    else:
        print(item_id)
    return 0


def supersede_matches(items: SafeDirectory, task: str, reason: str, new_id: str, now: dt.datetime) -> list[str]:
    superseded: list[str] = []
    for name in sorted(items.list_names()):
        if not name.endswith(".md"):
            continue
        state, raw = items.read_regular(name)
        if state != "regular" or raw is None:
            continue
        try:
            existing = parse_full(raw, name[:-3])
        except Malformed:
            continue  # never touch a malformed file silently
        if existing["task"] != task or existing["reason"] != reason:
            continue
        if existing["status"] not in {"open", "deferred"}:
            continue
        existing["status"] = "superseded"
        existing["superseded_by"] = new_id
        existing["updated_utc"] = stamp_seconds(now)
        existing["handling_log"].append(log_line(now, existing["status"], "superseded", f"superseded by {new_id}"))
        atomic_write(items, name, serialize_item(existing))
        superseded.append(existing["id"])
    return superseded


def cmd_update(args: argparse.Namespace) -> int:
    now = utc_now(args.now)
    note = sanitize_line(args.note)
    if note == "":
        raise SystemExit("--note must not be empty")
    if args.status is not None and args.status not in {"open", "handled", "deferred"}:
        raise SystemExit(f"--status not settable to: {args.status!r}")

    attention = items = None
    lock_fd = None
    try:
        attention, items = open_write_items(args.home)
        lock_fd = acquire_lock(attention)
        name = f"{args.id}.md"
        state, raw = items.read_regular(name)
        if state == "missing":
            raise SystemExit(f"no such item: {args.id}")
        if state != "regular" or raw is None:
            raise SystemExit(f"item is unsafe or unreadable ({state}): {args.id}")
        try:
            item = parse_full(raw, args.id)
        except Malformed as exc:
            raise SystemExit(f"refusing to update a malformed item ({exc}): {args.id}") from exc
        if item["status"] == "superseded":
            raise SystemExit(f"item is superseded by {item['superseded_by']}; update the successor instead")

        old_status = item["status"]
        new_status = args.status or old_status
        resume = item["resume_when"]
        if args.resume_when is not None:
            resume = sanitize_line(args.resume_when) or "none"
        if new_status == "deferred":
            if resume in NONE_TOKENS:
                raise SystemExit("--status deferred requires --resume-when")
        elif args.resume_when is None:
            resume = "none"

        if args.priority is not None:
            item["priority"] = args.priority
        if args.tag:
            merged = list(item["tags"])
            for tag in collect_tags(args.tag):
                if tag not in merged:
                    merged.append(tag)
            item["tags"] = merged
        item["status"] = new_status
        item["resume_when"] = resume
        item["updated_utc"] = stamp_seconds(now)
        item["handling_log"].append(log_line(now, old_status, new_status, note))
        atomic_write(items, name, serialize_item(item))
    except UnsafePath as exc:
        raise SystemExit(f"cannot open attention ledger for writing: {exc}") from exc
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        close_all(items, attention)

    if args.json:
        print(json.dumps({"id": args.id, "status": new_status}, sort_keys=True))
    else:
        print(f"{args.id} {old_status}->{new_status}")
    return 0


def normalize_multi(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        for token in value.split(","):
            item = token.strip()
            if item != "":
                out.append(item)
    return out


def apply_filters(records: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    statuses = normalize_multi(args.status) or ["open", "deferred"]
    for status in statuses:
        if status not in STATUSES:
            raise SystemExit(f"--status not recognized: {status!r}")
    reasons = normalize_multi(args.reason)
    for reason in reasons:
        if reason not in REASONS:
            raise SystemExit(f"--reason not recognized: {reason!r}")
    tags = normalize_multi(args.tag)
    since = stamp_seconds(utc_now(args.since)) if args.since else None
    until = stamp_seconds(utc_now(args.until)) if args.until else None

    selected = []
    for record in records:
        if record["status"] not in statuses:
            continue
        if args.task is not None and record["task"] != args.task:
            continue
        if reasons and record["reason"] not in reasons:
            continue
        if args.priority is not None and record["priority"] != args.priority:
            continue
        if tags and not any(tag in record["tags"] for tag in tags):
            continue
        if since is not None and record["updated_utc"] < since:
            continue
        if until is not None and record["updated_utc"] > until:
            continue
        selected.append(record)
    return selected


def paginate(records: list[dict[str, Any]], cursor: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    ordered = sort_records(records)
    if cursor is not None:
        updated, item_id = decode_cursor(cursor)
        ordered = [r for r in ordered if (r["updated_utc"], r["id"]) < (updated, item_id)]
    page = ordered[:limit]
    next_cursor = encode_cursor(page[-1]) if len(ordered) > limit else None
    return page, next_cursor


def cmd_list(args: argparse.Namespace) -> int:
    fields = normalize_multi([args.fields]) if args.fields else list(DEFAULT_FIELDS)
    for field in fields:
        if field not in LIST_FIELDS:
            raise SystemExit(f"unknown --fields entry: {field!r}")
    records, malformed = load_items(args.home, parse_header)
    selected = apply_filters(records, args)
    page, next_cursor = paginate(selected, args.cursor, args.limit)

    if args.format == "json":
        payload = {
            "items": [project(record, fields) for record in page],
            "next_cursor": next_cursor,
            "malformed": malformed,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.format == "tsv":
        lines = render_tsv(page, fields)
    else:
        lines = render_md_table(page, fields)
    if next_cursor is not None:
        lines.append(f"next: {next_cursor}")
    if malformed:
        names = ", ".join(entry["filename"] for entry in malformed)
        lines.append(f"malformed: {len(malformed)} ({names})")
    print("\n".join(lines))
    return 0


def read_one(home: Path, item_id: str) -> dict[str, Any]:
    if not SAFE_TOKEN.fullmatch(item_id):
        raise SystemExit(f"item id not in the safe character class: {item_id!r}")
    root = SafeDirectory.open_path(home, create=False, require_owner=True)
    chain = [root]
    try:
        current = root
        for child in ("watchtowers", "attention", "items"):
            try:
                current = current.open_child(child, require_owner=True)
            except FileNotFoundError as exc:
                raise SystemExit(f"no such item: {item_id}") from exc
            chain.append(current)
        state, raw = current.read_regular(f"{item_id}.md")
        if state == "missing":
            raise SystemExit(f"no such item: {item_id}")
        if state != "regular" or raw is None:
            raise SystemExit(f"item is unsafe or unreadable ({state}): {item_id}")
        try:
            return {**parse_full(raw, item_id), "raw": raw.decode("utf-8")}
        except Malformed as exc:
            raise SystemExit(f"item is malformed ({exc}): {item_id}") from exc
    finally:
        close_all(*reversed(chain))


def cmd_show(args: argparse.Namespace) -> int:
    try:
        item = read_one(args.home, args.id)
    except UnsafePath as exc:
        raise SystemExit(f"cannot read attention ledger: {exc}") from exc
    if args.json:
        payload = {
            "frontmatter": {key: item[key] for key in FRONTMATTER_ORDER},
            "summary": item["summary"],
            "snapshot": item["snapshot"],
            "handling_log": item["handling_log"],
            "context": item["context"],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        sys.stdout.write(item["raw"])
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        records, malformed = load_items(args.home, parse_full)
    except UnsafePath as exc:
        raise SystemExit(f"cannot scan attention ledger: {exc}") from exc
    ok = [{"filename": record["filename"], "id": record["id"]} for record in records]
    if args.json:
        print(json.dumps({"ok": ok, "malformed": malformed}, indent=2, sort_keys=True))
    else:
        lines = [f"ok: {len(ok)}", f"malformed: {len(malformed)}"]
        for entry in malformed:
            lines.append(f"  MALFORMED {entry['filename']}: {entry['reason']}")
        print("\n".join(lines))
    return 1 if malformed else 0


def cmd_export(args: argparse.Namespace) -> int:
    try:
        records, malformed = load_items(args.home, parse_full)
    except UnsafePath as exc:
        raise SystemExit(f"cannot scan attention ledger: {exc}") from exc
    items = []
    for record in sort_records(records):
        items.append(
            {
                "frontmatter": {key: record[key] for key in FRONTMATTER_ORDER},
                "summary": record["summary"],
                "snapshot": record["snapshot"],
                "handling_log": record["handling_log"],
                "context": record["context"],
                "filename": record["filename"],
            }
        )
    payload = {"schema": SCHEMA, "artifact_type": "watchtower-attention-ledger-export", "items": items, "malformed": malformed}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def final_note(record: dict[str, Any]) -> str:
    if not record["handling_log"]:
        return ""
    last = record["handling_log"][-1]
    _, sep, note = last.partition(": ")
    return note if sep else last


def cmd_prime(args: argparse.Namespace) -> int:
    # prime reads bodies so the "recently handled" section can show each item's final note.
    records, malformed = load_items(args.home, parse_full)
    by_status: dict[str, int] = {status: 0 for status in STATUSES}
    by_reason: dict[str, int] = {}
    for record in records:
        by_status[record["status"]] = by_status.get(record["status"], 0) + 1
        by_reason[record["reason"]] = by_reason.get(record["reason"], 0) + 1

    open_records = [r for r in records if r["status"] == "open"]
    urgent = sort_records([r for r in open_records if r["priority"] == "urgent"])
    normal = [r for r in open_records if r["priority"] != "urgent"]
    normal_page, normal_next = paginate(normal, None, args.limit)
    deferred = sort_records([r for r in records if r["status"] == "deferred"])
    handled = sort_records([r for r in records if r["status"] == "handled"])[:5]

    if args.format == "json":
        payload = {
            "disclaimer": DISCLAIMER,
            "counts": {"by_status": by_status, "by_reason": by_reason, "malformed": len(malformed)},
            "urgent_open": [project(r, DEFAULT_FIELDS) for r in urgent],
            "normal_open": [project(r, DEFAULT_FIELDS) for r in normal_page],
            "normal_open_next_cursor": normal_next,
            "deferred": [{"id": r["id"], "task": r["task"], "resume_when": r["resume_when"]} for r in deferred],
            "recently_handled": [{"id": r["id"], "task": r["task"], "final_note": final_note(r)} for r in handled],
            "malformed": malformed,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    reason_counts = ", ".join(f"{reason} {count}" for reason, count in sorted(by_reason.items())) or "none"
    status_counts = ", ".join(f"{status} {by_status[status]}" for status in ("open", "deferred", "handled", "superseded"))
    lines = [
        "# Watchtower attention ledger — prime",
        "",
        f"_{DISCLAIMER}_",
        "",
        "## Counts",
        "",
        f"- by status: {status_counts}",
        f"- by reason: {reason_counts}",
        f"- malformed: {len(malformed)}",
        "",
        "## Urgent open items",
        "",
        *render_md_table(urgent, DEFAULT_FIELDS),
        "",
        f"## Normal open items (limit {args.limit})",
        "",
        *render_md_table(normal_page, DEFAULT_FIELDS),
    ]
    if normal_next is not None:
        lines.append(f"next: {normal_next}")
    lines += ["", "## Deferred (resume conditions)", ""]
    if deferred:
        lines += [f"- `{r['id']}` {r['task']}: resume_when={r['resume_when']}" for r in deferred]
    else:
        lines.append("_none_")
    lines += ["", "## Recently handled (last 5)", ""]
    if handled:
        lines += [f"- `{r['id']}` {r['task']}: {final_note(r)}" for r in handled]
    else:
        lines.append("_none_")
    if malformed:
        names = ", ".join(entry["filename"] for entry in malformed)
        lines += ["", f"malformed: {len(malformed)} ({names})"]
    print("\n".join(lines))
    return 0


# --------------------------------------------------------------------------- cli


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", help="ledger home (default $ROZORO_HOME, else ~/.rozoro)")
    parser.add_argument("--now", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="record a new attention item (status open)")
    add_common(p_add)
    p_add.add_argument("--task", required=True)
    p_add.add_argument("--reason", required=True)
    p_add.add_argument("--summary", required=True)
    p_add.add_argument("--priority", choices=sorted(PRIORITIES), default="normal")
    p_add.add_argument("--generation", type=int)
    p_add.add_argument("--source", choices=sorted(SOURCES), default="reconcile")
    p_add.add_argument("--snapshot-file")
    p_add.add_argument("--snapshot", help="read snapshot body from stdin with '-'")
    p_add.add_argument("--tag", action="append")
    p_add.add_argument("--no-supersede", action="store_true")
    p_add.add_argument("--nonce", help=argparse.SUPPRESS)
    p_add.add_argument("--json", action="store_true")
    p_add.set_defaults(func=cmd_add)

    p_update = sub.add_parser("update", help="append a handling note and adjust status")
    add_common(p_update)
    p_update.add_argument("id")
    p_update.add_argument("--note", required=True)
    p_update.add_argument("--status", choices=["open", "handled", "deferred"])
    p_update.add_argument("--resume-when")
    p_update.add_argument("--priority", choices=sorted(PRIORITIES))
    p_update.add_argument("--tag", action="append")
    p_update.add_argument("--json", action="store_true")
    p_update.set_defaults(func=cmd_update)

    p_list = sub.add_parser("list", help="list items (frontmatter + title only)")
    add_common(p_list)
    p_list.add_argument("--status", action="append")
    p_list.add_argument("--task")
    p_list.add_argument("--reason", action="append")
    p_list.add_argument("--priority", choices=sorted(PRIORITIES))
    p_list.add_argument("--tag", action="append")
    p_list.add_argument("--since")
    p_list.add_argument("--until")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--cursor")
    p_list.add_argument("--fields")
    p_list.add_argument("--format", choices=["md", "json", "tsv"], default="md")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print a full item")
    add_common(p_show)
    p_show.add_argument("id")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_prime = sub.add_parser("prime", help="re-orientation digest for a fresh session")
    add_common(p_prime)
    p_prime.add_argument("--limit", type=int, default=20)
    p_prime.add_argument("--format", choices=["md", "json"], default="md")
    p_prime.set_defaults(func=cmd_prime)

    p_doctor = sub.add_parser("doctor", help="validate every item file")
    add_common(p_doctor)
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    p_export = sub.add_parser("export", help="dump all items as one JSON document")
    add_common(p_export)
    p_export.add_argument("--format", choices=["json"], default="json")
    p_export.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.home = resolve_home(getattr(args, "home", None))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
