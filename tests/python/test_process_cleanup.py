import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.test_helper import process_cleanup

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "bin/rozorod.py"


class ExactProcessCleanupTests(unittest.TestCase):
    def test_spaces_missing_malformed_wrong_lock_and_argv_spoof_fail_closed(self):
        for lock_case in ("missing", "malformed", "wrong-owner"):
            with self.subTest(lock_case=lock_case), tempfile.TemporaryDirectory(prefix="owned cleanup ") as temporary:
                home = Path(temporary) / "home with spaces"
                process = subprocess.Popen([sys.executable, str(DAEMON), "--home", str(home)],
                                           start_new_session=True)
                process_cleanup.register(process, home)
                deadline = time.monotonic() + 5
                while not (home / "monitor.lock").exists() and time.monotonic() < deadline: time.sleep(.02)
                lock = home / "monitor.lock"
                if lock_case == "missing": lock.unlink()
                elif lock_case == "malformed": lock.write_text("{malformed")
                else: lock.write_text('{"pid":1,"socket_dev":0,"socket_ino":0}')
                spoof = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)",
                                          "rozorod.py", "--home", str(home)])
                try:
                    with self.assertRaises(RuntimeError): process_cleanup.register(spoof, home)
                    with self.assertRaises(RuntimeError): process_cleanup.register(process, Path(temporary) / "wrong")
                    process_cleanup.cleanup(); process.wait(timeout=5)
                    self.assertIsNone(spoof.poll())
                finally:
                    spoof.terminate(); spoof.wait(timeout=5)

    def test_parallel_owned_process_groups_are_independent(self):
        with tempfile.TemporaryDirectory(prefix="owned-parallel-") as temporary:
            processes = []
            for number in range(3):
                home = Path(temporary) / f"home-{number}"
                process = subprocess.Popen([sys.executable, str(DAEMON), "--home", str(home)],
                                           start_new_session=True)
                process_cleanup.register(process, home); processes.append(process)
            process_cleanup.cleanup()
            for process in processes: process.wait(timeout=5)


if __name__ == "__main__": unittest.main()
