import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.rozoro_monitor.store import EventStore

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("codex_hook", ROOT / "hooks/codex-rozoro-event.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CodexNativeHookTests(unittest.TestCase):
    def test_stop_preserves_unknown_background(self):
        with patch.dict(os.environ, {"ROZORO_TASK_ID": "task-1"}, clear=True):
            events = hook.map_payload({"hook_event_name": "Stop", "session_id": "native-1", "turn_id": "turn-1"})
        self.assertEqual(events[0]["type"], "turn.stop")
        self.assertIsNone(events[0]["background_active"])

    def test_turn_end_with_new_report_wakes_without_claiming_quiescence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = Path(tmp) / "tasks"
            folder = tasks / "task-1"
            folder.mkdir(parents=True)
            store = EventStore(Path(tmp) / "monitor.db", tasks_dir=tasks)
            def envelope(kind, seq):
                value = {"v": 1, "type": kind, "event_id": f"e-{seq}", "producer_seq": seq,
                         "session_id": "native-1", "harness": "codex", "role": "crew", "task_id": "task-1"}
                if kind in {"turn.start", "turn.stop"}: value["turn_id"] = "turn-1"
                if kind == "turn.stop": value["background_active"] = None
                return value
            self.assertIsNone(store.accept_event(envelope("session.register", 1)).generation)
            self.assertIsNone(store.accept_event(envelope("turn.start", 2)).generation)
            (folder / "handoff.md").write_text("## turn 1 — complete\nverdict:       done\ndid:           fixed\npending:       none\ninputs-needed: none\nartifacts:     none\n")
            result = store.accept_event(envelope("turn.stop", 3))
            self.assertEqual(result.generation, 1)
            row = store._connection.execute("SELECT availability,actionable_reason FROM task_projections").fetchone()
            self.assertEqual(tuple(row), ("unknown", "none"))
            reason = store._connection.execute("SELECT actionable_reason FROM pending_generation_tasks").fetchone()[0]
            self.assertEqual(reason, "native-turn-ended-report")
            store.close()


if __name__ == "__main__": unittest.main()
