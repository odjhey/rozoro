"""Test-only exact process ownership and cleanup.

Ownership comes from a Popen argv captured at spawn, or from the monitor launcher's
private spawn record. Mutable daemon lock/socket state is never ownership proof.
"""
import atexit
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

_owned: dict[int, dict] = {}
_cleaning = False


def _birth(pid: int) -> Optional[str]:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        return fields[21]
    except (OSError, IndexError):
        result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        value = result.stdout.strip()
        return value or None


def _canonical(path) -> str:
    return os.path.realpath(os.path.abspath(os.fspath(path)))


def _daemon_argv(home: Path) -> list[str]:
    root = Path(__file__).resolve().parents[2]
    return [_canonical(sys.executable), _canonical(root / "bin/rozorod.py"), "--home", _canonical(home)]


def _normalize_argv(argv) -> list[str]:
    values = [os.fspath(value) for value in argv]
    if len(values) == 4:
        values[0] = _canonical(values[0]); values[1] = _canonical(values[1])
        if values[2] == "--home": values[3] = _canonical(values[3])
    return values


def _record(pid: int, home: Path, argv: list[str], pgid: Optional[int] = None) -> dict:
    birth = _birth(pid)
    if birth is None:
        raise RuntimeError(f"process {pid} exited before ownership registration")
    expected = _daemon_argv(home)
    if _normalize_argv(argv) != expected:
        raise RuntimeError(f"refusing non-daemon argv for pid {pid}")
    value = {"pid": pid, "birth": birth, "pgid": pgid if pgid is not None else os.getpgid(pid),
             "home": expected[3], "argv": expected}
    _owned[pid] = value
    return value


def register(process: subprocess.Popen, home: Path) -> subprocess.Popen:
    _record(process.pid, home, process.args)
    return process


def _load_file(path: Path) -> list[dict]:
    try:
        records = []
        for line in path.read_text().splitlines():
            value = json.loads(line)
            if isinstance(value, dict): records.append(value)
        return records
    except (OSError, ValueError):
        return []


def register_spawn_file(path: Path) -> int:
    records = _load_file(Path(path))
    if not records:
        raise RuntimeError("monitor launcher did not record its spawned owner")
    value = records[-1]
    pid = value.get("pid")
    if type(pid) is not int:
        raise RuntimeError("invalid monitor spawn record")
    recorded = _record(pid, Path(value.get("home", "")), value.get("argv", []), value.get("pgid"))
    if value.get("birth") != recorded["birth"]:
        _owned.pop(pid, None)
        raise RuntimeError("monitor spawn record no longer names the spawned process")
    return pid


def _alive(value: dict) -> bool:
    return _birth(value["pid"]) == value["birth"]


def _terminate(value: dict) -> None:
    if not _alive(value): return
    pid, pgid = value["pid"], value["pgid"]
    try:
        if pgid == pid: os.killpg(pgid, signal.SIGTERM)
        else: os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError): return
    deadline = time.monotonic() + 3
    while _alive(value) and time.monotonic() < deadline: time.sleep(.02)
    if _alive(value):
        try:
            if pgid == pid: os.killpg(pgid, signal.SIGKILL)
            else: os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError): pass


def cleanup() -> None:
    global _cleaning
    if _cleaning: return
    _cleaning = True
    try:
        registry = os.environ.get("ROZORO_TEST_PROCESS_REGISTRY")
        if registry:
            for raw in _load_file(Path(registry)):
                try:
                    value = _record(raw["pid"], Path(raw["home"]), raw["argv"], raw.get("pgid"))
                    if raw.get("birth") != value["birth"]: _owned.pop(value["pid"], None)
                except (KeyError, OSError, RuntimeError, TypeError): pass
        values = list(_owned.values())
        for value in values: _terminate(value)
        _owned.clear()
        for home in {Path(v["home"]) for v in values}:
            try: home.relative_to(Path(tempfile.gettempdir()).resolve())
            except ValueError: continue
            import shutil; shutil.rmtree(home, ignore_errors=True)
    finally: _cleaning = False


def guard(parent: int, registry: Path) -> None:
    os.environ["ROZORO_TEST_PROCESS_REGISTRY"] = str(registry)
    while True:
        try: os.kill(parent, 0)
        except ProcessLookupError: cleanup(); return
        time.sleep(.05)


def _interrupt(signum, _frame):
    cleanup(); signal.signal(signum, signal.SIG_DFL); os.kill(os.getpid(), signum)


if os.environ.get("ROZORO_PROCESS_CLEANUP_NO_ATEXIT") != "1":
    atexit.register(cleanup)
    for _signal in (signal.SIGINT, signal.SIGTERM): signal.signal(_signal, _interrupt)

if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "guard":
    guard(int(sys.argv[2]), Path(sys.argv[3]))
