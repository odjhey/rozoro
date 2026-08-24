"""Test-only ownership registry for exact isolated rozorod processes."""
import atexit
import json
import os
import re
import signal
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

_owned: dict[int, Path] = {}
_cleaning = False


def _command(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except (OSError, UnicodeError):
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], text=True, check=False,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return result.stdout.strip() if result.returncode == 0 else ""


def _is_owned(pid: int, home: Path) -> bool:
    command = _command(pid)
    return "rozorod.py" in command and re.search(rf"--home {re.escape(str(home))}(?:\s|$)", command) is not None


def register(process: subprocess.Popen, home: Path) -> subprocess.Popen:
    home = Path(home).absolute()
    if not _is_owned(process.pid, home):
        raise RuntimeError(f"refusing to register pid {process.pid}: command does not own {home}")
    _owned[process.pid] = home
    return process


def register_lock(home: Path) -> int:
    home = Path(home).absolute()
    value = json.loads((home / "monitor.lock").read_text())
    pid = value.get("pid")
    if type(pid) is not int or pid <= 1 or not _is_owned(pid, home):
        raise RuntimeError(f"refusing unproven daemon owner for {home}")
    _owned[pid] = home
    return pid


def cleanup() -> None:
    global _cleaning
    if _cleaning:
        return
    _cleaning = True
    try:
        for pid, home in list(_owned.items()):
            if not _is_owned(pid, home):
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            deadline = time.monotonic() + 3
            while _is_owned(pid, home) and time.monotonic() < deadline:
                time.sleep(.02)
            if _is_owned(pid, home):
                os.kill(pid, signal.SIGKILL)
        for home in set(_owned.values()):
            temporary = Path(tempfile.gettempdir()).absolute()
            try:
                home.relative_to(temporary)
            except ValueError:
                continue
            shutil.rmtree(home, ignore_errors=True)
        _owned.clear()
    finally:
        _cleaning = False


def _interrupt(signum, _frame):
    cleanup()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


atexit.register(cleanup)
for _signal in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_signal, _interrupt)
