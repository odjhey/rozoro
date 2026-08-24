"""Test-only subprocess hook: record and reap exact daemon ownership."""
import atexit
import json
import os
import signal
import subprocess
from pathlib import Path

_real_popen = subprocess.Popen


def _birth(pid, token):
    try:
        return "proc:" + Path(f"/proc/{pid}/stat").read_text().split()[21]
    except (OSError, IndexError):
        # A random nonce is injected into the child environment below. Unlike a
        # wall-clock timestamp it cannot validate a reused PID accidentally.
        return "token:" + token


class RecordingPopen(_real_popen):
    def __init__(self, args, *pargs, **kwargs):
        values = [os.fspath(value) for value in args] if isinstance(args, (list, tuple)) else []
        env = dict(kwargs.get("env") or os.environ)
        registry = env.get("ROZORO_TEST_PROCESS_REGISTRY")
        owned = len(values) == 4 and values[2] == "--home" and os.path.basename(values[1]) == "rozorod.py"
        if owned and registry:
            token = os.urandom(24).hex()
            env["ROZORO_TEST_PROCESS_TOKEN"] = token
            kwargs["env"] = env
        super().__init__(args, *pargs, **kwargs)
        if owned and registry:
            try:
                record = {"pid": self.pid, "pgid": self.pid if kwargs.get("start_new_session") else os.getpgid(self.pid),
                          "birth": _birth(self.pid, token), "home": os.path.realpath(values[3]),
                          "argv": [os.path.realpath(values[0]), os.path.realpath(values[1]), "--home", os.path.realpath(values[3])],
                          "token": token}
                fd = os.open(registry, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    import fcntl; fcntl.flock(fd, fcntl.LOCK_EX)
                    os.write(fd, (json.dumps(record, separators=(",", ":")) + "\n").encode())
                    os.fsync(fd)
                finally: os.close(fd)
            except Exception:
                try:
                    os.killpg(self.pid if kwargs.get("start_new_session") else os.getpgid(self.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.wait(timeout=5)
                raise


subprocess.Popen = RecordingPopen

# A production stop correctly refuses after its proof files are destroyed. Tests
# still own the exact spawn record, so reap that owner at process exit without
# weakening production stop semantics or consulting mutable lock/socket state.
if (os.environ.get("ROZORO_TEST_CLEANUP_ON_STOP") == "1"
        and os.environ.get("ROZORO_TEST_PROCESS_REGISTRY")
        and os.path.basename(__import__("sys").argv[0]) == "rzr-monitor.py"
        and "stop" in __import__("sys").argv[1:]):
    def _cleanup_failed_or_completed_stop():
        from tests.test_helper.process_cleanup import cleanup
        cleanup()
    atexit.register(_cleanup_failed_or_completed_stop)
