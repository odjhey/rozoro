#!/usr/bin/env python3
"""Generate static HTML fleet reports from the rozorod event store.

Read-only: opens monitor.db with mode=ro and never talks to the daemon, so it
cannot advance delivery or ACK cursors. Reports are runtime data and land under
$ROZORO_HOME/reports/ as dated, self-contained HTML files.

Reports:
  durations  task-durations-<date>.html   wall vs active time, idle share,
                                          reaction-gap/turn histograms, model
                                          profiles, churn
  timeline   fleet-timeline-<date>.html   concurrency step chart, reaction-gap
                                          trend, per-task turn lanes, current
                                          outcome breakdowns

Turn pairing is strict: a turn counts as active time only when its turn_id has
exactly one turn.start and one turn.stop with stop >= start. Unpaired turns
(interrupted or still running) are excluded from sums and surfaced as counts.
"""

import argparse
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates" / "reports"

HIST_EDGES = [1, 5, 15, 30, 60, 120]
HIST_LABELS = ["<1m", "1–5m", "5–15m", "15–30m", "30–60m", "1–2h", ">2h"]
TREND_BUCKET_MIN = 360


def parse_ts(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")


def open_store(home):
    db = home / "monitor.db"
    if not db.is_file():
        raise SystemExit(f"rzr-report: no event store at {db} (is the monitor initialized?)")
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def load_turn_events(connection):
    return connection.execute(
        """SELECT task_id, event_type, received_at,
                  json_extract(payload_json,'$.turn_id') AS turn_id
           FROM events
           WHERE task_id IS NOT NULL AND task_id != ''
             AND event_type IN ('turn.start','turn.stop')
           ORDER BY durable_seq"""
    ).fetchall()


def load_task_spans(connection):
    return connection.execute(
        """SELECT task_id, MIN(received_at) AS first_seen, MAX(received_at) AS last_seen
           FROM events WHERE task_id IS NOT NULL AND task_id != ''
           GROUP BY task_id"""
    ).fetchall()


def paired_turns_by_task(rows):
    """task_id -> (sorted [(start_dt, stop_dt)], unpaired_count)."""
    grouped = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        if row["turn_id"]:
            grouped[row["task_id"]][row["turn_id"]].setdefault(row["event_type"], row["received_at"])
    out = {}
    for task_id, turns in grouped.items():
        paired, unpaired = [], 0
        for turn in turns.values():
            start, stop = turn.get("turn.start"), turn.get("turn.stop")
            if start and stop and stop >= start:
                paired.append((parse_ts(start), parse_ts(stop)))
            else:
                unpaired += 1
        paired.sort()
        out[task_id] = (paired, unpaired)
    return out


def minutes(delta):
    return delta.total_seconds() / 60


def bucketize(values):
    counts = [0] * len(HIST_LABELS)
    for value in values:
        for i, edge in enumerate(HIST_EDGES):
            if value < edge:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    return [{"label": label, "count": count} for label, count in zip(HIST_LABELS, counts, strict=True)]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def load_profiles(home):
    """task_id -> "model/effort" from each task folder's session.json."""
    profiles = {}
    tasks_dir = home / "tasks"
    if not tasks_dir.is_dir():
        return profiles
    for folder in tasks_dir.iterdir():
        session = folder / "session.json"
        if not session.is_file():
            continue
        try:
            data = json.loads(session.read_text())
        except (OSError, ValueError):
            continue
        profile = data.get("profile", {})
        profiles[data.get("id", folder.name)] = f"{profile.get('model', '?')}/{profile.get('effort', '?')}"
    return profiles


def durations_data(connection, home):
    turn_rows = load_turn_events(connection)
    by_task = paired_turns_by_task(turn_rows)
    tasks = []
    turn_durations, gaps = [], []
    for span in load_task_spans(connection):
        task_id = span["task_id"]
        paired, unpaired = by_task.get(task_id, ([], 0))
        active = sum(minutes(stop - start) for start, stop in paired)
        for (_s1, e1), (s2, _e2) in zip(paired, paired[1:], strict=False):
            gap = minutes(s2 - e1)
            if gap >= 0:
                gaps.append(gap)
        turn_durations.extend(minutes(stop - start) for start, stop in paired)
        tasks.append({
            "task_id": task_id,
            "wall_min": round(minutes(parse_ts(span["last_seen"]) - parse_ts(span["first_seen"])), 1),
            "active_min": round(active, 1),
            "paired_turns": len(paired),
            "unpaired_turns": unpaired,
            "first_seen": span["first_seen"],
            "last_seen": span["last_seen"],
        })
    tasks.sort(key=lambda t: -t["wall_min"])

    profiles = load_profiles(home)
    active_by_task = {t["task_id"]: t["active_min"] for t in tasks}
    turns_by_task = {t["task_id"]: t["paired_turns"] for t in tasks}
    profile_agg = defaultdict(lambda: {"tasks": 0, "turns": 0, "active": 0.0})
    for task_id, profile in profiles.items():
        if task_id in active_by_task:
            agg = profile_agg[profile]
            agg["tasks"] += 1
            agg["turns"] += turns_by_task[task_id]
            agg["active"] += active_by_task[task_id]
    profile_rows = sorted(
        ({"profile": name, "tasks": agg["tasks"], "turns": agg["turns"],
          "active": round(agg["active"], 1),
          "avg_per_turn": round(agg["active"] / agg["turns"], 1) if agg["turns"] else 0}
         for name, agg in profile_agg.items()),
        key=lambda r: -r["active"])
    churn = sorted(
        ({"task_id": t["task_id"], "turns": t["paired_turns"], "active_min": t["active_min"]}
         for t in tasks if t["paired_turns"] > 0),
        key=lambda r: -r["turns"])[:15]

    def stats(values):
        if not values:
            return {"n": 0, "median": 0, "p90": 0}
        return {"n": len(values), "median": round(statistics.median(values), 1),
                "p90": round(percentile(values, 0.9), 1)}

    improve = {
        "turn_hist": bucketize(turn_durations),
        "gap_hist": bucketize(gaps),
        "turn_stats": stats(turn_durations),
        "gap_stats": stats(gaps),
        "profiles": profile_rows,
        "churn": churn,
    }
    return tasks, improve


def timeline_data(connection):
    turn_rows = load_turn_events(connection)
    if not turn_rows:
        raise SystemExit("rzr-report: no turn events in the store; nothing to draw")
    by_task = paired_turns_by_task(turn_rows)
    t0 = min(parse_ts(r["received_at"]) for r in turn_rows)

    def rel(dt):
        return round(minutes(dt - t0), 1)

    task_first_last = defaultdict(lambda: [None, None])
    for row in turn_rows:
        stamp = parse_ts(row["received_at"])
        entry = task_first_last[row["task_id"]]
        entry[0] = stamp if entry[0] is None else min(entry[0], stamp)
        entry[1] = stamp if entry[1] is None else max(entry[1], stamp)

    tasks, all_turns, gaps = [], [], []
    for task_id, (first, last) in task_first_last.items():
        paired, _unpaired = by_task.get(task_id, ([], 0))
        turns = [(rel(start), rel(stop)) for start, stop in paired]
        tasks.append({"id": task_id, "first": rel(first), "last": rel(last), "turns": turns})
        all_turns.extend(turns)
        for (_s1, e1), (s2, _e2) in zip(turns, turns[1:], strict=False):
            if s2 >= e1:
                gaps.append((e1, s2 - e1))
    tasks.sort(key=lambda t: t["first"])

    deltas = sorted([(start, 1) for start, _ in all_turns] + [(stop, -1) for _, stop in all_turns])
    concurrency, current = [], 0
    for stamp, delta in deltas:
        current += delta
        if concurrency and concurrency[-1][0] == stamp:
            concurrency[-1][1] = current
        else:
            concurrency.append([stamp, current])

    trend = defaultdict(list)
    for when, gap in gaps:
        trend[int(when // TREND_BUCKET_MIN)].append(gap)
    trend_rows = [{"bucket": bucket * TREND_BUCKET_MIN, "median": round(statistics.median(values), 1),
                   "n": len(values)} for bucket, values in sorted(trend.items())]

    def counts(column):
        return [{"label": row[0] if row[0] else "(empty)", "count": row[1]}
                for row in connection.execute(
                    f"SELECT {column}, COUNT(*) FROM task_projections GROUP BY {column} ORDER BY 2 DESC")]

    return {
        "t0": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "span_min": round(max(t["last"] for t in tasks), 1),
        "tasks": tasks,
        "concurrency": concurrency,
        "max_concurrency": max((c for _, c in concurrency), default=0),
        "gap_trend": trend_rows,
        "verdict": counts("verdict"),
        "availability": counts("availability"),
        "report_state": counts("report_state"),
        "actionable_reason": counts("actionable_reason"),
    }


def render(template_name, substitutions, destination):
    template = TEMPLATES / template_name
    if not template.is_file():
        raise SystemExit(f"rzr-report: missing template {template}")
    html = template.read_text()
    for placeholder, value in substitutions.items():
        html = html.replace(placeholder, value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", nargs="?", default="all", choices=["durations", "timeline", "all"])
    parser.add_argument("--home", help="rozoro home (default: $ROZORO_HOME, $RZR_HOME, ~/.rozoro)")
    parser.add_argument("--out", help="output directory (default: <home>/reports)")
    args = parser.parse_args()

    import os
    home = Path(args.home or os.environ.get("ROZORO_HOME") or os.environ.get("RZR_HOME")
                or Path.home() / ".rozoro").expanduser()
    out_dir = Path(args.out).expanduser() if args.out else home / "reports"
    generated = datetime.now(timezone.utc)
    date_tag = generated.strftime("%Y-%m-%d")
    stamp = generated.strftime("%Y-%m-%d %H:%M UTC")

    connection = open_store(home)
    try:
        written = []
        if args.report in ("durations", "all"):
            tasks, improve = durations_data(connection, home)
            written.append(render(
                "task-durations.html",
                {"__DATA__": json.dumps(tasks, separators=(",", ":")),
                 "__IMPROVE__": json.dumps(improve, separators=(",", ":")),
                 "__GENERATED__": stamp},
                out_dir / f"task-durations-{date_tag}.html"))
        if args.report in ("timeline", "all"):
            written.append(render(
                "fleet-timeline.html",
                {"__DATA__": json.dumps(timeline_data(connection), separators=(",", ":")),
                 "__GENERATED__": stamp},
                out_dir / f"fleet-timeline-{date_tag}.html"))
    finally:
        connection.close()
    for path in written:
        print(path)


if __name__ == "__main__":
    sys.exit(main())
