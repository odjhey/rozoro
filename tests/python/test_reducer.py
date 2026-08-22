import itertools
import unittest

from lib.rozoro_monitor.reducer import (
    BACKGROUNDS,
    FOREGROUNDS,
    LifecycleState,
    derive_availability,
    map_v2_projection,
    observe_gone,
    reduce_event,
    set_adapter_connected,
    with_report,
)


def event(kind, seq, **fields):
    return {"v": 1, "type": kind, "producer_seq": seq, **fields}


class AvailabilityMatrixTests(unittest.TestCase):
    def test_exhaustive_foreground_background_matrix(self):
        expected = {
            ("running", "active"): "busy",
            ("running", "clear"): "busy",
            ("running", "unknown"): "busy",
            ("stopped", "active"): "waiting-background",
            ("stopped", "clear"): "quiescent",
        }
        for foreground, background in itertools.product(FOREGROUNDS, BACKGROUNDS):
            with self.subTest(foreground=foreground, background=background):
                self.assertEqual(
                    derive_availability(foreground, background),
                    expected.get((foreground, background), "unknown"),
                )

    def test_disconnect_gone_and_blocked_precedence(self):
        self.assertEqual(derive_availability("stopped", "clear", adapter_connected=False), "unknown")
        self.assertEqual(derive_availability("stopped", "clear", blocked=True), "blocked")
        self.assertEqual(derive_availability("running", "active", gone=True), "gone")


class ReducerTests(unittest.TestCase):
    def test_stopped_active_waits_then_clear_quiesces(self):
        state = reduce_event(LifecycleState(), event("background.snapshot", 1, active_count=2)).state
        state = reduce_event(state, event("turn.stop", 2, background_active=True)).state
        self.assertEqual((state.foreground, state.background, state.availability),
                         ("stopped", "active", "waiting-background"))
        state = reduce_event(state, event("background.snapshot", 3, active_count=0)).state
        self.assertEqual((state.background, state.availability), ("clear", "quiescent"))

    def test_active_jobs_are_ids_and_incremental_updates_follow_certified_baseline(self):
        state = reduce_event(LifecycleState(), event("background.snapshot", 1, active_count=0)).state
        state = reduce_event(state, event("background.start", 2, job_id="a")).state
        state = reduce_event(state, event("background.start", 3, job_id="b")).state
        self.assertEqual(state.active_jobs, frozenset({"a", "b"}))
        self.assertEqual(state.active_count, 2)
        state = reduce_event(state, event("background.stop", 4, job_id="a")).state
        state = reduce_event(state, event("background.stop", 5, job_id="b")).state
        self.assertEqual((state.background, state.active_count), ("clear", 0))

    def test_uncertified_incremental_completion_remains_unknown(self):
        state = reduce_event(LifecycleState(), event("background.start", 1, job_id="a")).state
        state = reduce_event(state, event("background.stop", 2, job_id="a")).state
        self.assertEqual((state.background, state.active_count), ("unknown", None))

    def test_authoritative_snapshot_repairs_missed_increment_and_count_only_stop(self):
        state = reduce_event(LifecycleState(), event("background.start", 1, job_id="seen")).state
        state = reduce_event(state, event("background.snapshot", 2, active_count=3)).state
        self.assertEqual((state.active_jobs, state.anonymous_active, state.active_count),
                         (frozenset(), 3, 3))
        state = reduce_event(state, event("background.stop", 3, job_id="missed-id")).state
        self.assertEqual(state.active_count, 2)
        state = reduce_event(state, event("background.snapshot", 4, active_count=0)).state
        self.assertEqual((state.background, state.active_count), ("clear", 0))

    def test_stale_sequence_and_stop_before_start_replay(self):
        stopped = reduce_event(LifecycleState(), event("background.stop", 9, job_id="job")).state
        replay = reduce_event(stopped, event("background.start", 8, job_id="job"))
        self.assertFalse(replay.applied)
        self.assertEqual(replay.reason, "stale-producer-seq")
        self.assertEqual(replay.state.active_jobs, frozenset())
        duplicate = reduce_event(stopped, event("background.stop", 9, job_id="job"))
        self.assertFalse(duplicate.applied)

    def test_turn_stop_unknown_fails_closed(self):
        state = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=None)).state
        self.assertEqual((state.foreground, state.background, state.availability),
                         ("stopped", "unknown", "unknown"))

    def test_session_end_and_host_gone(self):
        state = reduce_event(LifecycleState(), event("background.start", 1, job_id="a")).state
        state = reduce_event(state, event("session.end", 2)).state
        self.assertTrue(state.session_ended)
        self.assertEqual((state.background, state.availability), ("clear", "gone"))
        state = observe_gone(state)
        self.assertEqual(state.availability, "gone")

    def test_disconnected_adapter_is_unknown_without_erasing_facts(self):
        state = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=False)).state
        disconnected = set_adapter_connected(state, False)
        self.assertEqual(disconnected.availability, "unknown")
        self.assertEqual((disconnected.foreground, disconnected.background), ("stopped", "clear"))
        self.assertEqual(set_adapter_connected(disconnected, True).availability, "quiescent")

    def test_report_done_never_changes_runtime_or_implies_acceptance(self):
        state = with_report(LifecycleState(), verdict="done", status="reported")
        self.assertEqual(state.availability, "unknown")
        self.assertFalse(state.report.accepted)
        active = reduce_event(state, event("background.start", 1, job_id="worker")).state
        done = with_report(active, verdict="done", status="reported")
        self.assertEqual(done.background, "active")
        self.assertNotEqual(done.availability, "quiescent")
        self.assertFalse(done.report.accepted)


