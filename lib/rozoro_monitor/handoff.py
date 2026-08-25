"""Canonical, read-only parser for Rozoro append-only handoffs."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

TURN = re.compile(r"^## turn ([1-9][0-9]*)(?:\s+—.*)?$")
H2 = re.compile(r"^## ")
FIELD = re.compile(r"^([A-Za-z][A-Za-z-]*):\s*(.*)$")
KNOWN = {"verdict", "reason", "did", "pending", "inputs-needed", "artifacts"}
REQUIRED = {"verdict", "did", "pending", "inputs-needed", "artifacts"}
VERDICTS = {"done", "waiting", "needs-action", "failed", "blocked"}
NONE = {"", "none", "n/a", "na", "-"}
OPEN = {"needs-action", "failed", "blocked"}


def cursor(path: str | os.PathLike[str] | None) -> int | str | None:
    if not path or not os.path.exists(path):
        return None
    try:
        value = int(Path(path).read_text().strip())
        if value < 0:
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError):
        return "invalid"


def parse(path: str | os.PathLike[str], ack_v2: str | os.PathLike[str] | None = None,
          ack_legacy: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    return parse_text(text, cursor(ack_v2), cursor(ack_legacy))


def parse_text(text: str, ack_v2: int | str | None = None,
               ack_legacy: int | str | None = None) -> dict[str, Any]:
    """Parse already-captured handoff text and cursor values without reopening paths."""
    lines = text.splitlines()
    starts: list[tuple[int, int]] = []
    legacy: list[int] = []
    for index, line in enumerate(lines):
        if H2.match(line):
            legacy.append(index)
        match = TURN.match(line)
        if match:
            starts.append((index, int(match.group(1))))
    blocks = []
    errors = []
    previous = 0
    for number, (start, declared) in enumerate(starts):
        end = starts[number + 1][0] if number + 1 < len(starts) else len(lines)
        fields: dict[str, str] = {}
        duplicates = []
        for line in lines[start + 1:end]:
            match = FIELD.match(line)
            if match and match.group(1).lower() in KNOWN:
                key = match.group(1).lower()
                if key in fields:
                    duplicates.append(key)
                else:
                    fields[key] = match.group(2).strip()
        block_errors = []
        if declared != previous + 1:
            block_errors.append(f"turn sequence expected {previous + 1}, got {declared}")
        previous = declared
        for key in sorted(REQUIRED - set(fields)):
            block_errors.append("missing field: " + key)
        for key in sorted(set(duplicates)):
            block_errors.append("duplicate field: " + key)
        verdict = fields.get("verdict", "").lower()
        if verdict not in VERDICTS:
            block_errors.append("unknown verdict: " + (fields.get("verdict") or "(missing)"))
        if verdict != "done" and not fields.get("reason", "").strip():
            block_errors.append("missing field: reason")
        if verdict == "waiting":
            if fields.get("inputs-needed", "").strip().lower() not in NONE:
                block_errors.append("waiting requires inputs-needed: none")
            if fields.get("pending", "").strip().lower() in NONE:
                block_errors.append("waiting requires useful pending")
            if fields.get("reason", "").strip().lower() in NONE:
                block_errors.append("waiting requires useful reason")
        index = number + 1
        errors.extend(f"block {index}: {error}" for error in block_errors)
        blocks.append({"index": index, "turn": declared, "heading": lines[start][3:].strip(),
                       "fields": fields, "valid": not block_errors, "errors": block_errors,
                       "legacy_index": legacy.index(start) + 1})
    malformed = [lines[index] for index in legacy if not TURN.match(lines[index])]
    if malformed:
        errors.append("noncanonical H2 heading(s): " + ", ".join(malformed))
    v2 = ack_v2
    old = ack_legacy
    source = "none"
    acked: int | str = 0
    if v2 is not None:
        source, acked = "v2", v2
        if v2 == "invalid" or v2 > len(blocks):
            errors.append("invalid canonical acknowledgement cursor")
            acked = 0
    elif old is not None:
        source = "legacy-mapped"
        if old == "invalid" or old > len(legacy):
            errors.append("invalid legacy acknowledgement cursor")
            acked = 0
        else:
            acked = sum(1 for block in blocks if block["legacy_index"] <= old)
    open_items = []
    for block in blocks:
        fields = block["fields"]
        needed = fields.get("inputs-needed", "").strip().lower()
        if block["index"] > acked and (fields.get("verdict", "").lower() in OPEN or needed not in NONE):
            open_items.append({"index": block["index"], "turn": block["turn"],
                               "heading": block["heading"], "verdict": fields.get("verdict", ""),
                               "inputs_needed": fields.get("inputs-needed", "")})
    return {"blocks": len(blocks), "legacy_headings": len(legacy), "acked_through": acked,
            "acked_source": source, "latest": blocks[-1] if blocks else None,
            "block_details": blocks, "open_items": open_items, "unresolved": len(open_items),
            "protocol_errors": errors}


def parse_task_report(task_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """Parse a task report and its independent handoff acknowledgement cursors."""
    task = Path(task_dir)
    return parse(task / "handoff.md", task / ".acked-blocks-v2", task / ".acked-blocks")
