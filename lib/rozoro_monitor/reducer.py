"""Pure lifecycle reduction and legacy v2 projection compatibility.

This module owns no clocks, files, sockets, or persistence.  Callers provide
validated protocol events and persist the returned immutable value themselves.
Report state is deliberately carried beside, rather than folded into, runtime
availability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

FOREGROUNDS = frozenset({"running", "stopped", "unknown"})
BACKGROUNDS = frozenset({"active", "clear", "unknown"})
AVAILABILITIES = frozenset(
    {"busy", "waiting-background", "quiescent", "blocked", "gone", "unknown"}
)


@dataclass(frozen=True)
class ReportState:
    """Independent handoff/report facts; neither field is a lifecycle fact."""

    verdict: str | None = None
    status: str = "unobserved"
    accepted: bool = False


@dataclass(frozen=True)
class PendingEvent:
    producer_seq: int
    fields: tuple[tuple[str, Any], ...]

    def thaw(self) -> dict[str, Any]:
        return dict(self.fields)


@dataclass(frozen=True)
class LifecycleState:
    foreground: str = "unknown"
    background: str = "unknown"
    availability: str = "unknown"
    # True only after an authoritative count/boolean established a baseline.
    background_certified: bool = False
    active_jobs: frozenset[str] = frozenset()
    # Active jobs certified by a count-only snapshot cannot be named.
    anonymous_active: int = 0
    # Positive presence without an authoritative identity/count baseline.
    active_presence_only: bool = False
    producer_seq: int = 0
    pending_events: tuple[PendingEvent, ...] = ()
    sequence_gap: bool = False
    session_ended: bool = False
    session_gone: bool = False
    adapter_connected: bool = True
    # Disconnect invalidates each semantic axis independently. Identity-only
    # traffic and facts for the other axis cannot recertify it.
    foreground_fresh: bool = True
    background_fresh: bool = True
    blocked: bool = False
    report: ReportState = ReportState()

    @property
    def active_count(self) -> int | None:
        if self.background == "unknown" or not self.background_certified:
            return None
        return len(self.active_jobs) + self.anonymous_active


@dataclass(frozen=True)
class Reduction:
    state: LifecycleState
    applied: bool
    reason: str | None = None


def derive_availability(
    foreground: str,
    background: str,
    *,
    blocked: bool = False,
    gone: bool = False,
    adapter_connected: bool = True,
) -> str:
    """Derive availability conservatively from independent certified axes."""
    if gone:
        return "gone"
    if not adapter_connected:
        return "unknown"
    if blocked:
        return "blocked"
    if foreground == "running":
        return "busy"
    if foreground == "stopped" and background == "active":
        return "waiting-background"
    if foreground == "stopped" and background == "clear":
        return "quiescent"
    return "unknown"


def _finish(state: LifecycleState, **changes: Any) -> LifecycleState:
    candidate = replace(state, **changes)
    return replace(
        candidate,
        availability=derive_availability(
            candidate.foreground if candidate.foreground_fresh else "unknown",
            candidate.background if candidate.background_fresh else "unknown",
            blocked=candidate.blocked and candidate.foreground_fresh,
            gone=candidate.session_ended or candidate.session_gone,
            adapter_connected=candidate.adapter_connected and not candidate.sequence_gap,
        ),
    )


def reduce_event(state: LifecycleState, event: Mapping[str, Any]) -> Reduction:
    """Buffer gaps and apply producer events strictly in contiguous order."""
    seq = event.get("producer_seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
        raise ValueError("producer_seq must be a positive integer")
    if seq <= state.producer_seq or any(item.producer_seq == seq for item in state.pending_events):
        return Reduction(state, False, "stale-producer-seq")
    if seq > state.producer_seq + 1:
        pending = PendingEvent(seq, tuple(sorted(event.items())))
        queued = tuple(sorted((*state.pending_events, pending), key=lambda item: item.producer_seq))
        # A gap invalidates the projected certification immediately while
        # retaining the pre-gap facts needed for deterministic ordered replay.
        buffered = _finish(state, pending_events=queued, sequence_gap=True)
        return Reduction(buffered, False, "producer-seq-gap")

    current = _apply_contiguous(state, event)
    while current.pending_events and current.pending_events[0].producer_seq == current.producer_seq + 1:
        item = current.pending_events[0]
        current = replace(current, pending_events=current.pending_events[1:])
        current = _apply_contiguous(current, item.thaw())
    current = _finish(current, sequence_gap=bool(current.pending_events))
    return Reduction(current, True)


def _apply_contiguous(state: LifecycleState, event: Mapping[str, Any]) -> LifecycleState:
    seq = event["producer_seq"]
    kind = event.get("type")
    changes: dict[str, Any] = {"producer_seq": seq, "adapter_connected": True}
    # A session ID denotes one session. Once ended, later events cannot revive
    # it; a caller must create a new state for a genuinely new session.
    if state.session_ended:
        return _finish(state, **changes)

    jobs = set(state.active_jobs)
    anonymous = state.anonymous_active
    presence_only = state.active_presence_only
    background = state.background
    certified_baseline = state.background_certified

    if kind == "session.register":
        pass
    elif kind == "turn.start":
        changes.update(foreground="running", foreground_fresh=True, blocked=False)
    elif kind == "turn.stop":
        changes.update(foreground="stopped", foreground_fresh=True, blocked=False)
        certified = event.get("background_active")
        if certified is False:
            jobs.clear()
            anonymous = 0
            presence_only = False
            background = "clear"
            certified_baseline = True
            changes["background_fresh"] = True
        elif certified is True:
            # A boolean certifies activity but not an identity or exact count.
            if not jobs and anonymous == 0:
                presence_only = True
            background = "active"
            changes["background_fresh"] = True
            # Presence is certified, but true supplies neither an exact count
            # nor a zero baseline from which later stops can prove clear.
            certified_baseline = False
        else:
            # Unknown does not negate positive facts already observed. It only
            # leaves an empty background axis uncertified.
            certified_baseline = False
            if jobs or anonymous or presence_only:
                background = "active"
            else:
                background = "unknown"
    elif kind == "background.start":
        changes["background_fresh"] = True
        job_id = event["job_id"]
        jobs.add(job_id)
        background = "active"
    elif kind == "background.stop":
        changes["background_fresh"] = True
        job_id = event["job_id"]
        if job_id in jobs:
            jobs.remove(job_id)
        elif anonymous:
            anonymous -= 1
        elif presence_only:
            # A stop may correspond to the presence-only fact, but cannot prove
            # that no other unobserved job remains.
            presence_only = False
        # Only a certified baseline/count can prove that no unobserved job
        # remains. Merely observing start then stop from unknown stays unknown.
        background = "clear" if not jobs and not anonymous and not presence_only and certified_baseline else (
            "active" if jobs or anonymous or presence_only else "unknown"
        )
    elif kind == "background.snapshot":
        changes["background_fresh"] = True
        jobs.clear()
        anonymous = event["active_count"]
        presence_only = False
        background = "active" if anonymous else "clear"
        certified_baseline = True
    elif kind == "session.end":
        changes.update(
            foreground="stopped",
            foreground_fresh=True,
            background_fresh=True,
            session_ended=True,
            session_gone=True,
        )
        jobs.clear()
        anonymous = 0
        presence_only = False
        background = "clear"
        certified_baseline = True
    else:
        raise ValueError(f"unsupported lifecycle event type: {kind!r}")

    changes.update(
        active_jobs=frozenset(jobs),
        anonymous_active=anonymous,
        active_presence_only=presence_only,
        background=background,
        background_certified=certified_baseline,
    )
    return _finish(state, **changes)


def observe_gone(state: LifecycleState, gone: bool = True) -> LifecycleState:
    """Apply host liveness; explicit session end is terminal for this state."""
    return _finish(state, session_gone=state.session_ended or gone)


def set_adapter_connected(state: LifecycleState, connected: bool) -> LifecycleState:
    """Reconnect transport without recertifying stale semantic observations."""
    return _finish(
        state,
        adapter_connected=connected,
        foreground_fresh=False,
        background_fresh=False,
        background_certified=False,
    )


def with_report(
    state: LifecycleState,
    *,
    verdict: str | None,
    status: str,
    accepted: bool = False,
) -> LifecycleState:
    """Attach report facts without changing lifecycle axes or availability."""
    return replace(state, report=ReportState(verdict, status, accepted))


def _map_v2_background(bg: Any) -> tuple[str, frozenset[str], int, bool, bool]:
    """Validate legacy state/count/jobs as one conservative tuple."""
    unknown = ("unknown", frozenset(), 0, False, False)
    if not isinstance(bg, Mapping) or bg.get("supported") is not True:
        return unknown

    state = bg.get("state")
    if state not in BACKGROUNDS:
        return unknown

    raw_count = bg.get("active_count")
    if raw_count is not None and (
        not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 0
    ):
        return unknown

    raw_jobs = bg.get("jobs", [])
    if raw_jobs is None:
        raw_jobs = []
    if not isinstance(raw_jobs, list):
        return unknown
    parsed_jobs: list[str] = []
    for job in raw_jobs:
        if isinstance(job, str):
            job_id = job
        elif isinstance(job, Mapping):
            job_id = job.get("id")
        else:
            return unknown
        if not isinstance(job_id, str) or not job_id:
            return unknown
        parsed_jobs.append(job_id)
    if len(set(parsed_jobs)) != len(parsed_jobs):
        return unknown
    jobs = frozenset(parsed_jobs)

    if state == "clear":
        if jobs or raw_count not in (None, 0):
            return unknown
        return ("clear", frozenset(), 0, True, False)
    if state == "unknown":
        return unknown

    # Active with explicit zero contradicts itself. A positive count and a
    # non-empty job list must describe the same aggregate when both are given.
    if raw_count == 0:
        return unknown
    if raw_count is not None and jobs and raw_count != len(jobs):
        return unknown
    if raw_count is not None:
        return ("active", jobs, raw_count - len(jobs), True, False)
    if jobs:
        return ("active", jobs, 0, True, False)
    # State alone proves positive presence, but not a count that stops can drain.
    return ("active", frozenset(), 0, False, True)


def map_v2_projection(runtime: Mapping[str, Any], status: Mapping[str, Any] | None = None) -> LifecycleState:
    """Purely map current ``rzr-runtime.py``/``rzr-status --json`` v2 shapes.

    Legacy Herdr foreground observations do not certify background clear.  A
    stale source is wholly uncertified.  Report verdicts are copied only onto
    the independent report axis and never imply acceptance.
    """
    status = status or {}
    source = runtime.get("source") or {}
    freshness = status.get("runtime_freshness", source.get("freshness", "current"))
    raw_fg = status.get("foreground_status", runtime.get("foreground_status"))
    raw_runtime = status.get("runtime_status", runtime.get("runtime_status", "unknown"))

    if freshness != "current":
        foreground = "unknown"
        background = "unknown"
        gone = False
        blocked = False
    else:
        foreground = "running" if raw_fg == "working" else (
            "stopped" if raw_fg in {"idle", "done", "blocked"} else "unknown"
        )
        gone = raw_fg == "gone" or raw_runtime == "gone"
        blocked = raw_fg == "blocked" or raw_runtime == "blocked"
        bg = status.get("background_activity", runtime.get("background_activity", {}))
        background, jobs, anonymous, exact_background, presence_only = _map_v2_background(bg)

    if freshness != "current":
        jobs = frozenset()
        anonymous = 0
        exact_background = False
        presence_only = False

    verdict = status.get("handoff_verdict")
    if isinstance(verdict, str):
        verdict = verdict.casefold()
    report_status = status.get("turn_report_status", (runtime.get("turn") or {}).get("report_status", "unobserved"))
    state = LifecycleState(
        foreground=foreground,
        background=background,
        background_certified=exact_background,
        active_jobs=jobs,
        anonymous_active=anonymous,
        active_presence_only=presence_only,
        # Herdr v2 event_seq is a different ordering domain from native
        # producer_seq and must never seed protocol replay state.
        producer_seq=0,
        session_gone=gone,
        blocked=blocked,
        report=ReportState(verdict, report_status, False),
    )
    return _finish(state)