class V2CompatibilityTests(unittest.TestCase):
    def runtime(self, foreground="idle", supported=None, bg_state="unknown", **extra):
        value = {
            "schema_version": 2,
            "source": {"freshness": "current", "event_seq": 7},
            "runtime_status": foreground,
            "foreground_status": foreground,
            "background_activity": {
                "supported": supported,
                "state": bg_state,
                "active_count": None,
                "jobs": [],
            },
            "turn": {"report_status": "reported"},
        }
        value.update(extra)
        return value

    def test_legacy_idle_without_background_support_remains_unknown(self):
        state = map_v2_projection(self.runtime("idle", False, "clear"))
        self.assertEqual((state.foreground, state.background, state.availability),
                         ("stopped", "unknown", "unknown"))

    def test_certified_v2_background_maps_both_settled_cases(self):
        active = map_v2_projection(self.runtime("done", True, "active"))
        clear = map_v2_projection(self.runtime("done", True, "clear"))
        self.assertEqual(active.availability, "waiting-background")
        self.assertEqual(clear.availability, "quiescent")

    def test_working_is_busy_even_when_background_unknown(self):
        self.assertEqual(map_v2_projection(self.runtime("working")).availability, "busy")

    def test_stale_v2_projection_is_uncertified(self):
        runtime = self.runtime("done", True, "clear")
        runtime["source"]["freshness"] = "stale"
        state = map_v2_projection(runtime)
        self.assertEqual((state.foreground, state.background, state.availability),
                         ("unknown", "unknown", "unknown"))

    def test_status_shape_report_done_is_not_acceptance_or_quiescence(self):
        status = {
            "runtime_status": "idle",
            "foreground_status": "idle",
            "runtime_freshness": "current",
            "background_activity": {"supported": None, "state": "unknown", "jobs": []},
            "handoff_verdict": "done",
            "turn_report_status": "reported",
        }
        state = map_v2_projection({}, status)
        self.assertEqual(state.report.verdict, "done")
        self.assertFalse(state.report.accepted)
        self.assertEqual(state.availability, "unknown")

    def test_blocked_and_gone_map_without_report_coupling(self):
        self.assertEqual(map_v2_projection(self.runtime("blocked")).availability, "blocked")
        self.assertEqual(map_v2_projection(self.runtime("gone")).availability, "gone")


if __name__ == "__main__":
    unittest.main()
