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
class LifecycleState:
    foreground: str = "unknown"
    background: str = "unknown"
    availability: str = "unknown"
    # True only after an authoritative count/boolean established a baseline.
    background_certified: bool = False
    active_jobs: frozenset[str] = frozenset()
    # Active jobs certified by a count-only snapshot cannot be named.
    anonymous_active: int = 0
    producer_seq: int = 0
    session_ended: bool = False
    session_gone: bool = False
    adapter_connected: bool = True
    blocked: bool = False
    report: ReportState = ReportState()

    @property
    def active_count(self) -> int | None:
        if self.background == "unknown":
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
            candidate.foreground,
            candidate.background,
            blocked=candidate.blocked,
            gone=candidate.session_gone,
            adapter_connected=candidate.adapter_connected,
        ),
    )


def reduce_event(state: LifecycleState, event: Mapping[str, Any]) -> Reduction:
    """Apply one validated protocol producer event.

    Sequence ordering is session-global.  An old replay is a no-op, which makes
    a stop received before its older start safe and deterministic.
    """
    seq = event.get("producer_seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
        raise ValueError("producer_seq must be a positive integer")
    if seq <= state.producer_seq:
        return Reduction(state, False, "stale-producer-seq")

    kind = event.get("type")
    changes: dict[str, Any] = {"producer_seq": seq, "adapter_connected": True}
    jobs = set(state.active_jobs)
    anonymous = state.anonymous_active
    background = state.background
    certified_baseline = state.background_certified

    if kind == "session.register":
        changes.update(session_ended=False, session_gone=False)
    elif kind == "turn.start":
        changes.update(foreground="running", blocked=False, session_ended=False)
    elif kind == "turn.stop":
        changes.update(foreground="stopped", blocked=False)
        certified = event.get("background_active")
        if certified is False:
            jobs.clear()
            anonymous = 0
            background = "clear"
            certified_baseline = True
        elif certified is True:
            # A boolean certifies activity but not an identity or exact count.
            if not jobs and anonymous == 0:
                anonymous = 1
            background = "active"
            certified_baseline = True
        else:
            jobs.clear()
            anonymous = 0
            background = "unknown"
            certified_baseline = False
    elif kind == "background.start":
        job_id = event["job_id"]
        jobs.add(job_id)
        background = "active"
    elif kind == "background.stop":
        job_id = event["job_id"]
        if job_id in jobs:
            jobs.remove(job_id)
        elif anonymous:
            anonymous -= 1
        # Only a certified baseline/count can prove that no unobserved job
        # remains. Merely observing start then stop from unknown stays unknown.
        background = "clear" if not jobs and not anonymous and certified_baseline else (
            "active" if jobs or anonymous else "unknown"
        )
    elif kind == "background.snapshot":
        jobs.clear()
        anonymous = event["active_count"]
        background = "active" if anonymous else "clear"
        certified_baseline = True
    elif kind == "session.end":
        changes.update(foreground="stopped", session_ended=True, session_gone=True)
        jobs.clear()
        anonymous = 0
        background = "clear"
        certified_baseline = True
    else:
        raise ValueError(f"unsupported lifecycle event type: {kind!r}")

    changes.update(
        active_jobs=frozenset(jobs),
        anonymous_active=anonymous,
        background=background,
        background_certified=certified_baseline,
    )
    return Reduction(_finish(state, **changes), True)


def observe_gone(state: LifecycleState, gone: bool = True) -> LifecycleState:
    """Apply host liveness without pretending it is a producer event."""
    return _finish(state, session_gone=gone)


def set_adapter_connected(state: LifecycleState, connected: bool) -> LifecycleState:
    """A live host with a disconnected semantic adapter is uncertified."""
    return _finish(state, adapter_connected=connected)


def with_report(
    state: LifecycleState,
    *,
    verdict: str | None,
    status: str,
    accepted: bool = False,
) -> LifecycleState:
    """Attach report facts without changing lifecycle axes or availability."""
    return replace(state, report=ReportState(verdict, status, accepted))


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
            "stopped" if raw_fg in {"idle", "done", "blocked", "shell"} else "unknown"
        )
        gone = raw_fg == "gone" or raw_runtime == "gone"
        blocked = raw_fg == "blocked" or raw_runtime == "blocked"
        bg = status.get("background_activity", runtime.get("background_activity", {})) or {}
        bg_state = bg.get("state")
        # supported=false/unknown cannot certify even if an incidental state says clear.
        background = bg_state if bg.get("supported") is True and bg_state in BACKGROUNDS else "unknown"

    bg_obj = status.get("background_activity", runtime.get("background_activity", {})) or {}
    jobs = frozenset(
        str(job.get("id", job)) if isinstance(job, Mapping) else str(job)
        for job in (bg_obj.get("jobs") or [])
    ) if background == "active" else frozenset()
    count = bg_obj.get("active_count")
    anonymous = max(0, count - len(jobs)) if background == "active" and isinstance(count, int) else 0
    if background == "active" and not jobs and anonymous == 0:
        anonymous = 1

    verdict = status.get("handoff_verdict")
    report_status = status.get("turn_report_status", (runtime.get("turn") or {}).get("report_status", "unobserved"))
    state = LifecycleState(
        foreground=foreground,
        background=background,
        background_certified=background != "unknown",
        active_jobs=jobs,
        anonymous_active=anonymous,
        producer_seq=source.get("event_seq") if isinstance(source.get("event_seq"), int) else 0,
        session_gone=gone,
        blocked=blocked,
        report=ReportState(verdict, report_status, False),
    )
    return _finish(state)
