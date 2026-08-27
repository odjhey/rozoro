#!/usr/bin/env python3
"""Reconstruct the full communication lineage of a Rozoro agent.

Every message an agent ever exchanged is already durable, but split across four
stores. This stitches them back into one ordered conversation:

  inbound   what the watchtower told the agent   transcript JSONL (user messages)
  outbound  what the agent reported back         tasks/<key>/handoff.md blocks
  decision  what the watchtower did about it     watchtowers/attention/items/*.md
  timing    turn boundaries and context loss     monitor.db events, transcript

Usage:
  rzr-lineage.py                     index every agent, one row each
  rzr-lineage.py <task>              full lineage for one agent (key or prefix)
  rzr-lineage.py <task> --full       do not truncate message bodies
  rzr-lineage.py [<task>] --json     machine-readable
  rzr-lineage.py --drift             index, but only agents whose counts disagree

Handoff blocks carry no timestamp of their own, so each is placed at the turn
boundary it most likely closed and printed with a leading '~'. When the inbound,
block, and turn counts disagree the header says so: that drift means a prompt
produced no report, or a report was appended outside a turn.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.rozoro_monitor.handoff import parse as parse_handoff

HOME_RAW = os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME") or str(Path.home() / ".rozoro")
HOME = Path(HOME_RAW)
TASKS = HOME / "tasks"
ATTENTION = HOME / "watchtowers" / "attention" / "items"
DB = HOME / "monitor.db"

KIND_MARK = {"dispatch": "▶", "in": "←", "out": "→",
             "attn": "⚑", "turn": "·", "compact": "✂"}


def die(msg):
    print(f"rzr-lineage: {msg}", file=sys.stderr)
    sys.exit(1)


def open_db():
    if not DB.exists():
        return None
    try:
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None


def resolve(token):
    """Resolve an exact key, a unique prefix, or a unique substring."""
    keys = sorted(p.name for p in TASKS.iterdir() if p.is_dir()) if TASKS.is_dir() else []
    if token in keys:
        return token
    for match in ([k for k in keys if k.startswith(token)],
                  [k for k in keys if token in k]):
        if len(match) == 1:
            return match[0]
        if len(match) > 1:
            die("'%s' matches %d tasks:\n  %s" % (token, len(match), "\n  ".join(match[:20])))
    die(f"no task matching '{token}'")


def read_session(task_dir):
    try:
        return json.loads((task_dir / "session.json").read_text())
    except (OSError, ValueError):
        return {}


def text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def read_transcript(session):
    """Inbound prompts and compaction points from the harness transcript."""
    path = session.get("session_path")
    if not path or not os.path.exists(path):
        return [], [], ("missing" if path else "unrecorded")
    inbound, compactions = [], []
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            kind = rec.get("type")
            if kind == "compaction":
                compactions.append({"kind": "compact", "ts": rec.get("timestamp"),
                                    "text": (rec.get("summary") or "").strip()})
            elif kind == "message" and (rec.get("message") or {}).get("role") == "user":
                inbound.append({"kind": "in", "ts": rec.get("timestamp"),
                                "text": text_of(rec["message"].get("content")).strip()})
    return inbound, compactions, "present"


def read_handoff(task_dir):
    ack_v2 = task_dir / ".acked-blocks-v2"
    ack_legacy = task_dir / ".acked-blocks"
    try:
        report = parse_handoff(task_dir / "handoff.md",
                               ack_v2 if ack_v2.exists() else None,
                               ack_legacy if ack_legacy.exists() else None)
    except (OSError, ValueError):
        return [], 0
    acked = report.get("acked_through") or 0
    acked = acked if isinstance(acked, int) else 0
    blocks = []
    for block in report.get("block_details", []):
        fields = block.get("fields", {})
        blocks.append({
            "kind": "out", "ts": None, "index": block.get("index"),
            "heading": block.get("heading", ""),
            "verdict": fields.get("verdict"), "reason": fields.get("reason"),
            "valid": block.get("valid", False), "errors": block.get("errors", []),
            "acked": bool(block.get("index") and block["index"] <= acked),
            "text": fields.get("did") or "",
            "pending": fields.get("pending") or "",
            "inputs_needed": fields.get("inputs-needed") or "",
            "artifacts": fields.get("artifacts") or "",
        })
    return blocks, acked


FRONT = re.compile(r"^(\w+): (.*)$", re.M)
LOGLINE = re.compile(r"^- (\S+Z) (\S+): (.*)$", re.M)


def read_attention():
    """Watchtower decisions, grouped by task key."""
    by_task = {}
    if not ATTENTION.is_dir():
        return by_task
    for path in sorted(ATTENTION.glob("*.md")):
        try:
            raw = path.read_text(errors="replace")
        except OSError:
            continue
        body = raw
        front = dict(FRONT.findall(raw.partition("\n---\n")[0]))
        task = front.get("task")
        if not task:
            continue
        title = ""
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        snapshot = ""
        chunk = body.split("## Snapshot", 1)
        if len(chunk) > 1:
            snapshot = chunk[1].split("##", 1)[0].strip()
        for ts, transition, note in LOGLINE.findall(body):
            by_task.setdefault(task, []).append({
                "kind": "attn", "ts": ts, "title": title, "snapshot": snapshot,
                "transition": transition, "text": note.strip(),
                "reason": front.get("reason", ""), "priority": front.get("priority", ""),
                "status": front.get("status", ""), "item": path.name,
            })
    return by_task


def read_turns(db, task_key):
    if db is None:
        return []
    rows = db.execute(
        "SELECT event_type, received_at, json_extract(payload_json,'$.turn_id') "
        "FROM events WHERE task_id=? AND event_type IN ('turn.start','turn.stop') "
        "ORDER BY durable_seq", (task_key,)).fetchall()
    return [{"kind": "turn", "ts": ts, "event": kind, "turn_id": tid}
            for kind, ts, tid in rows]


def norm_ts(value):
    """Everything to a sortable ISO-8601 UTC string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        import datetime
        seconds = value / 1000 if value > 1e11 else value
        return (datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
    return str(value)


def build(task_key):
    task_dir = TASKS / task_key
    if not task_dir.is_dir():
        die(f"no task folder for '{task_key}'")
    session = read_session(task_dir)
    inbound, compactions, transcript_state = read_transcript(session)
    blocks, acked = read_handoff(task_dir)
    turns = read_turns(open_db(), task_key)
    attention = read_attention().get(task_key, [])

    for entry in inbound + compactions + turns + attention:
        entry["ts"] = norm_ts(entry["ts"])

    # A handoff block closes a turn but records no time of its own; anchor block
    # k to the k-th turn.stop. Extra blocks fall on the last known boundary.
    stops = [t["ts"] for t in turns if t["event"] == "turn.stop"]
    for offset, block in enumerate(blocks):
        if offset < len(stops):
            block["ts"], block["ts_inferred"] = stops[offset], True
        elif stops:
            block["ts"], block["ts_inferred"] = stops[-1], True
        else:
            block["ts"], block["ts_inferred"] = None, True

    events = inbound + compactions + turns + attention + blocks
    # Untimed entries sink to the end; inbound precedes the turn it opened,
    # and a block sorts after the turn.stop sharing its timestamp.
    order = {"in": 0, "turn": 1, "out": 2, "compact": 3, "attn": 4}
    events.sort(key=lambda e: (e["ts"] is None, e["ts"] or "", order.get(e["kind"], 9)))

    if inbound:
        inbound[0]["kind"] = "dispatch"

    profile = session.get("profile", {})
    counts = {"inbound": len(inbound), "blocks": len(blocks), "turns": len(stops),
              "attention": len({a["item"] for a in attention}), "compactions": len(compactions)}
    return {
        "task": task_key,
        "display": (json.loads((task_dir / "identity.json").read_text()).get("display_name")
                    if (task_dir / "identity.json").exists() else task_key),
        "harness": session.get("harness", "?"),
        "model": profile.get("model", "?"),
        "effort": profile.get("effort", "?"),
        "cwd": session.get("cwd", ""),
        "resume": session.get("resume", ""),
        "transcript": transcript_state,
        "transcript_path": session.get("session_path", ""),
        "acked_through": acked,
        "counts": counts,
        "drift": not (counts["inbound"] == counts["blocks"] == counts["turns"]),
        "invalid_blocks": sum(1 for b in blocks if not b["valid"]),
        "events": events,
    }


def clip(text, limit):
    text = " ".join((text or "").split())
    if limit and len(text) > limit:
        return text[:limit - 1] + "…"
    return text


def render(lin, limit):
    out = []
    add = out.append
    add(f"{lin['display']}  ({lin['task']})")
    add(f"  {lin['harness']}/{lin['model']} effort={lin['effort']}  cwd={lin['cwd'] or '?'}")
    counts = lin["counts"]
    add(f"  inbound={counts['inbound']} blocks={counts['blocks']} turns={counts['turns']} "
        f"attention={counts['attention']} acked-through={lin['acked_through']}")
    if lin["transcript"] != "present":
        add(f"  ! transcript {lin['transcript']} — inbound messages cannot be recovered")
    if lin["drift"]:
        add("  ! drift: inbound/blocks/turns disagree — a prompt produced no report, "
            "or a report landed outside a turn")
    if lin["invalid_blocks"]:
        add(f"  ! {lin['invalid_blocks']} handoff block(s) failed protocol validation")
    add("")

    for event in lin["events"]:
        kind = event["kind"]
        stamp = (event["ts"] or "")[:19].replace("T", " ") or " " * 19
        mark = KIND_MARK.get(kind, " ")
        if kind in ("in", "dispatch"):
            label = "DISPATCH" if kind == "dispatch" else "prompt"
            add(f"{stamp} {mark} {label}")
            add(f"{'':19}   {clip(event['text'], limit)}")
        elif kind == "out":
            flags = []
            if not event["valid"]:
                flags.append("INVALID: " + "; ".join(event["errors"]))
            flags.append("acked" if event["acked"] else "unacked")
            tilde = "~" if event.get("ts_inferred") and event["ts"] else " "
            add(f"{stamp}{tilde}{mark} report #{event['index']} "
                f"[{event['verdict'] or 'no-verdict'}] ({', '.join(flags)})")
            add(f"{'':19}   {clip(event['heading'], limit)}")
            if event["text"]:
                add(f"{'':19}   did: {clip(event['text'], limit)}")
            if event["inputs_needed"] and event["inputs_needed"] != "none":
                add(f"{'':19}   inputs-needed: {clip(event['inputs_needed'], limit)}")
        elif kind == "attn":
            add(f"{stamp} {mark} watchtower {event['transition']} "
                f"[{event['reason']}/{event['priority']}]")
            add(f"{'':19}   {clip(event['title'], limit)}")
            add(f"{'':19}   {clip(event['text'], limit)}")
        elif kind == "compact":
            add(f"{stamp} {mark} context compacted — prior turns summarized away")
        elif kind == "turn":
            add(f"{stamp} {mark} {event['event']}")
        add("")
    if lin["resume"]:
        add(f"resume: {lin['resume']}")
    if lin["transcript_path"]:
        add(f"transcript: {lin['transcript_path']}")
    return "\n".join(out)


def index(drift_only):
    db = open_db()
    last = {}
    if db is not None:
        last = dict(db.execute("SELECT task_id, MAX(received_at) FROM events "
                               "WHERE task_id IS NOT NULL GROUP BY 1"))
    attention = read_attention()
    rows = []
    for path in sorted(TASKS.iterdir()) if TASKS.is_dir() else []:
        if not path.is_dir():
            continue
        key = path.name
        session = read_session(path)
        inbound, compactions, state = read_transcript(session)
        blocks, acked = read_handoff(path)
        turns = read_turns(db, key)
        stops = sum(1 for t in turns if t["event"] == "turn.stop")
        row = {
            "task": key, "harness": session.get("harness", "?"),
            "model": session.get("profile", {}).get("model", "?"),
            "inbound": len(inbound), "blocks": len(blocks), "turns": stops,
            "attention": len({a["item"] for a in attention.get(key, [])}),
            "invalid": sum(1 for b in blocks if not b["valid"]),
            "compactions": len(compactions), "transcript": state,
            "acked_through": acked, "last_event": last.get(key, ""),
            "drift": not (len(inbound) == len(blocks) == stops),
        }
        if drift_only and not row["drift"] and row["transcript"] == "present":
            continue
        rows.append(row)
    rows.sort(key=lambda r: r["last_event"], reverse=True)
    return rows


def render_index(rows):
    head = (f"{'task':<52} {'harness/model':<18} {'in':>3} {'out':>4} {'trn':>4} "
            f"{'atn':>4} {'bad':>4} {'cmp':>4}  {'transcript':<10} last")
    out = [head, "-" * len(head)]
    for row in rows:
        flag = "!" if row["drift"] or row["transcript"] != "present" else " "
        out.append(
            f"{row['task'][:52]:<52} {(row['harness'] + '/' + row['model'])[:18]:<18} "
            f"{row['inbound']:>3} {row['blocks']:>4} {row['turns']:>4} {row['attention']:>4} "
            f"{row['invalid']:>4} {row['compactions']:>4}  {row['transcript']:<10} "
            f"{(row['last_event'] or '')[:19].replace('T', ' ')}{flag}")
    out.append("")
    out.append(f"{len(rows)} agent(s).  in=inbound prompts  out=handoff reports  "
               f"trn=turns  atn=attention items  bad=invalid reports  cmp=compactions")
    out.append("'!' marks count drift or an unrecoverable transcript.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("task", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--full", action="store_true", help="do not truncate message bodies")
    ap.add_argument("--drift", action="store_true", help="index only agents with drift")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()
    if args.help:
        print(__doc__.strip())
        return
    if not TASKS.is_dir():
        die(f"no task store at {TASKS}")
    if args.task:
        lineage = build(resolve(args.task))
        print(json.dumps(lineage, indent=2) if args.json
              else render(lineage, 0 if args.full else 160))
    else:
        rows = index(args.drift)
        print(json.dumps(rows, indent=2) if args.json else render_index(rows))


if __name__ == "__main__":
    main()
