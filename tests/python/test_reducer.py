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

    def test_all_sequence_arrival_permutations_replay_without_false_quiescence(self):
        ordered = (
            event("turn.stop", 1, background_active=False),
            event("background.start", 2, job_id="job"),
            event("background.stop", 3, job_id="job"),
        )
        expected = None
        for arrival in itertools.permutations(ordered):
            state = LifecycleState()
            for item in arrival:
                result = reduce_event(state, item)
                state = result.state
                if result.reason == "producer-seq-gap":
                    self.assertNotEqual(state.availability, "quiescent")
            projection = (state.foreground, state.background, state.availability,
                          state.producer_seq, state.active_jobs, state.pending_events)
            expected = projection if expected is None else expected
            self.assertEqual(projection, expected)
        self.assertEqual(expected[:4], ("stopped", "clear", "quiescent", 3))

    def test_duplicate_or_applied_lower_sequence_is_stale(self):
        state = reduce_event(LifecycleState(), event("turn.start", 1)).state
        duplicate = reduce_event(state, event("turn.start", 1))
        self.assertFalse(duplicate.applied)
        self.assertEqual(duplicate.reason, "stale-producer-seq")

    def test_active_boolean_is_not_an_exact_count_baseline(self):
        state = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=True)).state
        self.assertEqual(state.availability, "waiting-background")
        state = reduce_event(state, event("background.stop", 2, job_id="possibly-known")).state
        self.assertEqual((state.background, state.availability), ("unknown", "unknown"))

    def test_turn_stop_unknown_fails_closed_only_without_positive_facts(self):
        state = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=None)).state
        self.assertEqual((state.foreground, state.background, state.availability),
                         ("stopped", "unknown", "unknown"))

    def test_turn_stop_unknown_preserves_named_and_anonymous_active_facts(self):
        named = reduce_event(LifecycleState(), event("background.start", 1, job_id="named")).state
        named = reduce_event(named, event("turn.stop", 2, background_active=None)).state
        self.assertEqual(named.active_jobs, frozenset({"named"}))
        self.assertEqual((named.background, named.availability), ("active", "waiting-background"))

        anonymous = reduce_event(LifecycleState(), event("background.snapshot", 1, active_count=2)).state
        anonymous = reduce_event(anonymous, event("turn.stop", 2, background_active=None)).state
        self.assertEqual(anonymous.anonymous_active, 2)
        self.assertEqual((anonymous.background, anonymous.availability), ("active", "waiting-background"))

    def test_reconnect_requires_both_axes_before_waiting_background(self):
        base = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=False)).state
        state = set_adapter_connected(set_adapter_connected(base, False), True)
        state = reduce_event(state, event("background.start", 2, job_id="fresh-job")).state
        self.assertEqual(state.availability, "unknown")  # foreground remains stale
        state = reduce_event(state, event("turn.stop", 3, background_active=None)).state
        self.assertEqual(state.availability, "waiting-background")

    def test_disconnect_drops_exact_baseline_until_authoritative_repair(self):
        state = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=False)).state
        state = set_adapter_connected(set_adapter_connected(state, False), True)
        state = reduce_event(state, event("background.start", 2, job_id="job")).state
        state = reduce_event(state, event("turn.stop", 3, background_active=None)).state
        state = reduce_event(state, event("background.stop", 4, job_id="job")).state
        self.assertEqual((state.background, state.availability, state.active_count),
                         ("unknown", "unknown", None))
        state = reduce_event(state, event("background.snapshot", 5, active_count=0)).state
        self.assertEqual((state.background, state.availability, state.active_count),
                         ("clear", "quiescent", 0))

    def test_null_aggregate_invalidates_snapshot_exactness_until_repair(self):
        state = reduce_event(LifecycleState(), event("background.snapshot", 1, active_count=2)).state
        state = reduce_event(state, event("turn.stop", 2, background_active=None)).state
        self.assertEqual((state.background, state.anonymous_active, state.active_count),
                         ("active", 2, None))
        state = reduce_event(state, event("background.stop", 3, job_id="one")).state
        state = reduce_event(state, event("background.stop", 4, job_id="two")).state
        self.assertEqual((state.background, state.availability, state.active_count),
                         ("unknown", "unknown", None))
        state = reduce_event(state, event("turn.stop", 5, background_active=False)).state
        self.assertEqual((state.background, state.availability), ("clear", "quiescent"))

    def test_session_end_and_host_gone(self):
        state = reduce_event(LifecycleState(), event("background.start", 1, job_id="a")).state
        state = reduce_event(state, event("session.end", 2)).state
        self.assertTrue(state.session_ended)
        self.assertEqual((state.background, state.availability), ("clear", "gone"))
        state = observe_gone(state, False)
        self.assertTrue(state.session_gone)
        self.assertEqual(state.availability, "gone")
        registered = reduce_event(state, event("session.register", 3)).state
        started = reduce_event(registered, event("turn.start", 4)).state
        self.assertTrue(started.session_ended)
        self.assertEqual(started.availability, "gone")

    def test_disconnected_adapter_is_unknown_without_erasing_facts(self):
        state = reduce_event(LifecycleState(), event("turn.stop", 1, background_active=False)).state
        disconnected = set_adapter_connected(state, False)
        self.assertEqual(disconnected.availability, "unknown")
        self.assertEqual((disconnected.foreground, disconnected.background), ("stopped", "clear"))
        reconnected = set_adapter_connected(disconnected, True)
        self.assertEqual(reconnected.availability, "unknown")
        identity_only = reduce_event(reconnected, event("session.register", 2)).state
        self.assertEqual(identity_only.availability, "unknown")
        background_only = reduce_event(identity_only, event("background.snapshot", 3, active_count=0)).state
        self.assertEqual(background_only.availability, "unknown")
        recertified = reduce_event(background_only, event("turn.stop", 4, background_active=False)).state
        self.assertEqual(recertified.availability, "quiescent")

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
            "handoff_verdict": "Done",
            "turn_report_status": "reported",
        }
        state = map_v2_projection({}, status)
        self.assertEqual(state.report.verdict, "done")
        self.assertFalse(state.report.accepted)
        self.assertEqual(state.availability, "unknown")

    def test_blocked_and_gone_map_without_report_coupling(self):
        self.assertEqual(map_v2_projection(self.runtime("blocked")).availability, "blocked")
        self.assertEqual(map_v2_projection(self.runtime("gone")).availability, "gone")

    def test_shell_cannot_be_quiescent_even_with_legacy_clear(self):
        state = map_v2_projection(self.runtime("shell", True, "clear"))
        self.assertEqual((state.foreground, state.availability), ("unknown", "unknown"))

    def test_v2_event_sequence_does_not_seed_native_producer_order(self):
        state = map_v2_projection(self.runtime("working"))
        self.assertEqual(state.producer_seq, 0)
        native = reduce_event(state, event("turn.start", 1))
        self.assertTrue(native.applied)
        self.assertEqual(native.state.producer_seq, 1)

    def test_v2_presence_only_active_does_not_invent_exact_count(self):
        state = map_v2_projection(self.runtime("idle", True, "active"))
        self.assertEqual((state.background, state.availability, state.active_count),
                         ("active", "waiting-background", None))
        self.assertTrue(state.active_presence_only)
        stopped = reduce_event(state, event("background.stop", 1, job_id="unknown-job")).state
        self.assertEqual((stopped.background, stopped.availability), ("unknown", "unknown"))


if __name__ == "__main__":
    unittest.main()
